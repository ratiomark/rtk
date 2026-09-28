# AIB runtime fork

Upstream baseline: `v0.42.3` (`de78d70aee86fe6b7b5c2462820a1b6c250d425b`).
Working branch: `codex/aib-runtime`; `origin` is `ratiomark/rtk`, `upstream` is `rtk-ai/rtk`.
Rust sources and Cargo dependencies are unchanged in the initial infrastructure setup.

## Local feedback

Run from `D:\dev\rtk`:

```powershell
# Focused Git and tracking unit tests; detailed logs stay in .tmp/checks.
./scripts/aib/check.ps1
# Also build, smoke and package the Windows release binary.
./scripts/aib/check.ps1 -Release
# Smoke any downloaded or locally built executable against a disposable Git repo.
python scripts/aib/runtime.py smoke <path-to-rtk.exe>
```

The smoke checks version/help, Git status/diff/log and three isolated tracking rows.
It disables telemetry and uses a temporary database; it does not mutate user repositories.
The local check script requires PowerShell 7, Rust 1.92.0 with MSVC build tools, Python and Git.

`aib.json` provides `@core`, `@git`, `@cmd`, `@stats`, `@ci`, `@tool`.
Use `aib qr`, `aib rg --`, `aib git --` for text/Git work; semantic TS inspection is not applicable to Rust.
The current repo-dev native launcher incorrectly reads agent-ide aliases for QR in this repo.
Until fixed, use the verified QR fallback:

```powershell
node D:/dev/agent-ide/packages/cli/dist/bin/aib.js qr @git/git.rs head=40
```

## GitHub feedback

Pushes affecting runtime sources, tests or our build scripts run the five-target matrix.
The matrix uses native Windows/Linux/macOS hosts, pinned Rust and `cargo --locked`.
Each target runs Git/tracking unit tests and release smoke, then uploads its archive for three days.
Other inherited upstream workflows are disabled in the fork's Actions settings.

```powershell
gh run list -R ratiomark/rtk --workflow aib-runtime.yml --limit 5
gh run view <run-id> -R ratiomark/rtk
gh run view <run-id> -R ratiomark/rtk --log-failed > .tmp/failed-run.log
# Explicit check-only run:
gh workflow run aib-runtime.yml -R ratiomark/rtk --ref codex/aib-runtime -f publish=false
# Explicit prerelease: choose a NEW tag; existing releases are not overwritten.
gh workflow run aib-runtime.yml -R ratiomark/rtk --ref codex/aib-runtime -f publish=true -f tag=v0.42.3-aib.1
```

After all builds pass, publication attaches five archives, `checksums.txt`, and `build-info.json`.
The release is a prerelease and is not marked latest. Publishing uses `GITHUB_TOKEN`; no custom secrets are needed.
Archive filenames and executable layout match AIB's existing upstream downloads.
Nothing automatically switches the AIB runtime to these binaries.

```powershell
gh release download v0.42.3-aib.1 -R ratiomark/rtk --dir .tmp/download/v0.42.3-aib.1
python scripts/aib/runtime.py verify .tmp/download/v0.42.3-aib.1
```

## Updating upstream

Fetch upstream tags, review the selected version, then merge/rebase deliberately.
Keep the Rust patch small and run the same five-target matrix before publishing a new version.
Update the baseline/version checks and release notes with each upstream upgrade.
Do not merge an upstream branch just to obtain a newer workflow or publish on every AIB change.
