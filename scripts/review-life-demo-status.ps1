param(
    [switch]$Markdown
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

function Convert-StatusLine {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Line
    )

    if ($Line.Length -lt 4) {
        return $null
    }

    $status = $Line.Substring(0, 2).Trim()
    $path = $Line.Substring(3).Trim()
    if ($path -like "* -> *") {
        $path = ($path -split " -> ", 2)[1]
    }

    [PSCustomObject]@{
        Status = $status
        Path = $path.Replace("/", "\")
    }
}

function Test-PathPrefix {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string[]]$Prefixes
    )

    foreach ($prefix in $Prefixes) {
        if ($Path -eq $prefix -or $Path.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

function Add-BucketItem {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Buckets,
        [Parameter(Mandatory = $true)]
        [string]$Bucket,
        [Parameter(Mandatory = $true)]
        [object]$Item
    )

    $Buckets[$Bucket].Add($Item) | Out-Null
}

Push-Location $repoRoot
try {
    $rawStatus = git status --short -- . ":(exclude).miloco-smoke/**" ":(exclude).pytest-tmp/**" ":(exclude).pytest-tmp-live/**" ":(exclude).ruff_cache/**" ":(exclude).uv-cache/**"
}
finally {
    Pop-Location
}

$items = @()
foreach ($line in $rawStatus) {
    $item = Convert-StatusLine -Line $line
    if ($null -ne $item) {
        $items += $item
    }
}

$buckets = @{
    "Upstream-ready code" = [System.Collections.ArrayList]::new()
    "Manual decision required" = [System.Collections.ArrayList]::new()
    "Do-not-commit paths" = [System.Collections.ArrayList]::new()
    "Runtime-only evidence" = [System.Collections.ArrayList]::new()
    "Other review items" = [System.Collections.ArrayList]::new()
}

$upstreamPrefixes = @(
    ".gitignore",
    "backend\miloco\pyproject.toml",
    "backend\miloco\src\miloco\main.py",
    "backend\miloco\src\miloco\life\",
    "backend\miloco\tests\fixtures\life_mimo_mock.json",
    "backend\miloco\tests\test_life_",
    "cli\src\miloco_cli\commands\life.py",
    "cli\src\miloco_cli\main.py",
    "cli\tests\test_life_commands.py",
    "knowledge\04-testing\life-demo-evening-checklist.md",
    "knowledge\04-testing\life-demo-review-package.md",
    "plugins\openclaw\tests\life-skill.test.ts",
    "plugins\skills\miloco-life-agent\",
    "scripts\run-life-demo.ps1",
    "scripts\smoke-life-demo.ps1",
    "scripts\test-life-tts-voice.ps1",
    "scripts\review-life-demo-status.ps1",
    "scripts\preflight-life-demo-review.ps1",
    "scripts\plan-life-demo-review-split.ps1",
    "scripts\export-life-demo-review-manifest.ps1",
    "scripts\prepare-life-demo-staging-checklist.ps1",
    "scripts\explain-life-demo-manual-decisions.ps1",
    "scripts\preview-life-demo-staging-commands.ps1",
    "scripts\test-life-demo-review-ready.ps1",
    "scripts\test-life-demo-secret-boundary.ps1",
    "scripts\export-life-demo-proof-bundle.ps1",
    "scripts\test-life-demo-final-staging.ps1",
    "scripts\test-life-demo-recording-ready.ps1"
)

$doNotCommitPrefixes = @(
    ".miloco-smoke",
    ".pytest-tmp",
    ".pytest-tmp-live",
    ".ruff_cache",
    ".uv-cache"
)

foreach ($item in $items) {
    if (Test-PathPrefix -Path $item.Path -Prefixes $doNotCommitPrefixes) {
        Add-BucketItem -Buckets $buckets -Bucket "Do-not-commit paths" -Item $item
    }
    elseif ($item.Path -eq "cli\src\miloco_cli\commands\time_compute.py") {
        Add-BucketItem -Buckets $buckets -Bucket "Manual decision required" -Item $item
    }
    elseif (Test-PathPrefix -Path $item.Path -Prefixes $upstreamPrefixes) {
        Add-BucketItem -Buckets $buckets -Bucket "Upstream-ready code" -Item $item
    }
    else {
        Add-BucketItem -Buckets $buckets -Bucket "Other review items" -Item $item
    }
}

$localHelperNotes = @(
    "E:\new_job\MilocoDev\run-live-demo.ps1",
    "E:\new_job\MilocoDev\pc-speaker-server.ps1"
)

Write-Host "# Life Demo Review Status"
Write-Host ""
Write-Host "Source command: git status --short"
Write-Host "No commit, push, or PR is performed by this script."
Write-Host ""
Write-Host "## Upstream-ready code"
if ($buckets["Upstream-ready code"].Count -eq 0) {
    Write-Host "- none currently reported by git status"
}
else {
    foreach ($item in $buckets["Upstream-ready code"]) {
        Write-Host ("- {0} {1}" -f $item.Status, $item.Path)
    }
}

Write-Host ""
Write-Host "## Manual decision required"
if ($buckets["Manual decision required"].Count -eq 0) {
    Write-Host "- none"
}
else {
    foreach ($item in $buckets["Manual decision required"]) {
        Write-Host ("- {0} {1} (decide whether it belongs with the life demo package or should be split out)" -f $item.Status, $item.Path)
    }
}

Write-Host ""
Write-Host "## Local helper scripts"
foreach ($note in $localHelperNotes) {
    $exists = Test-Path -LiteralPath $note
    Write-Host ("- {0} ({1})" -f $note, $(if ($exists) { "exists outside official clone" } else { "not found in this checkout" }))
}

Write-Host ""
Write-Host "## Runtime-only evidence"
Write-Host "- Ubuntu service 1810, sidecar 1811, camera clips, MiMo raw outputs, generated WAV files, SQLite proof DBs, and private LAN URLs are evidence/setup only."
Write-Host "- Record exact verified commands in MILOCO_HACKATHON_DEMO_PROGRESS.md instead of committing runtime artifacts."

Write-Host ""
Write-Host "## Do-not-commit paths"
if ($buckets["Do-not-commit paths"].Count -eq 0) {
    Write-Host "- none currently reported by git status"
}
else {
    foreach ($item in $buckets["Do-not-commit paths"]) {
        Write-Host ("- {0} {1}" -f $item.Status, $item.Path)
    }
}
foreach ($path in $doNotCommitPrefixes) {
    $localPath = Join-Path $repoRoot $path
    if (Test-Path -LiteralPath $localPath) {
        Write-Host ("- known local path exists: {0}" -f $path)
    }
}

Write-Host ""
Write-Host "## Other review items"
if ($buckets["Other review items"].Count -eq 0) {
    Write-Host "- none"
}
else {
    foreach ($item in $buckets["Other review items"]) {
        Write-Host ("- {0} {1}" -f $item.Status, $item.Path)
    }
}

Write-Host ""
Write-Host "Next: compare this status with knowledge/04-testing/life-demo-review-package.md before staging anything."
