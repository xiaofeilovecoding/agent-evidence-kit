"""Unified CLI: config/stream subcommands over the two bounded cores.

Argument/help errors are intentionally generic: user-supplied paths and
values are never echoed to stdout or stderr. Exit-code semantics of the
two original cores are preserved:
- config: 0 = structure check only, 1 = findings need review, 2 = input error
- stream: 0 = normal termination, 1 = needs review (warnings), 2 = invalid input
"""
from __future__ import annotations

import json
import os
import sys

from .config.analysis import analyze_bytes as config_analyze_bytes
from .config.parsers import InputRejected as ConfigInputRejected
from .config.parsers import read_file_bytes
from .stream.parsers import InputRejected as StreamInputRejected
from .config.renderers import LANGUAGES, OUTPUT_FORMATS
from .config.renderers import render_card as render_config_card
from .stream.renderers import render_card as render_stream_card
from .demos import STREAM_DEMO_BYTES
from .stream.analysis import analyze_bytes as stream_analyze_bytes
from .stream.compare import compare_projections
from .stream.diagnostics import EXIT_CODES
from .stream.renderers import render_compare_card

USAGE = (
    "usage: python -m agent_evidence_kit config --input <config.json|config.toml> "
    "[--format json|md] [--lang zh-CN|en]\n"
    "       python -m agent_evidence_kit stream --input <capture.sse|capture.txt> "
    "[--format json|md] [--lang zh-CN|en] [--chunk-bytes 1-65536]\n"
    "       python -m agent_evidence_kit stream demo --case <name> [same output options]\n"
    "       python -m agent_evidence_kit stream compare --baseline <normal.sse> "
    "--candidate <failed.sse> [--format json|md] [--lang zh-CN|en] [--chunk-bytes 1-65536]\n"
    "       python -m agent_evidence_kit web [--port N] [--no-open]\n"
    "compare exit codes: 0 = no observed differences, 1 = differences observed, "
    "2 = invalid input on either side"
)

NL_REAL = chr(10)

_EXIT_ERROR = 2
_EXIT_FINDINGS = 1
_EXIT_OK = 0

CONFIG_EXTENSIONS = {".json": "json", ".toml": "toml"}
STREAM_EXTENSIONS = (".sse", ".txt")


def _arg_error(message: str) -> int:
    print(USAGE, file=sys.stderr)
    print(message, file=sys.stderr)
    return _EXIT_ERROR


def _collect_output_args(argv: list[str], out: dict) -> int | None:
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--help", "-h"):
            print(USAGE)
            return _EXIT_OK
        if arg == "--format":
            if i + 1 >= len(argv) or argv[i + 1] not in OUTPUT_FORMATS:
                return _arg_error("--format must be json or md")
            out["format"] = argv[i + 1]
            i += 2
            continue
        if arg == "--lang":
            if i + 1 >= len(argv) or argv[i + 1] not in LANGUAGES:
                return _arg_error("--lang must be zh-CN or en")
            out["lang"] = argv[i + 1]
            i += 2
            continue
        if arg == "--chunk-bytes":
            if i + 1 >= len(argv) or not argv[i + 1].isdigit():
                return _arg_error("--chunk-bytes must be an integer")
            value = int(argv[i + 1])
            if not 1 <= value <= 65536:
                return _arg_error("--chunk-bytes must be between 1 and 65536")
            out["chunk"] = value
            i += 2
            continue
        return _arg_error("unknown or misplaced argument")
    return None


def _emit(core: dict, output_format: str, lang: str, error_code: str | None,
          module: str) -> None:
    render = render_config_card if module == "config" else render_stream_card
    card = render(core, lang, output_format)
    if output_format == "json":
        print(json.dumps(card, ensure_ascii=False, indent=2))
    else:
        print(card, end="" if card.endswith("\n") else "\n")
    if error_code is not None:
        print(error_code, file=sys.stderr)


def _run_config(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(USAGE)
        return _EXIT_OK
    input_path = None
    out = {"format": "json", "lang": "zh-CN"}
    rest: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--input":
            if i + 1 >= len(argv):
                return _arg_error("--input requires a value")
            input_path = argv[i + 1]
            i += 2
            continue
        rest.append(argv[i])
        i += 1
    if input_path is None:
        return _arg_error("--input is required for config")
    status = _collect_output_args(rest, out)
    if status is not None:
        return status
    try:
        raw = read_file_bytes(input_path)
        ext = os.path.splitext(input_path)[1].lower()
        input_format = CONFIG_EXTENSIONS.get(ext)
        if input_format is None:
            raise InputRejected("UNSUPPORTED_FORMAT")
        core = config_analyze_bytes(raw, input_format)
    except ConfigInputRejected as rejected:
        _emit({"error": rejected.code}, out["format"], out["lang"], rejected.code, "config")
        return _EXIT_ERROR
    exit_code = _EXIT_FINDINGS if core["outcome"] == "needs_review" else _EXIT_OK
    _emit(core, out["format"], out["lang"], None, "config")
    return exit_code


def _stream_exit_code(core: dict) -> int:
    exit_code = _EXIT_OK
    for finding in core["findings"]:
        if finding["severity"] == "error":
            exit_code = _EXIT_ERROR
            break
        if finding["severity"] == "warning":
            exit_code = _EXIT_FINDINGS
    return exit_code


def _run_stream_inspect(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(USAGE)
        return _EXIT_OK
    out = {"format": "json", "lang": "zh-CN", "chunk": 4096}
    input_path = None
    rest: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--input":
            if i + 1 >= len(argv):
                return _arg_error("--input requires a value")
            input_path = argv[i + 1]
            i += 2
            continue
        rest.append(argv[i])
        i += 1
    if input_path is None:
        return _arg_error("--input is required for stream")
    status = _collect_output_args(rest, out)
    if status is not None:
        return status
    ext = os.path.splitext(input_path)[1].lower()
    if ext not in STREAM_EXTENSIONS:
        _emit({"error": "INPUT_UNREADABLE"}, out["format"], out["lang"], "INPUT_UNREADABLE", "stream")
        return _EXIT_ERROR
    try:
        with open(input_path, "rb") as handle:
            from .stream.analysis import analyze_chunks

            core = analyze_chunks(iter(lambda: handle.read(out["chunk"]), b""))
    except (ConfigInputRejected, StreamInputRejected) as rejected:
        _emit({"error": rejected.code}, out["format"], out["lang"], rejected.code, "stream")
        return _EXIT_ERROR
    except OSError:
        _emit({"error": "INPUT_UNREADABLE"}, out["format"], out["lang"], "INPUT_UNREADABLE", "stream")
        return _EXIT_ERROR
    _emit(core, out["format"], out["lang"], None, "stream")
    return _stream_exit_code(core)


def _run_stream_demo(argv: list[str]) -> int:
    out = {"format": "json", "lang": "zh-CN", "chunk": 4096}
    case = None
    rest: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--case":
            if i + 1 >= len(argv):
                return _arg_error("--case requires a value")
            case = argv[i + 1]
            i += 2
            continue
        rest.append(argv[i])
        i += 1
    if case is None:
        return _arg_error("--case is required for demo")
    if case not in STREAM_DEMO_BYTES:
        return _arg_error("--case must be one of the built-in demo names")
    status = _collect_output_args(rest, out)
    if status is not None:
        return status
    try:
        core = stream_analyze_bytes(STREAM_DEMO_BYTES[case], out["chunk"])
    except (ConfigInputRejected, StreamInputRejected) as rejected:
        _emit({"error": rejected.code}, out["format"], out["lang"], rejected.code, "stream")
        return _EXIT_ERROR
    _emit(core, out["format"], out["lang"], None, "stream")
    return _stream_exit_code(core)


def _read_stream_input(path: str, chunk: int):
    """Reads one stream input through the existing bounded pipeline."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in STREAM_EXTENSIONS:
        raise StreamInputRejected("INPUT_UNREADABLE")
    with open(path, "rb") as handle:
        from .stream.analysis import analyze_chunks

        return analyze_chunks(iter(lambda: handle.read(chunk), b""))


def _run_stream_compare(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(USAGE)
        return _EXIT_OK
    out = {"format": "json", "lang": "zh-CN", "chunk": 4096}
    baseline_path = None
    candidate_path = None
    rest: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--baseline":
            if i + 1 >= len(argv):
                return _arg_error("--baseline requires a value")
            baseline_path = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--candidate":
            if i + 1 >= len(argv):
                return _arg_error("--candidate requires a value")
            candidate_path = argv[i + 1]
            i += 2
            continue
        rest.append(argv[i])
        i += 1
    if baseline_path is None or candidate_path is None:
        return _arg_error("--baseline and --candidate are both required for compare")
    status = _collect_output_args(rest, out)
    if status is not None:
        return status
    try:
        baseline_core = _read_stream_input(baseline_path, out["chunk"])
        candidate_core = _read_stream_input(candidate_path, out["chunk"])
    except (ConfigInputRejected, StreamInputRejected) as rejected:
        _emit({"error": rejected.code}, out["format"], out["lang"], rejected.code, "stream")
        return _EXIT_ERROR
    except OSError:
        _emit({"error": "INPUT_UNREADABLE"}, out["format"], out["lang"], "INPUT_UNREADABLE", "stream")
        return _EXIT_ERROR
    # An invalid-input side (error cores) compares as its error projection.
    compare_core = compare_projections(baseline_core, candidate_core)
    card = render_compare_card(compare_core, out["lang"], out["format"])
    if out["format"] == "json":
        print(json.dumps(card, ensure_ascii=False, indent=2))
    else:
        print(card, end="" if card.endswith(NL_REAL) else NL_REAL)
    invalid = "error" in baseline_core or "error" in candidate_core
    if invalid:
        return _EXIT_ERROR
    return _EXIT_FINDINGS if compare_core["differences"] else _EXIT_OK


def _run_stream(argv: list[str]) -> int:
    if argv and argv[0] == "demo":
        return _run_stream_demo(argv[1:])
    if argv and argv[0] == "compare":
        return _run_stream_compare(argv[1:])
    return _run_stream_inspect(argv)


def main(argv: list[str]) -> int:
    if not argv:
        return _arg_error("a subcommand is required: config, stream, or web")
    if argv[0] == "config":
        return _run_config(argv[1:])
    if argv[0] == "stream":
        return _run_stream(argv[1:])
    if argv[0] == "web":
        from .server.run import run_web

        return run_web(argv[1:])
    return _arg_error("unknown subcommand")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
