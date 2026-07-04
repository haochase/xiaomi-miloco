param(
    [string]$OutputPath
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
        status = $status
        path = $path.Replace("/", "\")
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
    if ($item.path -eq "cli\src\miloco_cli\commands\time_compute.py") {
        Add-GroupItem -Groups $groups -Group "manual-decision-time-compute" -Item $item
    }
    elseif (Test-PathPrefix -Path $item.path -Prefixes $localRuntimePrefixes) {
        Add-GroupItem -Groups $groups -Group "local-runtime-only" -Item $item
    }
    elseif (Test-PathPrefix -Path $item.path -Prefixes $corePrefixes) {
        Add-GroupItem -Groups $groups -Group "core-life-demo" -Item $item
    }
    elseif (Test-PathPrefix -Path $item.path -Prefixes $reviewPrefixes) {
        Add-GroupItem -Groups $groups -Group "review-and-recording-support" -Item $item
    }
    else {
        Add-GroupItem -Groups $groups -Group "unexpected-review-needed" -Item $item
    }
}

$manifest = [ordered]@{
    manifest_version = 1
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    repo_root = $repoRoot
    source_command = "git status --short"
    safety_boundary = "No commit, push, or PR is performed by this script."
    groups = [ordered]@{
        "core-life-demo" = @($groups["core-life-demo"])
        "review-and-recording-support" = @($groups["review-and-recording-support"])
        "manual-decision-time-compute" = @($groups["manual-decision-time-compute"])
        "local-runtime-only" = @($groups["local-runtime-only"])
        "unexpected-review-needed" = @($groups["unexpected-review-needed"])
    }
    manual_decisions = @(
        "Decide whether cli\src\miloco_cli\commands\time_compute.py belongs in the life demo package or should be split out.",
        "Keep generated media, local SQLite proof DBs, caches, private LAN URLs, API keys, and real household data out of git.",
        "Keep 1810 official service and 1811 life sidecar claims separate in review notes."
    )
    verification_commands = @(
        "scripts\preflight-life-demo-review.ps1",
        "scripts\test-life-demo-review-ready.ps1",
        "scripts\prepare-life-demo-staging-checklist.ps1",
        "scripts\explain-life-demo-manual-decisions.ps1",
        "scripts\preview-life-demo-staging-commands.ps1",
        "scripts\test-life-demo-secret-boundary.ps1",
        "scripts\export-life-demo-proof-bundle.ps1",
        "scripts\test-life-demo-final-staging.ps1",
        "scripts\test-life-demo-recording-ready.ps1",
        "scripts\smoke-life-demo.ps1",
        "powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\test-life-tts-voice.ps1 -DryRun",
        "git diff --check"
    )
    do_not_commit_patterns = @(
        ".miloco-smoke/",
        ".pytest-tmp/",
        ".pytest-tmp-live/",
        ".ruff_cache/",
        ".uv-cache/",
        "*.wav",
        "*.mp4",
        "*.db",
        "*.sqlite",
        "*.sqlite3"
    )
    next_steps = @(
        "Review unexpected-review-needed first; it should be empty before staging.",
        "Review manual-decision-time-compute before staging any CLI files.",
        "Run scripts\preflight-life-demo-review.ps1 before any commit preparation."
    )
}

$json = $manifest | ConvertTo-Json -Depth 8

if ($OutputPath) {
    $resolvedOutputPath = if ([System.IO.Path]::IsPathRooted($OutputPath)) {
        $OutputPath
    }
    else {
        Join-Path $repoRoot $OutputPath
    }
    $outputDir = Split-Path -Parent $resolvedOutputPath
    if ($outputDir -and -not (Test-Path -LiteralPath $outputDir)) {
        New-Item -ItemType Directory -Path $outputDir | Out-Null
    }
    Set-Content -LiteralPath $resolvedOutputPath -Value $json -Encoding UTF8
    Write-Host ("Wrote life demo review manifest: {0}" -f $resolvedOutputPath)
}
else {
    Write-Output $json
}
