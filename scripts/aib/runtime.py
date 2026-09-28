"""Build artifact checks shared by local work and the five GitHub runners."""

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tarfile
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / ".tmp" / "aib-release"
TARGETS = (
    "x86_64-pc-windows-msvc",
    "x86_64-unknown-linux-musl",
    "aarch64-unknown-linux-gnu",
    "x86_64-apple-darwin",
    "aarch64-apple-darwin",
)


def archive_name(target):
    extension = "zip" if "windows" in target else "tar.gz"
    return f"rtk-{target}.{extension}"


def run(args, cwd, env):
    result = subprocess.run(
        [str(arg) for arg in args], cwd=cwd, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=90,
    )
    if result.returncode:
        raise RuntimeError(
            f"{args[0]} exited {result.returncode}: "
            f"{(result.stderr or result.stdout)[-1800:]}"
        )
    return result.stdout


def smoke(binary):
    binary = binary.resolve()
    with tempfile.TemporaryDirectory(prefix="rtk-aib-smoke-") as temporary:
        root = Path(temporary)
        repo = root / "repo"
        repo.mkdir()
        env = dict(os.environ)
        env.update({
            "RTK_TELEMETRY_DISABLED": "1",
            "RTK_DB_PATH": str(root / "history.db"),
            "RTK_TEE_DIR": str(root / "tee"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "NO_COLOR": "1",
        })
        version = run([binary, "--version"], repo, env).strip()
        if version != "rtk 0.42.3":
            raise RuntimeError(f"Unexpected binary version: {version}")
        run([binary, "--help"], repo, env)
        run(["git", "init", "--initial-branch=main"], repo, env)
        run(["git", "config", "user.name", "AIB smoke"], repo, env)
        run(["git", "config", "user.email", "smoke@example.invalid"], repo, env)
        fixture = repo / "fixture.txt"
        fixture.write_text("baseline\n", encoding="utf-8")
        run(["git", "add", "fixture.txt"], repo, env)
        run(["git", "commit", "-m", "baseline smoke"], repo, env)
        fixture.write_text("baseline\nchanged-by-smoke\n", encoding="utf-8")
        cases = (
            (["git", "status"], "fixture.txt"),
            (["git", "diff"], "changed-by-smoke"),
            (["git", "log", "-1"], "baseline smoke"),
        )
        for args, expected in cases:
            output = run([binary, *args], repo, env)
            if expected not in output:
                raise RuntimeError(f"Missing {expected!r} in {args}: {output[:1200]}")
        with closing(sqlite3.connect(root / "history.db")) as database:
            rows = database.execute("SELECT COUNT(*) FROM commands").fetchone()[0]
            if rows != len(cases):
                raise RuntimeError(f"Expected {len(cases)} tracking rows, got {rows}")
        print(f"PASS {version}: startup, Git status/diff/log, {rows} tracking rows")


def package(target):
    name = "rtk.exe" if "windows" in target else "rtk"
    binary = ROOT / "target" / target / "release" / name
    smoke(binary)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    archive = OUTPUT / archive_name(target)
    if "windows" in target:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(binary, name)
    else:
        with tarfile.open(archive, "w:gz") as bundle:
            bundle.add(binary, arcname=name)
    # Check that the packaged bytes equal the binary that passed smoke.
    verify_archive(archive, hashlib.sha256(binary.read_bytes()).hexdigest())
    print(f"Packaged {archive.name}: {archive.stat().st_size} bytes")


def verify_archive(archive, expected_binary_hash=None):
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            if bundle.namelist() != ["rtk.exe"]:
                raise RuntimeError(f"Unexpected archive members: {archive.name}")
            binary = bundle.read("rtk.exe")
    else:
        with tarfile.open(archive, "r:gz") as bundle:
            if bundle.getnames() != ["rtk"] or not bundle.getmember("rtk").isfile():
                raise RuntimeError(f"Unexpected archive members: {archive.name}")
            if not bundle.getmember("rtk").mode & 0o111:
                raise RuntimeError(f"Missing executable permission: {archive.name}")
            binary = bundle.extractfile("rtk").read()
    digest = hashlib.sha256(binary).hexdigest()
    if expected_binary_hash is not None and digest != expected_binary_hash:
        raise RuntimeError(f"Packaged binary differs: {archive.name}")
    return digest


def manifest(tag):
    if not re.fullmatch(r"v0\.42\.3-aib\.[1-9][0-9]*", tag):
        raise ValueError("Expected new prerelease tag v0.42.3-aib.N")
    archives = [OUTPUT / archive_name(target) for target in TARGETS]
    facts = []
    for target, archive in zip(TARGETS, archives):
        facts.append({
            "target": target,
            "asset": archive.name,
            "binarySha256": verify_archive(archive),
        })
    metadata = {
        "tag": tag,
        "upstreamTag": "v0.42.3",
        "sourceCommit": os.environ["GITHUB_SHA"],
        "rustVersion": "1.92.0",
        "workflowRun": os.environ["GITHUB_RUN_ID"],
        "targets": facts,
    }
    info = OUTPUT / "build-info.json"
    info.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    checksums = []
    for path in [*archives, info]:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checksums.append(f"{digest}  {path.name}\n")
    (OUTPUT / "checksums.txt").write_text("".join(checksums), encoding="utf-8")
    print(f"Validated {len(archives)} archives for {tag}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("smoke").add_argument("binary", type=Path)
    commands.add_parser("package").add_argument("--target", choices=TARGETS, required=True)
    commands.add_parser("manifest").add_argument("--tag", required=True)
    args = parser.parse_args()
    if args.command == "smoke":
        smoke(args.binary)
    elif args.command == "package":
        package(args.target)
    else:
        manifest(args.tag)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        raise SystemExit(str(error)) from None
