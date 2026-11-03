"""Generate the showcase data file from the real diagnostic cores.

Run:  python scripts/generate_showcase.py
Writes frontend/src/showcase-data.json. The showcase build renders this
pre-generated projection; it never hand-writes findings.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agent_evidence_kit import __version__  # noqa: E402
from agent_evidence_kit.config.analysis import analyze_bytes as config_analyze  # noqa: E402
from agent_evidence_kit.config.renderers import render_card as config_render  # noqa: E402
from agent_evidence_kit.demos import (  # noqa: E402
    CONFIG_DEMO_CASES,
    STREAM_DEMO_BYTES,
    STREAM_DEMO_CASES,
    STREAM_DEMO_DESCRIPTIONS,
    config_demo_bytes,
)
from agent_evidence_kit.stream.analysis import analyze_bytes as stream_analyze  # noqa: E402
from agent_evidence_kit.stream.renderers import render_card as stream_render  # noqa: E402

LANGUAGES = ("zh-CN", "en")


def main() -> int:
    cases = []
    for case in CONFIG_DEMO_CASES:
        raw, input_format = config_demo_bytes(case["case_id"])
        core = config_analyze(raw, input_format)
        results = {}
        for language in LANGUAGES:
            results[language] = {
                "card": config_render(core, language, "json"),
                "markdown": config_render(core, language, "md"),
            }
        cases.append(
            {
                "case_id": case["case_id"],
                "module": "config",
                "input_format": input_format,
                "description": case["description"],
                "results": results,
            }
        )
    for case_id in STREAM_DEMO_CASES:
        raw = STREAM_DEMO_BYTES[case_id]
        core = stream_analyze(raw)
        results = {}
        for language in LANGUAGES:
            results[language] = {
                "card": stream_render(core, language, "json"),
                "markdown": stream_render(core, language, "md"),
            }
        cases.append(
            {
                "case_id": case_id,
                "module": "stream",
                "description": STREAM_DEMO_DESCRIPTIONS[case_id],
                "results": results,
            }
        )
    payload = {
        "mode": "sample-showcase",
        "generated_with": __version__,
        "cases": cases,
    }
    target = PROJECT_ROOT / "frontend" / "src" / "showcase-data.json"
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {target} ({target.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
