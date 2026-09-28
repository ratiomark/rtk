"""Compare JSON stdout and evidence files using the original JSON probe corpus."""

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import random
import sqlite3
import statistics
import subprocess
import tempfile
import time


def run(args, cwd, env):
    start = time.perf_counter_ns()
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, timeout=60)
    elapsed = (time.perf_counter_ns() - start) / 1_000_000
    return result, elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--json-candidate", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--rounds", type=int, default=15)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    baseline = str(args.baseline.resolve())
    candidate = str(args.candidate.resolve())
    json_candidate = str(args.json_candidate.resolve())
    report = {"rounds": args.rounds, "cases": [], "checks": []}
    with tempfile.TemporaryDirectory(prefix="rtk-json-probe-") as temp:
        root = Path(temp)
        env = os.environ.copy()
        env.update({
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "Probe",
            "GIT_AUTHOR_EMAIL": "probe@example.invalid",
            "GIT_COMMITTER_NAME": "Probe",
            "GIT_COMMITTER_EMAIL": "probe@example.invalid",
            "GIT_AUTHOR_DATE": "2020-01-01T12:00:00Z",
            "GIT_COMMITTER_DATE": "2020-01-01T12:00:00Z",
            "RTK_TELEMETRY_DISABLED": "1",
            "NO_COLOR": "1",
            "LC_ALL": "C",
        })
        env.pop("RTK_AIB_JSON", None)
        env.pop("RTK_TRACKING_DISABLED", None)
        env.pop("RTK_AIB_EXPORT_PATH", None)

        def git(cwd, *argv):
            result, _ = run(["git", *argv], cwd, env)
            if result.returncode:
                raise RuntimeError(result.stderr.decode(errors="replace"))
            return result

        repos = {}
        for size in ("small", "large", "empty"):
            repo = root / size
            repo.mkdir()
            git(repo, "init", "-b", "main")
            repos[size] = repo
            if size == "empty":
                continue
            count = 4 if size == "small" else 10000
            (repo / "sample.txt").write_text(
                "".join(f"old {i:06d} " + "x" * 60 + "\n" for i in range(count)),
                encoding="utf-8",
            )
            git(repo, "add", ".")
            message = root / f"{size}-message.txt"
            message.write_text("Initial fixture\n\n" + ("Large log body; Unicode пример.\n" * (1 if size == "small" else 12000)), encoding="utf-8")
            git(repo, "commit", "-F", str(message))
            (repo / "sample.txt").write_text(
                "".join(f"new {i:06d} " + "y" * 60 + "\n" for i in range(count)),
                encoding="utf-8",
            )
            for index in range(1 if size == "small" else 1200):
                (repo / f"untracked-{index:04d}.txt").write_text("probe\n", encoding="utf-8")

        modes = {
            "baseline": (baseline, "text", False),
            "json-plain-db": (json_candidate, "text", False),
            "json-plain-no-db": (json_candidate, "text", True),
            "json-db": (json_candidate, "json", False),
            "json-no-db": (json_candidate, "json", True),
            "file-plain-db": (candidate, "text", False),
            "file-plain-no-db": (candidate, "text", True),
            "file-db": (candidate, "file", False),
            "file-no-db": (candidate, "file", True),
        }
        cases = []
        for size in ("small", "large"):
            for command in ("status", "diff", "log"):
                cases.append((f"{size}-{command}", repos[size], [command]))
        cases.extend([
            ("large-log-full", repos["large"], ["log", "--format=%B", "-1"]),
            ("diff-stat", repos["small"], ["diff", "--stat"]),
            ("diff-passthrough", repos["small"], ["diff", "--no-compact"]),
            ("status-porcelain", repos["small"], ["status", "--porcelain"]),
            ("diff-error", repos["small"], ["diff", "nonexistent-ref"]),
            ("log-error", repos["small"], ["log", "nonexistent-ref"]),
            ("status-not-repo", root, ["status"]),
            ("empty-diff", repos["empty"], ["diff"]),
            ("empty-log", repos["empty"], ["log"]),
        ])
        for name, cwd, argv in cases:
            entry = {"name": name, "args": argv, "modes": {}}
            reference = None
            json_reference = None
            environments = {}
            for mode, (binary, transport, no_db) in modes.items():
                local = env.copy()
                db = root / f"{name}-{mode}.db"
                evidence_path = root / f"{name}-{mode}.json"
                local.update({
                    "RTK_DB_PATH": str(db),
                    "RTK_AIB_JSON": "1" if transport == "json" else "0",
                    "RTK_TRACKING_DISABLED": "1" if no_db else "0",
                })
                if transport == "file":
                    local["RTK_AIB_EXPORT_PATH"] = str(evidence_path)
                environments[mode] = local
                result, elapsed = run([binary, "git", *argv], cwd, local)
                visible = result.stdout
                evidence_bytes = 0
                payload = None
                if transport == "json":
                    payload = json.loads(result.stdout)
                    visible = payload["stdout"].encode("utf-8")
                    json_reference = payload
                    if mode == "json-no-db":
                        (args.out / f"{name}.json-stdout.json").write_bytes(result.stdout)
                elif transport == "file":
                    evidence = evidence_path.read_bytes()
                    evidence_bytes = len(evidence)
                    payload = json.loads(evidence)
                    payload["stdout"] = visible.decode("utf-8")
                    assert payload == json_reference, (name, "file and JSON carry different evidence")
                    if mode == "file-no-db":
                        (args.out / f"{name}.evidence.json").write_bytes(evidence)
                if payload is not None:
                    if "comparison" in payload:
                        comparison = payload["comparison"]
                        original = git(cwd, *comparison["gitArgs"])
                        assert original.stdout == comparison["original"].encode("utf-8"), (name, "original differs")
                current = (visible, result.stderr, result.returncode)
                if reference is None:
                    reference = current
                    (args.out / f"{name}.stdout.txt").write_bytes(visible)
                    (args.out / f"{name}.stderr.txt").write_bytes(result.stderr)
                assert current == reference, (name, mode, "visible stdout/stderr/exit changed")
                assert not (no_db and db.exists()), (name, mode, "disabled tracking created DB")
                rows = 0
                if db.exists():
                    with closing(sqlite3.connect(db)) as connection:
                        rows = connection.execute("select count(*) from commands").fetchone()[0]
                if result.returncode == 0 and not no_db:
                    assert rows == 1, (name, mode, "tracking should create one row")
                entry["modes"][mode] = {
                    "firstMs": elapsed,
                    "stdoutBytes": len(result.stdout),
                    "evidenceBytes": evidence_bytes,
                    "visibleBytes": len(visible),
                    "dbRows": rows,
                    "samplesMs": [],
                }
            # Interleave deterministic randomized modes to reduce timing drift.
            rng = random.Random(42)
            for iteration in range(args.rounds if name.startswith(("small-", "large-")) else 0):
                order = list(modes)
                rng.shuffle(order)
                for mode in order:
                    if modes[mode][1] == "file":
                        environments[mode]["RTK_AIB_EXPORT_PATH"] = str(root / f"{name}-{mode}-{iteration}.json")
                    result, elapsed = run([modes[mode][0], "git", *argv], cwd, environments[mode])
                    assert result.returncode == reference[2]
                    if modes[mode][1] == "file":
                        assert Path(environments[mode]["RTK_AIB_EXPORT_PATH"]).stat().st_size > 0
                    entry["modes"][mode]["samplesMs"].append(elapsed)
            for data in entry["modes"].values():
                samples = data["samplesMs"]
                if samples:
                    data["medianMs"] = statistics.median(samples)
                    data["p90Ms"] = sorted(samples)[int((len(samples) - 1) * .9)]
            report["cases"].append(entry)
            (args.out / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"PASS {name}", flush=True)
        existing = root / "existing.db"
        local = env.copy()
        local["RTK_DB_PATH"] = str(existing)
        run([candidate, "git", "status"], repos["small"], local)
        before = existing.read_bytes()
        local["RTK_TRACKING_DISABLED"] = "1"
        run([candidate, "git", "status"], repos["small"], local)
        assert existing.read_bytes() == before, "disabled tracking modified existing database"
        occupied = root / "occupied.json"
        occupied.write_bytes(b"existing evidence must survive")
        for argv in (["status"], ["diff", "nonexistent-ref"]):
            reference, _ = run([candidate, "git", *argv], repos["small"], local)
            for path in (occupied, root / "missing-parent" / "evidence.json", root):
                failure_env = {**local, "RTK_AIB_EXPORT_PATH": str(path)}
                result, _ = run([candidate, "git", *argv], repos["small"], failure_env)
                assert (result.stdout, result.stderr, result.returncode) == (reference.stdout, reference.stderr, reference.returncode)
                assert occupied.read_bytes() == b"existing evidence must survive"
        report["checks"] = [
            "15 cases: visible stdout, stderr, exit unchanged across nine modes",
            "file + stdout equals JSON envelope; source equals Git with captured effective arguments",
            "tracking disabled creates no SQLite database and leaves existing DB unchanged",
            "tracking enabled creates one row per successful call",
            "file failure leaves successful and failed Git results unchanged; occupied files are preserved",
        ]
    (args.out / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
