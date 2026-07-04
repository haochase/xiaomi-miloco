param(
    [switch]$FailOnWarning
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$manifestScript = Join-Path $PSScriptRoot "export-life-demo-review-manifest.ps1"

function Get-GroupItems {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Groups,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $items = $Groups.$Name
    if ($null -eq $items) {
        return @()
    }
    return @($items)
}

function Write-PathList {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Paths
    )

    Write-Host ("- {0}: {1}" -f $Label, $Paths.Count)
    foreach ($path in $Paths) {
        Write-Host ("  - {0}" -f $path)
    }
}

Write-Host "# Secret boundary audit"
Write-Host ""
Write-Host "No commit, push, or PR is performed by this script."
Write-Host "Scope: checks review metadata and known local artifact paths only; it does not scan source text for documented examples."

$manifestJson = & $manifestScript
if ($LASTEXITCODE -ne 0) {
    throw "export-life-demo-review-manifest.ps1 failed with exit code $LASTEXITCODE"
}

$manifest = $manifestJson | ConvertFrom-Json
$groups = $manifest.groups

$runtimeOnly = @(Get-GroupItems -Groups $groups -Name "local-runtime-only")
$unexpected = @(Get-GroupItems -Groups $groups -Name "unexpected-review-needed")

$generatedMediaPatterns = @("*.wav", "*.mp4", "*.mov", "*.m4a", "*.png", "*.jpg", "*.jpeg")
$sqlitePatterns = @("*.db", "*.sqlite", "*.sqlite3")
$runtimeDirs = @(".miloco-smoke", ".pytest-tmp", ".pytest-tmp-live", ".ruff_cache", ".uv-cache")

$existingRuntimeDirs = @()
foreach ($dir in $runtimeDirs) {
    if (Test-Path -LiteralPath (Join-Path $repoRoot $dir)) {
        $existingRuntimeDirs += $dir
    }
}

function Convert-ToRepoRelativePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FullName
    )

    return $FullName.Substring($repoRoot.Length + 1)
}

function Find-RuntimeFiles {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Patterns
    )

    $paths = @()
    foreach ($dir in @(".miloco-smoke", ".pytest-tmp", ".pytest-tmp-live")) {
        $root = Join-Path $repoRoot $dir
        if (-not (Test-Path -LiteralPath $root)) {
            continue
        }
        foreach ($pattern in $Patterns) {
            $paths += @(
                Get-ChildItem -Path $root -Filter $pattern -File -Recurse -ErrorAction SilentlyContinue |
                    ForEach-Object { Convert-ToRepoRelativePath -FullName $_.FullName }
            )
        }
    }
    return $paths
}

$localGeneratedMedia = @(Find-RuntimeFiles -Patterns $generatedMediaPatterns)
$localSQLiteFiles = @(Find-RuntimeFiles -Patterns $sqlitePatterns)

Write-Host ""
Write-Host "## Boundary rules"
Write-Host "- Keep MIMO_TTS_API_KEY, Xiaomi account state, private LAN URLs, real household data, raw MiMo responses, generated media, and SQLite proof DBs out of git."
Write-Host "- Expected do_not_commit_patterns from manifest:"
foreach ($pattern in @($manifest.do_not_commit_patterns)) {
    Write-Host ("  - {0}" -f $pattern)
}

Write-Host ""
Write-Host "## Current local artifacts"
Write-PathList -Label "runtime-only paths from manifest" -Paths @($runtimeOnly | ForEach-Object { $_.path })
Write-PathList -Label "existing runtime directories" -Paths $existingRuntimeDirs
Write-PathList -Label "generated media under runtime dirs" -Paths $localGeneratedMedia
Write-PathList -Label "SQLite proof DBs under runtime dirs" -Paths $localSQLiteFiles
Write-PathList -Label "unexpected-review-needed paths" -Paths @($unexpected | ForEach-Object { $_.path })

$warnings = [System.Collections.ArrayList]::new()
if ($unexpected.Count -gt 0) {
    $warnings.Add("unexpected-review-needed is not empty; inspect paths before staging.") | Out-Null
}
if ($runtimeOnly.Count -gt 0) {
    $warnings.Add("local-runtime-only is visible in git status; keep those paths unstaged.") | Out-Null
}
if ($localGeneratedMedia.Count -gt 0) {
    $warnings.Add("generated media exists under runtime dirs; keep it unstaged and out of review packages.") | Out-Null
}
if ($localSQLiteFiles.Count -gt 0) {
    $warnings.Add("SQLite proof DBs exist under runtime dirs; keep them unstaged and out of review packages.") | Out-Null
}

Write-Host ""
Write-Host "## Audit result"
if ($warnings.Count -eq 0) {
    Write-Host "- no private artifact boundary warnings from manifest/runtime paths"
    exit 0
}

foreach ($warning in $warnings) {
    Write-Host ("- warning: {0}" -f $warning)
}

if ($FailOnWarning) {
    exit 1
}

Write-Host "- default mode reports warnings without failing; use -FailOnWarning before final staging if desired"
