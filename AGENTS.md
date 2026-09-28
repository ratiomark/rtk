# RTK fork for AIB

This checkout is the RTK fork at `ratiomark/rtk`; `rtk-ai/rtk` is upstream.
Read [scripts/aib/README.md](scripts/aib/README.md) for the pinned baseline,
build/release commands, and current local tooling caveats.

- Respond in Russian when working with this repository's owner.
- Keep upstream Rust changes small and separate from build infrastructure.
- Use `aib help` and `aib config aliases` when entering this checkout.
- Use `aib qr` for focused text reads, `aib rg --` for search, and `aib git --` for Git.
- Aliases are in `aib.json`; the README describes the verified QR fallback for the current native launcher.
- Rust is not TS/JS: use text reads/search, not TypeScript semantic inspect or mutations.
- On Windows, run `./scripts/aib/check.ps1` for focused Git/tracking/artifact checks.
- Add `-Release` to build and smoke the Windows archive. Logs stay in `.tmp/checks`.
- Do not run local Cargo builds/tests concurrently against the same target directory.
- Use `origin` for pushes and `upstream` for fetching upstream changes.
- GitHub builds all five platforms. Release publication requires explicit workflow dispatch;
  ordinary pushes only validate. See the README for exact commands.
- Preserve Cargo.lock and use `--locked`; update dependencies only for an intended dependency change.
