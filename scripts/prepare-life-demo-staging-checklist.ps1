param(
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$manifestScript = Join-Path $PSScriptRoot "export-life-demo-review-manifest.ps1"

function Format-ChecklistGroup {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]]$Items,
        [Parameter(Mandatory = $true)]
        [string]$Action
    )

    $lines = [System.Collections.ArrayList]::new()
    $lines.Add("") | Out-Null
    $lines.Add(("## {0}" -f $Title)) | Out-Null
    $lines.Add(("- action: {0}" -f $Action)) | Out-Null

    if ($Items.Count -eq 0) {
        $lines.Add("- files: none currently reported by git status") | Out-Null
        return $lines
    }

    $lines.Add("- files:") | Out-Null
    foreach ($item in $Items) {
        $lines.Add(("  - [ ] {0} {1}" -f $item.status, $item.path)) | Out-Null
    }
    return $lines
}

$manifestJson = & $manifestScript
if ($LASTEXITCODE -ne 0) {
    throw "export-life-demo-review-manifest.ps1 failed with exit code $LASTEXITCODE"
}

$manifest = $manifestJson | ConvertFrom-Json
$groups = $manifest.groups
$lines = [System.Collections.ArrayList]::new()

$lines.Add("# Manual staging checklist") | Out-Null
$lines.Add("") | Out-Null
$lines.Add(("Repo: {0}" -f $repoRoot)) | Out-Null
$lines.Add(("Generated from: {0}" -f $manifest.source_command)) | Out-Null
$lines.Add("No git add is executed by this script.") | Out-Null
$lines.Add("Do not commit, push, or open a PR until the user manually reviews this checklist.") | Out-Null
$lines.Add("") | Out-Null
$lines.Add("## Review order") | Out-Null
$lines.Add("- [ ] Resolve unexpected-review-needed; it should be empty before staging.") | Out-Null
$lines.Add("- [ ] Decide whether cli\src\miloco_cli\commands\time_compute.py belongs in the package.") | Out-Null
$lines.Add("- [ ] Review core-life-demo source and tests.") | Out-Null
$lines.Add("- [ ] Review review-and-recording-support scripts and docs.") | Out-Null
$lines.Add("- [ ] Keep local-runtime-only and do-not-commit patterns out of git.") | Out-Null
$lines.Add("- [ ] Run scripts\preflight-life-demo-review.ps1 before any manual staging.") | Out-Null

$lines.AddRange((Format-ChecklistGroup -Title "unexpected-review-needed" -Items @($groups."unexpected-review-needed") -Action "review manually first; do not stage until explained")) | Out-Null
$lines.AddRange((Format-ChecklistGroup -Title "manual-decision-time-compute" -Items @($groups."manual-decision-time-compute") -Action "hold until user decides whether time_compute.py is included or split out")) | Out-Null
$lines.AddRange((Format-ChecklistGroup -Title "core-life-demo" -Items @($groups."core-life-demo") -Action "candidate source package after review")) | Out-Null
$lines.AddRange((Format-ChecklistGroup -Title "review-and-recording-support" -Items @($groups."review-and-recording-support") -Action "candidate support package after review")) | Out-Null
$lines.AddRange((Format-ChecklistGroup -Title "local-runtime-only" -Items @($groups."local-runtime-only") -Action "do not stage; summarize evidence in progress notes only")) | Out-Null

$lines.Add("") | Out-Null
$lines.Add("## verification_commands") | Out-Null
foreach ($command in $manifest.verification_commands) {
    $lines.Add(("- [ ] {0}" -f $command)) | Out-Null
}

$lines.Add("") | Out-Null
$lines.Add("## Do-not-commit patterns") | Out-Null
foreach ($pattern in $manifest.do_not_commit_patterns) {
    $lines.Add(("- {0}" -f $pattern)) | Out-Null
}

$output = $lines -join [Environment]::NewLine

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
    Set-Content -LiteralPath $resolvedOutputPath -Value $output -Encoding UTF8
    Write-Host ("Wrote manual staging checklist: {0}" -f $resolvedOutputPath)
}
else {
    Write-Output $output
}
