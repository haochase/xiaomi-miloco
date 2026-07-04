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

function Add-GroupItem {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Groups,
        [Parameter(Mandatory = $true)]
        [string]$Group,
        [Parameter(Mandatory = $true)]
        [object]$Item
    )

    $Groups[$Group].Add($Item) | Out-Null
}

function Write-Group {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title,
        [System.Collections.ArrayList]$Items,
        [Parameter(Mandatory = $true)]
        [string]$Note
    )

    Write-Host ""
    Write-Host ("## {0}" -f $Title)
    Write-Host ("- intent: {0}" -f $Note)
    if ($Items.Count -eq 0) {
        Write-Host "- files: none currently reported by git status"
        return
    }

    Write-Host "- files:"
    foreach ($item in $Items) {
        Write-Host ("  - {0} {1}" -f $item.Status, $item.Path)
    }
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

$groups = @{
    "core-life-demo" = [System.Collections.ArrayList]::new()
    "review-and-recording-support" = [System.Collections.ArrayList]::new()
    "manual-decision-time-compute" = [System.Collections.ArrayList]::new()
    "local-runtime-only" = [System.Collections.ArrayList]::new()
    "unexpected-review-needed" = [System.Collections.ArrayList]::new()
}

$corePrefixes = @(
    ".gitignore",
    "backend\miloco\pyproject.toml",
    "backend\miloco\src\miloco\main.py",
    "backend\miloco\src\miloco\life\",
    "backend\miloco\tests\fixtures\life_mimo_mock.json",
    "backend\miloco\tests\test_life_",
    "cli\src\miloco_cli\commands\life.py",
    "cli\src\miloco_cli\main.py",
    "cli\tests\test_life_commands.py",
    "plugins\openclaw\tests\life-skill.test.ts",
    "plugins\skills\miloco-life-agent\"
)

$reviewPrefixes = @(
    "knowledge\04-testing\life-demo-evening-checklist.md",
    "knowledge\04-testing\life-demo-review-package.md",
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

$localRuntimePrefixes = @(
    ".miloco-smoke",
    ".pytest-tmp",
    ".pytest-tmp-live",
    ".ruff_cache",
    ".uv-cache"
)

foreach ($item in $items) {
    if ($item.Path -eq "cli\src\miloco_cli\commands\time_compute.py") {
        Add-GroupItem -Groups $groups -Group "manual-decision-time-compute" -Item $item
    }
    elseif (Test-PathPrefix -Path $item.Path -Prefixes $localRuntimePrefixes) {
        Add-GroupItem -Groups $groups -Group "local-runtime-only" -Item $item
    }
    elseif (Test-PathPrefix -Path $item.Path -Prefixes $corePrefixes) {
        Add-GroupItem -Groups $groups -Group "core-life-demo" -Item $item
    }
    elseif (Test-PathPrefix -Path $item.Path -Prefixes $reviewPrefixes) {
        Add-GroupItem -Groups $groups -Group "review-and-recording-support" -Item $item
    }
    else {
        Add-GroupItem -Groups $groups -Group "unexpected-review-needed" -Item $item
    }
}

Write-Host "# Life Demo Review Split Plan"
Write-Host ""
Write-Host "Source command: git status --short"
Write-Host "No commit, push, or PR is performed by this script."
Write-Host "Do not run git add from this output without a manual user review."
Write-Host ""
Write-Host "## Suggested staging groups"
Write-Host "- core-life-demo: schema, mock MiMo extraction, recommendation, repo/router/CLI/skill/tests."
Write-Host "- review-and-recording-support: smoke scripts, preflight, checklist, and recording order docs."
Write-Host "- manual-decision-time-compute: decide whether cli\src\miloco_cli\commands\time_compute.py belongs in this package."
Write-Host "- local-runtime-only: keep generated media, caches, SQLite proof DBs, private URLs, and real-device evidence out of git."

Write-Group -Title "core-life-demo" -Items $groups["core-life-demo"] -Note "candidate source package for the hackathon demo review"
Write-Group -Title "review-and-recording-support" -Items $groups["review-and-recording-support"] -Note "candidate support package for repeatable review, preflight, and recording order"
Write-Group -Title "manual-decision-time-compute" -Items $groups["manual-decision-time-compute"] -Note "hold until the user decides whether this unrelated CLI fallback is included or split out"
Write-Group -Title "local-runtime-only" -Items $groups["local-runtime-only"] -Note "do not stage; record evidence in MILOCO_HACKATHON_DEMO_PROGRESS.md when relevant"
Write-Group -Title "unexpected-review-needed" -Items $groups["unexpected-review-needed"] -Note "review manually before any staging decision"

Write-Host ""
Write-Host "Next: run scripts\preflight-life-demo-review.ps1, then compare this split with knowledge\04-testing\life-demo-review-package.md before staging anything."
