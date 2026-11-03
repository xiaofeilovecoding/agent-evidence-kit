"""Config core regressions: P-01..P-05 + R01 deep-input CLI stability.

Independently derived expectations (from the frozen review and task
briefs), not generated from the current implementation output.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tests import helpers  # noqa: E402

PYTHON = sys.executable
ENV = {**os.environ, "PYTHONUTF8": "1"}


def run_cli(args):
    return subprocess.run(
        [PYTHON, "-m", "agent_evidence_kit", "config", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=ENV,
    )


class TempFileCase(unittest.TestCase):
    def write_input(self, data: bytes, suffix: str) -> str:
        handle = tempfile.NamedTemporaryFile(
            suffix=suffix, delete=False, dir=self.tmp
        )
        handle.write(data)
        handle.close()
        self.files.append(handle.name)
        return handle.name

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aek-test-")
        self.files = []

    def tearDown(self):
        for name in self.files:
            try:
                os.unlink(name)
            except OSError:
                pass
        try:
            os.rmdir(self.tmp)
            os.rmdir(self.tmp)
        except OSError:
            pass


class P01ResidueDetection(TempFileCase):
    def test_json_and_toml_residue_exit_1(self):
        for text, suffix in (
            (helpers.residue_config(), ".json"),
            (helpers.residue_config_toml(), ".toml"),
        ):
            path = self.write_input(text.encode("utf-8"), suffix)
            result = run_cli(["--input", path])
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            card = json.loads(result.stdout)
            codes = {
                f["code"]
                for s in card["services"]
                for f in s["findings"]
            }
            self.assertIn("POSSIBLE_TRANSPORT_RESIDUE", codes)
            self.assertIn("AMBIGUOUS_TRANSPORT", codes)
            self.assertEqual(card["services"][0]["transport"], "http")

    def test_command_and_url_also_ambiguous(self):
        path = self.write_input(helpers.ambiguous_config().encode("utf-8"), ".json")
        result = run_cli(["--input", path])
        self.assertEqual(result.returncode, 1)
        card = json.loads(result.stdout)
        codes = {f["code"] for s in card["services"] for f in s["findings"]}
        self.assertIn("AMBIGUOUS_TRANSPORT", codes)
        self.assertIn("TRANSPORT_CONFLICT", codes)
        self.assertIn("POSSIBLE_TRANSPORT_RESIDUE", codes)


class P02Privacy(TempFileCase):
    CANARIES = [
        helpers.CANARY_KEY,
        helpers.CANARY_URL,
        helpers.CANARY_TOKEN,
        helpers.CANARY_MARKDOWN,
        helpers.CANARY_EMAIL,
        "magpie-prod",
        "primary-svc",
        "local-tools",
        "MAGPIE_TOKEN",
        "npx",
        "magpie@1.2.3",
        "server.js",
        "node",
        "python",
        "dual",
        "uvx",
        "API_KEY",
    ]

    def test_no_canary_in_any_output(self):
        injected = json.dumps(
            {
                "mcp_servers": {
                    "svc\n# injected": {
                        "url": helpers.CANARY_URL + "&token=" + helpers.CANARY_KEY,
                        "env": {"X": "value\n| fake-row | more"},
                        "unknown_secret_field": helpers.CANARY_KEY,
                    }
                }
            },
            ensure_ascii=False,
        )
        cases = [
            (helpers.residue_config(), ".json"),
            (helpers.residue_config_toml(), ".toml"),
            (helpers.plain_stdio_config(), ".json"),
            (injected, ".json"),
        ]
        for text, suffix in cases:
            for out_format in ("json", "md"):
                for lang in ("zh-CN", "en"):
                    path = self.write_input(text.encode("utf-8"), suffix)
                    result = run_cli(
                        ["--input", path, "--format", out_format, "--lang", lang]
                    )
                    combined = result.stdout + result.stderr
                    for canary in self.CANARIES:
                        self.assertNotIn(canary, combined)
                    self.assertNotIn("svc", combined)

    def test_chinese_path_not_leaked(self):
        handle = tempfile.NamedTemporaryFile(
            prefix="配置", suffix=".json", delete=False, dir=self.tmp
        )
        handle.write(helpers.plain_stdio_config().encode("utf-8"))
        handle.close()
        self.files.append(handle.name)
        result = run_cli(["--input", handle.name])
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("配置", result.stdout)
        self.assertNotIn("配置", result.stderr)

    def test_error_paths_not_leaked(self):
        missing = os.path.join(self.tmp, "zzcanaryECHO99_config.json")
        result = run_cli(["--input", missing])
        self.assertEqual(result.returncode, 2)
        combined = result.stdout + result.stderr
        self.assertNotIn("zzcanaryECHO99", combined)
        self.assertNotIn(self.tmp, combined)
        self.assertIn("INPUT_UNREADABLE", result.stdout)


class R01DeepInput(TempFileCase):
    """Deeply nested input must be rejected stably, never crash/leak."""

    def test_deep_json_stable_error(self):
        for depth in (1500, 300):
            path = self.write_input(helpers.deep_config_json(depth).encode(), ".json")
            result = run_cli(["--input", path])
            self.assertEqual(result.returncode, 2, f"depth={depth}")
            self.assertIn("LIMIT_EXCEEDED", result.stdout)
            self.assertNotIn("Traceback", result.stderr)
            self.assertNotIn("agent_evidence_kit", result.stderr)
            self.assertNotIn(self.tmp, result.stderr)
            self.assertNotIn(".py", result.stderr)

    def test_deep_toml_stable_error(self):
        for depth in (1500, 300):
            path = self.write_input(helpers.deep_config_toml(depth).encode(), ".toml")
            result = run_cli(["--input", path])
            self.assertEqual(result.returncode, 2, f"depth={depth}")
            self.assertIn("LIMIT_EXCEEDED", result.stdout)
            self.assertNotIn("Traceback", result.stderr)
            self.assertNotIn(self.tmp, result.stderr)

    def test_depth_16_boundary_ok_17_rejected(self):
        ok = json.dumps(
            {"mcp_servers": {"s": {"command": "cmd", "probe": None}}}
        )
        # exactly depth-16 doc: root(1)+mcp_servers(2)+svc(3)+probe(4)+12 wraps
        node = {"leaf": True}
        for _ in range(12):
            node = {"n": node}
        ok = json.dumps({"mcp_servers": {"s": {"command": "cmd", "probe": node}}})
        path = self.write_input(ok.encode(), ".json")
        self.assertEqual(run_cli(["--input", path]).returncode, 0)

        node = {"leaf": True}
        for _ in range(13):
            node = {"n": node}
        bad = json.dumps({"mcp_servers": {"s": {"command": "cmd", "probe": node}}})
        path = self.write_input(bad.encode(), ".json")
        result = run_cli(["--input", path])
        self.assertEqual(result.returncode, 2)
        self.assertIn("LIMIT_EXCEEDED", result.stdout)

    def test_deep_stream_event_cli_stable(self):
        deep = "data: " + "[" * 1500 + "]" * 1500 + "\n\n"
        path = self.write_input(deep.encode(), ".sse")
        result = subprocess.run(
            [PYTHON, "-m", "agent_evidence_kit", "stream", "--input", path],
            cwd=PROJECT_ROOT, capture_output=True, text=True,
            encoding="utf-8", env=ENV,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("LIMIT_EXCEEDED", result.stdout)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn(self.tmp, result.stderr)


class P03Limits(TempFileCase):
    def test_256kib_boundary(self):
        under = {
            "mcp_servers": {
                "svc": {
                    "command": "cmd",
                    "args": ["x" * 1000] * 240,
                }
            }
        }
        raw = json.dumps(under).encode("utf-8")
        self.assertLessEqual(len(raw), 256 * 1024)
        path = self.write_input(raw, ".json")
        result = run_cli(["--input", path])
        self.assertEqual(result.returncode, 0, result.stderr)

        over = dict(under)
        over["mcp_servers"]["svc"]["args"] = ["x" * 1000] * 300
        raw = json.dumps(over).encode("utf-8")
        self.assertGreater(len(raw), 256 * 1024)
        path = self.write_input(raw, ".json")
        result = run_cli(["--input", path])
        self.assertEqual(result.returncode, 2)
        self.assertIn("INPUT_TOO_LARGE", result.stdout)
        self.assertNotIn("svc", result.stdout)

    def test_service_count_limit(self):
        for count, expected in ((32, 0), (33, 2)):
            doc = {
                "mcp_servers": {
                    f"svc-{i}": {"command": "cmd"} for i in range(count)
                }
            }
            path = self.write_input(json.dumps(doc).encode("utf-8"), ".json")
            result = run_cli(["--input", path])
            self.assertEqual(result.returncode, expected, f"count={count}")

    def test_rejections_exit_2(self):
        cases = [
            (b'{"mcp_servers": {"a": {"command": "x"}, "b": {"url": "u"}}, "mcpServers": {}}', ".json", "INVALID_STRUCTURE"),
            (b'{"unrelated": {"a": {"command": "x"}}}', ".json", "INVALID_STRUCTURE"),
            (b'{"mcp_servers": {"a": {"command": "x"}}}', ".yaml", "UNSUPPORTED_FORMAT"),
            (b"key = = 2", ".toml", "INVALID_SYNTAX"),
            (b"{broken", ".json", "INVALID_SYNTAX"),
            (b"\xff\xfe\x00bad", ".json", "INVALID_ENCODING"),
            (b'{"mcp_servers": {"a": {"command": "x"}, "a": {"url": "u"}}}', ".json", "DUPLICATE_KEY"),
            (b"[mcp_servers]\nx = 1\n", ".toml", "INVALID_STRUCTURE"),
        ]
        for data, suffix, code in cases:
            path = self.write_input(data, suffix)
            result = run_cli(["--input", path])
            self.assertEqual(result.returncode, 2, f"{code}: {result.stdout}")
            self.assertIn(code, result.stdout)
            self.assertNotIn(self.tmp, result.stdout + result.stderr)

    def test_toml_duplicate_key(self):
        data = b'[mcp_servers.svc]\ncommand = "x"\ncommand = "y"\n'
        path = self.write_input(data, ".toml")
        result = run_cli(["--input", path])
        self.assertEqual(result.returncode, 2)
        self.assertIn("DUPLICATE_KEY", result.stdout)

    def test_toml_string_edge_cases_still_parse(self):
        # Literal strings and comments must not confuse bracket counting.
        data = (
            '[mcp_servers.s]\n'
            'command = "echo \\"hi\\""\n'
            "path = 'C:\\backslash\\path'\n"
            '# comment with braces { [ }\n'
            'note = "text # not a comment {ok}"\n'
        )
        path = self.write_input(data.encode("utf-8"), ".toml")
        result = run_cli(["--input", path])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class P04StructureOnly(TempFileCase):
    def test_single_command_not_validated_exit_0(self):
        path = self.write_input(
            b'{"mcp_servers": {"a": {"command": "cmd", "args": ["b"]}}}', ".json"
        )
        result = run_cli(["--input", path])
        self.assertEqual(result.returncode, 0)
        card = json.loads(result.stdout)
        service = card["services"][0]
        self.assertEqual(service["transport"], "stdio")
        self.assertEqual(
            [f["code"] for f in service["findings"]], ["NOT_VALIDATED"]
        )
        self.assertEqual(card["outcome"], "not_validated")

    def test_single_url_infers_http(self):
        path = self.write_input(
            b'{"mcp_servers": {"a": {"url": "https://x.example.invalid"}}}', ".json"
        )
        result = run_cli(["--input", path])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["services"][0]["transport"], "http")

    def test_type_errors_exit_1(self):
        cases = [
            b'{"mcp_servers": {"a": {"command": ""}}}',
            b'{"mcp_servers": {"a": {"url": 5}}}',
            b'{"mcp_servers": {"a": {"args": [1]}}}',
            b'{"mcp_servers": {"a": {"env": {"k": 2}}}}',
            b'{"mcp_servers": {"a": {"transport": 3}}}',
        ]
        for data in cases:
            path = self.write_input(data, ".json")
            result = run_cli(["--input", path])
            self.assertEqual(result.returncode, 1, data)
            card = json.loads(result.stdout)
            codes = {f["code"] for f in card["services"][0]["findings"]}
            self.assertIn("INVALID_FIELD_TYPE", codes)
            self.assertNotIn("cmd", result.stdout)

    def test_empty_services_map(self):
        path = self.write_input(b'{"mcp_servers": {}}', ".json")
        result = run_cli(["--input", path])
        self.assertEqual(result.returncode, 0)
        card = json.loads(result.stdout)
        self.assertEqual(card["summary"]["service_count"], 0)

    def test_empty_service_object_is_valid_structure(self):
        path = self.write_input(b'{"mcp_servers": {"a": {}}}', ".json")
        result = run_cli(["--input", path])
        self.assertEqual(result.returncode, 0)
        service = json.loads(result.stdout)["services"][0]
        self.assertEqual(service["transport"], "unknown")


class P05DeterminismAndImmutability(TempFileCase):
    def test_deterministic_output(self):
        path = self.write_input(helpers.residue_config().encode("utf-8"), ".json")
        first = run_cli(["--input", path, "--lang", "en"])
        second = run_cli(["--input", path, "--lang", "en"])
        self.assertEqual(first.returncode, second.returncode)
        self.assertEqual(first.stdout, second.stdout)

    def test_input_bytes_unchanged(self):
        data = helpers.residue_config().encode("utf-8")
        path = self.write_input(data, ".json")
        run_cli(["--input", path])
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), data)

    def test_help_works_without_key(self):
        result = run_cli(["--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("--input", result.stdout)

    def test_bad_args_generic(self):
        result = run_cli(["--format", "yaml", "--input", "x.json"])
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("yaml", result.stdout + result.stderr)
        result = run_cli(["--unknown-flag"])
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("unknown-flag", result.stdout + result.stderr)

    def test_no_subprocess_no_network(self):
        data = json.dumps(
            {
                "mcp_servers": {
                    "a": {
                        "command": sys.executable,
                        "args": ["-c", "print('SHOULD_NOT_RUN')"],
                    }
                }
            }
        ).encode("utf-8")
        path = self.write_input(data, ".json")
        result = run_cli(["--input", path])
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("SHOULD_NOT_RUN", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
