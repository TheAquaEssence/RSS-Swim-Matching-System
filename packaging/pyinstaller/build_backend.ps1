param(
    [string]$Python = "python",
    [string]$DistPath = ".dist/pyinstaller",
    [string]$WorkPath = ".dist/pyinstaller-work"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$Spec = Join-Path $PSScriptRoot "aqua-backend.spec"
$ResolvedDist = Join-Path $RepoRoot $DistPath
$ResolvedWork = Join-Path $RepoRoot $WorkPath
$ReleaseMetadata = Join-Path $RepoRoot ".dist/pyinstaller-release-metadata"

& $Python (Join-Path $PSScriptRoot "generate_release_metadata.py") --output $ReleaseMetadata
if ($LASTEXITCODE -ne 0) {
    throw "Release metadata generation failed with exit code $LASTEXITCODE"
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $ResolvedDist `
    --workpath $ResolvedWork `
    $Spec

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

Write-Host "Backend package: $(Join-Path $ResolvedDist 'aqua-backend')"
