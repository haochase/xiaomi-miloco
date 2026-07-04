param(
    [string]$FixturePath = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend\miloco"
if (-not $FixturePath) {
    $FixturePath = Join-Path $backendDir "tests\fixtures\life_mimo_mock.json"
}
if (-not $env:UV_CACHE_DIR) {
    $env:UV_CACHE_DIR = Join-Path $repoRoot ".uv-cache"
}

Push-Location $backendDir
try {
    uv run miloco-life-demo $FixturePath
}
finally {
    Pop-Location
}
