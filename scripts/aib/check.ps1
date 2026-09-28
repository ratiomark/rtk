param([switch]$Release)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$logRoot = Join-Path $repoRoot '.tmp/checks'
New-Item -ItemType Directory -Force $logRoot | Out-Null

function Invoke-Check([string]$Name, [string]$Executable, [string[]]$Arguments) {
    $log = Join-Path $logRoot "$Name.log"
    & $Executable @Arguments > $log 2>&1
    if ($LASTEXITCODE -ne 0) {
        Get-Content -LiteralPath $log -Tail 15 | ForEach-Object {
            $_.Substring(0, [Math]::Min($_.Length, 400))
        }
        throw "$Name failed; full log: $log"
    }
    Write-Host "PASS $Name; log: $log"
}

$oldDatabase = $env:RTK_DB_PATH
$oldTelemetry = $env:RTK_TELEMETRY_DISABLED
Push-Location $repoRoot
try {
    $env:RTK_DB_PATH = Join-Path $logRoot 'history.db'
    $env:RTK_TELEMETRY_DISABLED = '1'
    Invoke-Check 'artifact-tests' 'python' @('-m', 'unittest', 'discover', '-s', 'scripts/aib', '-p', 'test_runtime.py')
    Invoke-Check 'git-tests' 'cargo' @('test', '--locked', '--bin', 'rtk', 'cmds::git::git::tests', '--', '--test-threads=1')
    Invoke-Check 'tracking-tests' 'cargo' @('test', '--locked', '--bin', 'rtk', 'core::tracking::tests', '--', '--test-threads=1')
    if ($Release) {
        Invoke-Check 'release-build' 'cargo' @('build', '--locked', '--release', '--target', 'x86_64-pc-windows-msvc')
        Invoke-Check 'release-smoke' 'python' @('scripts/aib/runtime.py', 'package', '--target', 'x86_64-pc-windows-msvc')
    }
} finally {
    $env:RTK_DB_PATH = $oldDatabase
    $env:RTK_TELEMETRY_DISABLED = $oldTelemetry
    Pop-Location
}
