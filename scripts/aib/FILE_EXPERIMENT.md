# File export experiment for AIB

Branch: `codex/rtk-file-probe`, based on `codex/aib-runtime` at `31cb77a`.
Compare with JSON branch `codex/rtk-json-probe`, commit `9305292`.
Only captured Git status, diff and log are in scope. No AIB integration,
compact processing, new dependencies or published runtime changes.

## Contract

The caller sets `RTK_AIB_EXPORT_PATH` to a fresh file path in an existing
directory. RTK keeps ordinary stdout, stderr and exit code and writes:

```json
{
  "version": 1,
  "comparison": {
    "original": "captured Git text before RTK formatting",
    "gitArgs": ["diff"]
  }
}
```

Actual RTK stdout already travels through the ordinary pipe, so the file does
not duplicate it. File contents plus captured stdout give the same facts as
the JSON experiment. No extra Git subprocess is added.

This uses capture sites rather than blindly exporting `track()` arguments:
those arguments can combine stat+diff and do not necessarily contain exact
printed newlines. Keeping the same evidence contract avoids comparing a
smaller but less accurate patch against the JSON implementation.

The caller owns call ID association, path allocation, directories and retention.
RTK writes only the supplied file, with exclusive creation. An occupied path is
not overwritten. Export failure is silent and does not change command behavior;
missing/invalid evidence means unknown, never zero savings. No retry or queue.

Writing is synchronous at existing capture points, buffered and flushed before
return. It is not background work, and there is no fsync durability guarantee.
Consumers should read after RTK exits; interruption/write failure may leave a
partial file, which the consumer must reject. This experiment does not implement
the consumer or raw cleanup policy.

Failed Git captures write version only, without comparison. Successful empty
captures write an empty original. A failure to spawn Git can leave no file.
Help, other commands and routes outside these handlers do not export.

Default compact diff exports the captured diff, without the separate stat.
Default log exports the effective Git output after RTK's added format/limit,
not a hypothetical unlimited plain `git log`. Effective args are recorded.
This UTF-8 text experiment does not define arbitrary binary output support.

`RTK_TRACKING_DISABLED=1` independently skips automatic SQLite tracking and
approximate token counting. Unset or `0` preserves upstream behavior. Existing
database/query APIs remain. Telemetry and integrity checks are unchanged.

## Reproduce

Keep the JSON release binary from `9305292` before rebuilding this branch.

```powershell
./scripts/aib/check.ps1 -Release
python scripts/aib/transport_probe.py --baseline .tmp/json-probe/baseline.exe --json-candidate .tmp/json-probe/json-candidate.exe --candidate target/x86_64-pc-windows-msvc/release/rtk.exe --out .tmp/file-probe/first --rounds 15
node scripts/aib/transport_parse_probe.cjs .tmp/file-probe/first
```

Baseline is the unchanged executable from `v0.42.3-aib.1`. The corpus matches
the original JSON experiment. Disposable Git repositories and databases are
used; every timed file-export invocation gets a fresh evidence path.

Nine modes: baseline, each candidate with export off and tracking on/off,
JSON export with tracking on/off, file export with tracking on/off. Each timed
case interleaves modes in deterministic shuffled order. First calls use fresh
DBs; they do not represent an OS cold boot. Times include process startup,
Git, formatting, pipe transfer, optional SQLite and optional evidence write.

The Node probe separately measures UTF-8 decode/parse of already received JSON
versus file read/decode/parse plus ordinary stdout decode, with a warm filesystem
cache. It does not include AIB trace writing. If a future consumer postpones
file analysis until offline processing, that read/parse need not delay users.

Tests compare stdout/stderr/exit, file+stdout versus JSON, source versus Git
with captured args, tracking behavior, occupied paths and inaccessible export
destinations. Local results and artifact examples: `.tmp/file-probe/report.md`.

## Updating upstream

File export changes six capture sites in the three Git handlers; function
signatures and printing remain upstream's. The helper is a new module discovered
by the existing automod setup. JSON additionally wraps dispatch, passes output
state through handler signatures and replaces print sites. Both still need a
review when upstream changes capture/filtering behavior; line count alone is
not a compatibility guarantee.
