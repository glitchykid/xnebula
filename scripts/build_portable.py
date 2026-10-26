"""Build a self-contained Windows x64 ZIP from the verified official Python runtime."""

import argparse
import hashlib
import os
import tempfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

PYTHON_VERSION = "3.15.2"
PYTHON_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
)
# Published on https://www.python.org/downloads/release/python-3152/
PYTHON_SHA256 = "d012f3aa29cf07436dae8aea1fec0fd195c2612a0b059b1f915ae0afb9ad1f62"


def build(root: Path, runtime: Path, output: Path) -> Path:
    if hashlib.sha256(runtime.read_bytes()).hexdigest() != PYTHON_SHA256:
        raise ValueError("Python runtime checksum does not match the official release.")
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    with zipfile.ZipFile(runtime) as python:
        names = python.namelist()
        required = {"python.exe", "python315.dll", "python315.zip", "python315._pth", "LICENSE.txt"}
        if not required.issubset(names):
            raise ValueError("Python runtime is incomplete.")
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
                raise ValueError("Unsafe path in Python runtime archive.")
        output.mkdir(parents=True, exist_ok=True)
        destination = output / f"xnebula-{version}-windows-x64.zip"
        with tempfile.TemporaryDirectory(dir=output) as temporary:
            staging = Path(temporary) / "bundle.zip"
            with zipfile.ZipFile(staging, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                for name in names:
                    content = python.read(name)
                    if name == "python315._pth":
                        content = b"python315.zip\n.\n../src\n"
                    bundle.writestr("XNebula/.runtime/" + name, content)
                files = [
                    root / name
                    for name in (
                        "Start-XNebula.cmd",
                        "Start-XNebula-Admin.cmd",
                        "START-HERE.txt",
                        "README.md",
                        "scripts/launch.ps1",
                    )
                ]
                files += sorted((root / "src/xnebula").glob("*.py"))
                files += sorted((root / "docs").rglob("*.md"))
                for file in files:
                    bundle.write(file, "XNebula/" + file.relative_to(root).as_posix())
            os.replace(staging, destination)
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".zip.sha256").write_text(
        f"{checksum}  {destination.name}\n", encoding="ascii"
    )
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True, help=f"Downloaded from {PYTHON_URL}")
    parser.add_argument("--output", type=Path, default=Path("dist"))
    args = parser.parse_args()
    try:
        print(build(Path(__file__).resolve().parents[1], args.runtime, args.output))
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Build failed: {error}\n")
