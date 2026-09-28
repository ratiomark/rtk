RTK runtime for AIB, based on upstream v0.42.3.

Adds opt-in file evidence for Git status, diff and log through `RTK_AIB_EXPORT_PATH`.
Evidence contains the captured Git stdout and effective Git arguments; ordinary RTK stdout stays unchanged.
Export errors never replace Git output or exit status, and existing evidence files are not overwritten.

`RTK_AIB=1` skips the automatic hook installation warning for explicit AIB calls.
`RTK_TRACKING_DISABLED=1` disables automatic SQLite tracking; default tracking remains unchanged.

Five native builds run Git/tracking tests and an isolated Git smoke before packaging,
including file evidence parity, occupied destinations and Git errors.
`checksums.txt` contains SHA-256 hashes; `build-info.json` identifies the exact source commit and build targets.

This prerelease does not change the RTK version used by AIB automatically.
