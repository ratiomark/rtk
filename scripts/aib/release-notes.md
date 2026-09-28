RTK runtime for AIB. Infrastructure validation build based on upstream v0.42.3.

No Rust source changes or trace-export patch are included in this baseline.
Five native builds run Git/tracking tests and an isolated Git smoke before packaging.
`checksums.txt` contains SHA-256 hashes; `build-info.json` identifies the exact source commit and build targets.

This prerelease does not change the RTK version used by AIB automatically.
