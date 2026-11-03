"""Reproducible frontend build and asset sync (R08).

One command builds both frontend modes from a clean install and syncs the
resulting local-UI assets into the Python package:

    python scripts/build_frontend.py          # npm ci + both builds + sync
    python scripts/build_frontend.py --sync-only   # only re-sync existing dist/

Steps:
1. npm ci (locked dependencies from frontend/package-lock.json)
2. npm run build          (local UI  -> frontend/dist)
3. npm run build:showcase (showcase   -> frontend/dist-showcase)
4. clean agent_evidence_kit/_web_static and copy frontend/dist into it

The showcase build stays in frontend/dist-showcase for static hosting and
is NOT packaged into the wheel. The local UI assets in _web_static are
what `python -m agent_evidence_kit web` serves.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = PROJECT_ROOT / "frontend"
PACKAGE_STATIC = PROJECT_ROOT / "agent_evidence_kit" / "_web_static"


def run(cmd: list[str], cwd: Path) -> None:
    print(f"+ {' '.join(cmd)} (cwd={cwd.name})")
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync-only", action="store_true",
                        help="skip npm and rebuild steps; only sync dist/")
    args = parser.parse_args()

    if not args.sync_only:
        run(["npm", "ci", "--no-audit", "--no-fund"], FRONTEND)
        run(["npm", "run", "build"], FRONTEND)
        run(["npm", "run", "build:showcase"], FRONTEND)

    dist = FRONTEND / "dist"
    if not (dist / "index.html").is_file():
        print("frontend/dist/index.html missing; build first", file=sys.stderr)
        return 1

    # Clean sync: never leave stale hashed assets behind (R08).
    if PACKAGE_STATIC.is_dir():
        shutil.rmtree(PACKAGE_STATIC)
    shutil.copytree(dist, PACKAGE_STATIC)
    synced = sorted(p.name for p in PACKAGE_STATIC.rglob("*") if p.is_file())
    print(f"synced {len(synced)} files -> {PACKAGE_STATIC}")
    for name in synced:
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
