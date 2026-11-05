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


def check_assets(dist: Path, packaged: Path) -> bool:
    """Compare complete file sets and bytes, including obsolete hashed assets."""
    if not (dist / "index.html").is_file():
        return False
    def files(root: Path) -> dict[str, bytes]:
        return {path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*") if path.is_file()}
    return files(dist) == files(packaged)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--sync-only", action="store_true",
                        help="skip npm and rebuild steps; only sync dist/")
    mode.add_argument("--check", action="store_true",
                      help="compare existing dist/ with packaged assets without changing files")
    args = parser.parse_args()

    if args.check:
        if check_assets(FRONTEND / "dist", PACKAGE_STATIC):
            print("built and packaged frontend assets match")
            return 0
        print("packaged frontend differs; run scripts/build_frontend.py and commit the assets",
              file=sys.stderr)
        return 1

    if not args.sync_only:
        run(["npm", "ci", "--no-audit", "--no-fund"], FRONTEND)
        run(["npm", "run", "build"], FRONTEND)
        run(["npm", "run", "build:showcase"], FRONTEND)

    dist = FRONTEND / "dist"
    if not (dist / "index.html").is_file():
        print("frontend/dist/index.html missing; build first", file=sys.stderr)
        return 1

    # Clean sync: never leave stale hashed assets behind (R08).
    target = PACKAGE_STATIC.resolve()
    if target == PROJECT_ROOT.resolve() or not target.is_relative_to(PROJECT_ROOT.resolve()):
        raise ValueError("Asset sync target is outside the project")
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
