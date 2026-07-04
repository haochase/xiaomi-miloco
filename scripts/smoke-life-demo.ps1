param(
    [bool]$SkipLiveCli = $true,
    [string]$BackendUrl = "http://127.0.0.1:1810"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend\miloco"
$cliDir = Join-Path $repoRoot "cli"
$fixturePath = Join-Path $backendDir "tests\fixtures\life_mimo_mock.json"
$smokeHome = Join-Path $repoRoot ".miloco-smoke"
$smokeDb = Join-Path $smokeHome "life-demo.db"
$pytestTmp = Join-Path ([System.IO.Path]::GetTempPath()) ("miloco-life-smoke-pytest-" + [System.Guid]::NewGuid().ToString("N"))

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

if (-not $env:UV_CACHE_DIR) {
    $env:UV_CACHE_DIR = Join-Path $repoRoot ".uv-cache"
}
if (-not $env:MILOCO_HOME) {
    $env:MILOCO_HOME = $smokeHome
}
if (-not $env:TEMP) {
    $env:TEMP = $pytestTmp
}
if (-not $env:TMP) {
    $env:TMP = $pytestTmp
}

New-Item -ItemType Directory -Force -Path $env:UV_CACHE_DIR, $env:MILOCO_HOME, $pytestTmp | Out-Null

Write-Host "== Miloco life mock smoke =="
Write-Host "This smoke uses desensitized mock MiMo data and does not touch real photos, camera frames, API keys, or speakers."
& (Join-Path $PSScriptRoot "run-life-demo.ps1") -FixturePath $fixturePath

Write-Host ""
Write-Host "== Quick two-feature E2E smoke =="
Push-Location $backendDir
try {
    Invoke-NativeCommand -Label "Quick two-feature E2E smoke" -Command {
        uv run miloco-life-quick-e2e $fixturePath --db-path (Join-Path $smokeHome "quick-life-e2e.db")
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "== Backend life smoke tests =="
Push-Location $backendDir
try {
    Invoke-NativeCommand -Label "Backend life smoke tests" -Command {
        uv run pytest tests\test_life_demo_cli.py tests\test_life_demo_script.py tests\test_life_notify.py tests\test_life_quick_e2e.py tests\test_life_repo.py tests\test_life_router.py -q -p no:cacheprovider --basetemp $pytestTmp
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "== CLI life command tests =="
Push-Location $cliDir
try {
    Invoke-NativeCommand -Label "CLI life command tests" -Command {
        uv run pytest tests\test_life_commands.py -q -p no:cacheprovider --basetemp $pytestTmp
    }
}
finally {
    Pop-Location
}

if ($SkipLiveCli) {
    Write-Host ""
    Write-Host "== Live backend CLI smoke skipped =="
    Write-Host "Run with -SkipLiveCli:`$false after starting the backend to execute:"
    Write-Host "miloco-cli life history --db-path $smokeDb --domain cooking --pretty  # empty history check"
    Write-Host "miloco-cli life demo --fixture $fixturePath --persist --db-path $smokeDb --pretty"
    Write-Host "miloco-cli life history --db-path $smokeDb --source-id demo_afternoon_interview_dinner --pretty"
    Write-Host "miloco-cli life notify --domain cooking --urgency medium --requires-ack --message `"The water may be boiling; Please confirm before adding dumplings.`" --pretty"
    exit 0
}

$env:MILOCO_SERVER__URL = $BackendUrl

Write-Host ""
Write-Host "== Live backend CLI smoke =="
Push-Location $cliDir
try {
    Invoke-NativeCommand -Label "Live history empty check" -Command {
        uv run miloco-cli life history --db-path $smokeDb --domain cooking --pretty
    }
    Invoke-NativeCommand -Label "Live persistent demo" -Command {
        uv run miloco-cli life demo --fixture $fixturePath --persist --db-path $smokeDb --pretty
    }
    Invoke-NativeCommand -Label "Live persisted history check" -Command {
        uv run miloco-cli life history --db-path $smokeDb --source-id demo_afternoon_interview_dinner --pretty
    }
    Invoke-NativeCommand -Label "Live notify fallback" -Command {
        uv run miloco-cli life notify --domain cooking --urgency medium --requires-ack --message "The water may be boiling; Please confirm before adding dumplings." --pretty
    }
}
finally {
    Pop-Location
}
