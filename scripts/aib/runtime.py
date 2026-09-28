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
        for key in ("RTK_AIB", "RTK_AIB_EXPORT_PATH", "RTK_AIB_JSON", "RTK_TRACKING_DISABLED"):
            env.pop(key, None)
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
        for index, (args, expected) in enumerate(cases):
            output = run([binary, *args], repo, env)
            if expected not in output:
                raise RuntimeError(f"Missing {expected!r} in {args}: {output[:1200]}")
            evidence_path = root / f"evidence-{index}.json"
            export_env = {
                **env,
                "RTK_AIB": "1",
                "RTK_TRACKING_DISABLED": "1",
                "RTK_AIB_EXPORT_PATH": str(evidence_path),
            }
            captured = subprocess.run(
                [str(binary), *args], cwd=repo, env=export_env,
                capture_output=True, text=True, encoding="utf-8", timeout=90,
            )
            if captured.returncode or captured.stdout != output:
                raise RuntimeError(f"File export changed output or exit status: {args}")
            if "No hook installed" in captured.stderr or "Hook outdated" in captured.stderr:
                raise RuntimeError(f"AIB invocation emitted hook warning: {args}")
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            comparison = evidence["comparison"]
            original = run(["git", *comparison["gitArgs"]], repo, env)
            if evidence["version"] != 1 or comparison["original"].replace("\r\n", "\n") != original:
                raise RuntimeError(f"Evidence differs from captured Git command: {args}")
            # Existing destinations must neither be overwritten nor break the command.
            saved = evidence_path.read_bytes()
            if run([binary, *args], repo, export_env) != output or evidence_path.read_bytes() != saved:
                raise RuntimeError(f"Occupied export destination changed result: {args}")
        error_args = [str(binary), "git", "diff", "--bad-aib-smoke-option"]
        error_env = {**env, "RTK_AIB": "1", "RTK_TRACKING_DISABLED": "1"}
        plain_error = subprocess.run(error_args, cwd=repo, env=error_env, capture_output=True, timeout=90)
        export_env = {**error_env, "RTK_AIB_EXPORT_PATH": str(root / "error.json")}
        export_error = subprocess.run(error_args, cwd=repo, env=export_env, capture_output=True, timeout=90)
        if not plain_error.returncode or (
            plain_error.returncode, plain_error.stdout, plain_error.stderr
        ) != (export_error.returncode, export_error.stdout, export_error.stderr):
            raise RuntimeError("File export changed Git error output or exit status")
        with closing(sqlite3.connect(root / "history.db")) as database:
            rows = database.execute("SELECT COUNT(*) FROM commands").fetchone()[0]
            if rows != len(cases):
                raise RuntimeError(f"Expected {len(cases)} tracking rows, got {rows}")
        print(f"PASS {version}: startup, Git status/diff/log, file evidence, errors, {rows} tracking rows")


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


def verify(directory):
    expected = {archive_name(target) for target in TARGETS} | {"build-info.json"}
    seen = set()
    for line in (directory / "checksums.txt").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        if name not in expected or name in seen:
            raise ValueError(f"Unexpected or repeated checksum entry: {name}")
        actual = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        if actual != digest:
            raise ValueError(f"Checksum mismatch: {name}")
        seen.add(name)
    if seen != expected:
        raise ValueError(f"Missing checksum entries: {expected - seen}")
    metadata = json.loads((directory / "build-info.json").read_text(encoding="utf-8"))
    targets = metadata["targets"]
    if len(targets) != len(TARGETS) or {item["target"] for item in targets} != set(TARGETS):
        raise ValueError("Manifest does not describe the five expected targets")
    for item in targets:
        if item["asset"] != archive_name(item["target"]):
            raise ValueError(f"Unexpected asset: {item['asset']}")
        verify_archive(directory / item["asset"], item["binarySha256"])
    print(f"PASS {metadata['tag']}: all five archives, binary hashes and manifest")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("smoke").add_argument("binary", type=Path)
    commands.add_parser("package").add_argument("--target", choices=TARGETS, required=True)
    commands.add_parser("manifest").add_argument("--tag", required=True)
    commands.add_parser("verify").add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.command == "smoke":
        smoke(args.binary)
    elif args.command == "package":
        package(args.target)
    elif args.command == "manifest":
        manifest(args.tag)
    else:
        verify(args.directory)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        raise SystemExit(str(error)) from None
