param(
    [string]$OutputPath,
    [switch]$Json
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

function Format-GroupSummary {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]]$Items
    )

    $lines = [System.Collections.ArrayList]::new()
    $lines.Add(("- {0}: {1}" -f $Name, $Items.Count)) | Out-Null
    foreach ($item in $Items) {
        $lines.Add(("  - {0} {1}" -f $item.status, $item.path)) | Out-Null
    }
    return $lines
}

function ConvertTo-Markdown {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Bundle
    )

    $lines = [System.Collections.ArrayList]::new()
    $lines.Add("# Life Demo Proof Bundle") | Out-Null
    $lines.Add("") | Out-Null
    $lines.Add(("Repo: {0}" -f $Bundle.repo_root)) | Out-Null
    $lines.Add(("Generated at: {0}" -f $Bundle.generated_at)) | Out-Null
    $lines.Add("No git add is executed by this script.") | Out-Null
    $lines.Add("Do not commit, push, or open a PR until the user manually reviews this proof bundle.") | Out-Null

    $lines.Add("") | Out-Null
    $lines.Add("## readiness_summary") | Out-Null
    foreach ($line in $Bundle.readiness_summary.lines) {
        $lines.Add($line) | Out-Null
    }
    foreach ($warning in $Bundle.readiness_summary.warnings) {
        $lines.Add(("- warning: {0}" -f $warning)) | Out-Null
    }

    $lines.Add("") | Out-Null
    $lines.Add("## secret_boundary_summary") | Out-Null
    foreach ($line in $Bundle.secret_boundary_summary.lines) {
        $lines.Add($line) | Out-Null
    }
    foreach ($warning in $Bundle.secret_boundary_summary.warnings) {
        $lines.Add(("- warning: {0}" -f $warning)) | Out-Null
    }

    $lines.Add("") | Out-Null
    $lines.Add("## recording_order") | Out-Null
    foreach ($step in $Bundle.recording_order) {
        $lines.Add(("- [ ] {0}" -f $step)) | Out-Null
    }

    $lines.Add("") | Out-Null
    $lines.Add("## verification_commands") | Out-Null
    foreach ($command in $Bundle.verification_commands) {
        $lines.Add(("- [ ] {0}" -f $command)) | Out-Null
    }

    $lines.Add("") | Out-Null
    $lines.Add("## manual_decisions") | Out-Null
    foreach ($decision in $Bundle.manual_decisions) {
        $lines.Add(("- [ ] {0}" -f $decision)) | Out-Null
    }

    $lines.Add("") | Out-Null
    $lines.Add("## do_not_commit_patterns") | Out-Null
    foreach ($pattern in $Bundle.do_not_commit_patterns) {
        $lines.Add(("- {0}" -f $pattern)) | Out-Null
    }

    return $lines -join [Environment]::NewLine
}

$manifestJson = & $manifestScript
if ($LASTEXITCODE -ne 0) {
    throw "export-life-demo-review-manifest.ps1 failed with exit code $LASTEXITCODE"
}

$manifest = $manifestJson | ConvertFrom-Json
$groups = $manifest.groups

$unexpected = @(Get-GroupItems -Groups $groups -Name "unexpected-review-needed")
$manual = @(Get-GroupItems -Groups $groups -Name "manual-decision-time-compute")
$core = @(Get-GroupItems -Groups $groups -Name "core-life-demo")
$support = @(Get-GroupItems -Groups $groups -Name "review-and-recording-support")
$runtimeOnly = @(Get-GroupItems -Groups $groups -Name "local-runtime-only")

$readinessLines = [System.Collections.ArrayList]::new()
foreach ($line in @(Format-GroupSummary -Name "unexpected-review-needed" -Items $unexpected)) {
    $readinessLines.Add($line) | Out-Null
}
foreach ($line in @(Format-GroupSummary -Name "manual-decision-time-compute" -Items $manual)) {
    $readinessLines.Add($line) | Out-Null
}
foreach ($line in @(Format-GroupSummary -Name "core-life-demo" -Items $core)) {
    $readinessLines.Add($line) | Out-Null
}
foreach ($line in @(Format-GroupSummary -Name "review-and-recording-support" -Items $support)) {
    $readinessLines.Add($line) | Out-Null
}
foreach ($line in @(Format-GroupSummary -Name "local-runtime-only" -Items $runtimeOnly)) {
    $readinessLines.Add($line) | Out-Null
}

$readinessWarnings = [System.Collections.ArrayList]::new()
if ($unexpected.Count -gt 0) {
    $readinessWarnings.Add("unexpected-review-needed is not empty; inspect these paths before staging.") | Out-Null
}
if ($manual.Count -gt 0) {
    $readinessWarnings.Add("time_compute.py remains a manual decision before final staging.") | Out-Null
}
if ($core.Count -eq 0) {
    $readinessWarnings.Add("core-life-demo is empty; there is no source package to review.") | Out-Null
}
if ($support.Count -eq 0) {
    $readinessWarnings.Add("review-and-recording-support is empty; helper scripts and docs are not visible.") | Out-Null
}

$secretBoundaryWarnings = [System.Collections.ArrayList]::new()
if ($runtimeOnly.Count -gt 0) {
    $secretBoundaryWarnings.Add("local-runtime-only items are visible in git status; keep them unstaged.") | Out-Null
}
$secretBoundaryWarnings.Add("Keep MIMO_TTS_API_KEY, private LAN URLs, real household data, raw MiMo responses, generated media, and SQLite proof DBs out of git.") | Out-Null

$bundle = [ordered]@{
    bundle_version = 1
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    repo_root = $repoRoot
    source_manifest_version = $manifest.manifest_version
    source_command = $manifest.source_command
    safety_boundary = "No git add is executed by this script. Do not commit, push, or open a PR until user review."
    readiness_summary = [ordered]@{
        lines = @($readinessLines)
        warnings = @($readinessWarnings)
    }
    secret_boundary_summary = [ordered]@{
        lines = @(
            "private inputs must stay out of git",
            "MIMO_TTS_API_KEY and private LAN URLs are runtime-only",
            "real household data, generated media, and SQLite proof DBs are local evidence only"
        )
        warnings = @($secretBoundaryWarnings)
    }
    recording_order = @(
        "Run scripts\preflight-life-demo-review.ps1 and keep live backend CLI skipped unless the backend is already running.",
        "Run scripts\smoke-life-demo.ps1 for the mock MiMo baseline.",
        "Run scripts\test-life-tts-voice.ps1 -DryRun to show the MiMo TTS request shape without secrets.",
        "Only after manual approval, run E:\new_job\MilocoDev\run-live-demo.ps1 -Speak with real camera/audio.",
        "For cooking scenes, verify spoken text uses may, possible, or please confirm wording.",
        "Record whether evidence came from mock data, real MiMo, real camera, or real audio in MILOCO_HACKATHON_DEMO_PROGRESS.md."
    )
    verification_commands = @($manifest.verification_commands)
    manual_decisions = @($manifest.manual_decisions)
    do_not_commit_patterns = @($manifest.do_not_commit_patterns)
    review_groups = $manifest.groups
}

$output = if ($Json) {
    $bundle | ConvertTo-Json -Depth 10
}
else {
    ConvertTo-Markdown -Bundle $bundle
}

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
    Write-Host ("Wrote life demo proof bundle: {0}" -f $resolvedOutputPath)
}
else {
    Write-Output $output
}
