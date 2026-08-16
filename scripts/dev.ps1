$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "Install uv first: https://docs.astral.sh/uv/getting-started/installation/"
}

& uv run --script (Join-Path $root "scripts/run_local.py") @args
exit $LASTEXITCODE
