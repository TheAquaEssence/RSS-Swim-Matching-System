param(
    [string]$Python = "python",
    [switch]$SkipBackend,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$Desktop = Join-Path $RepoRoot "desktop"
$Backend = Join-Path $RepoRoot ".dist/pyinstaller/aqua-backend/aqua-backend.exe"

$started = Get-Date

if (-not $SkipBackend) {
    & (Join-Path $RepoRoot "packaging/pyinstaller/build_backend.ps1") -Python $Python
    if ($LASTEXITCODE -ne 0) { throw "Backend packaging failed with exit code $LASTEXITCODE" }
}
if (-not (Test-Path -LiteralPath $Backend)) {
    throw "Frozen backend is missing: $Backend"
}

Push-Location $Desktop
try {
    if (-not $SkipInstall) {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed with exit code $LASTEXITCODE" }
    }
    npm run test
    if ($LASTEXITCODE -ne 0) { throw "Desktop tests failed with exit code $LASTEXITCODE" }
    npm run check
    if ($LASTEXITCODE -ne 0) { throw "Desktop checks failed with exit code $LASTEXITCODE" }
    npm run pack:win
    if ($LASTEXITCODE -ne 0) { throw "Electron packaging failed with exit code $LASTEXITCODE" }
    npm run verify:package
    if ($LASTEXITCODE -ne 0) { throw "Packaged application verification failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}

$elapsed = (Get-Date) - $started
Write-Host "Electron output: $(Join-Path $RepoRoot '.dist/electron')"
Write-Host ("Build duration: {0:mm\:ss}" -f $elapsed)
