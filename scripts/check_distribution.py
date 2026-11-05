"""Check release contents and exercise an isolated wheel install (no model API)."""
from __future__ import annotations

import argparse
from email.parser import BytesParser
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import venv
import zipfile


def validate_member(name: str, *, source: bool = False) -> None:
    path = PurePosixPath(name)
    if (path.is_absolute() or ".." in path.parts or "\\" in name
            or re.match(r"^[A-Za-z]:", name)):
        raise ValueError("Unsafe archive path")
    if set(path.parts) & {".git", ".venv", "node_modules", "__pycache__", "artifacts", "reports"}:
        raise ValueError("Internal or generated files in distribution")
    for part in path.parts:
        if part == ".env" or part.startswith(".env."):
            if not (source and path.parts[-2:] == ("frontend", ".env.showcase")):
                raise ValueError("Environment file in distribution")
    if path.suffix in {".pyc", ".log"}:
        raise ValueError("Generated file in distribution")


def inspect_archives(wheel: Path, sdist: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        for name in names:
            validate_member(name)
        metadata = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata) != 1:
            raise ValueError("Missing wheel metadata")
        message = BytesParser().parsebytes(archive.read(metadata[0]))
        if message["Name"] != "agent-evidence-kit" or not message["Version"]:
            raise ValueError("Unexpected wheel identity")
        version = message["Version"]
        prefix = "agent_evidence_kit/_web_static/"
        required = {prefix + "index.html", prefix + "THIRD_PARTY_LICENSES.txt"}
        if not required.issubset(names):
            raise ValueError("Missing packaged web assets or licenses")
        html = archive.read(prefix + "index.html").decode("utf-8")
        refs = re.findall(r'(?:src|href)="(/assets/[^"?#]+)', html)
        if not refs or any(prefix + ref.lstrip("/") not in names for ref in refs):
            raise ValueError("Broken packaged asset reference")
        if not any("licenses/" in name and name.endswith("LICENSE") for name in names):
            raise ValueError("Missing package license")
    with tarfile.open(sdist) as archive:
        files = set()
        for member in archive.getmembers():
            validate_member(member.name, source=True)
            if member.issym() or member.islnk():
                raise ValueError("Link in source distribution")
            if member.isfile():
                files.add(member.name.split("/", 1)[-1])
        if not {"pyproject.toml", "LICENSE", "frontend/package-lock.json",
                "frontend/src/App.tsx", "scripts/check_distribution.py"}.issubset(files):
            raise ValueError("Missing source rebuild inputs")
    return version


def installed_check(expected: str) -> None:
    import agent_evidence_kit

    location = Path(agent_evidence_kit.__file__).resolve()
    if not location.is_relative_to(Path(sys.prefix).resolve()) or "site-packages" not in location.parts:
        raise ValueError("Package imported from outside isolated installation")
    if importlib.metadata.version("agent-evidence-kit") != expected:
        raise ValueError("Installed version mismatch")
    config = Path.cwd() / "synthetic-config.json"
    config.write_text('{"mcpServers":{"synthetic":{"command":"python",'
                      '"env":{"SYNTHETIC":"AEK_PACKAGE_CANARY"}}}}', encoding="utf-8")

    def cli(*args: str) -> dict:
        result = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", "-m", "agent_evidence_kit", *args],
            capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
        if result.returncode != 0 or "AEK_PACKAGE_CANARY" in result.stdout + result.stderr:
            raise ValueError("Installed CLI failed or exposed raw input")
        return json.loads(result.stdout)

    if cli("config", "--input", str(config), "--lang", "en")["summary"]["service_count"] != 1:
        raise ValueError("Installed config CLI result mismatch")
    if cli("stream", "demo", "--case", "normal", "--lang", "en")["verdict"] != "NORMAL_TERMINATION":
        raise ValueError("Installed stream CLI result mismatch")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "-I", "-m", "agent_evidence_kit", "web", "--port", str(port), "--no-open"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(base + "/api/health", timeout=.5) as response:
                    if json.load(response)["status"] == "ok":
                        break
            except OSError:
                if process.poll() is not None:
                    raise ValueError("Installed web service exited") from None
                time.sleep(.05)
        else:
            raise ValueError("Installed web service did not start")
        with urllib.request.urlopen(base, timeout=5) as response:
            html = response.read().decode("utf-8")
        for path in re.findall(r'(?:src|href)="(/assets/[^"?#]+)', html):
            with urllib.request.urlopen(base + path, timeout=5) as response:
                if response.status != 200 or not response.read():
                    raise ValueError("Installed web asset missing")
        with urllib.request.urlopen(base + "/THIRD_PARTY_LICENSES.txt", timeout=5) as response:
            if b"Facebook" not in response.read():
                raise ValueError("Installed frontend license missing")
    finally:
        process.terminate()
        process.wait(timeout=10)
    print(json.dumps({"version": expected, "isolated_install": True,
                      "cli": "PASS", "web_assets_and_licenses": "PASS"}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", nargs="?", type=Path)
    parser.add_argument("--installed", metavar="VERSION")
    args = parser.parse_args()
    if args.installed:
        installed_check(args.installed)
        return
    if args.dist is None:
        parser.error("distribution directory is required")
    wheels = sorted(args.dist.resolve().glob("*.whl"))
    sources = sorted(args.dist.resolve().glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise ValueError("Expected exactly one wheel and source distribution")
    version = inspect_archives(wheels[0], sources[0])
    with tempfile.TemporaryDirectory(prefix="aek-package-") as directory:
        root = Path(directory).resolve()
        if root.parent != Path(tempfile.gettempdir()).resolve():
            raise ValueError("Unexpected temporary workspace")
        environment = root / "env"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
                        "--no-input", str(wheels[0]) + "[web]"], check=True, timeout=180)
        subprocess.run([str(python), "-I", str(Path(__file__).resolve()), "--installed", version],
                       cwd=root, check=True, timeout=45)


if __name__ == "__main__":
    main()
