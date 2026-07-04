param(
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

function New-Decision {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Id,
        [Parameter(Mandatory = $true)]
        [string]$Title,
        [Parameter(Mandatory = $true)]
        [string]$CurrentState,
        [Parameter(Mandatory = $true)]
        [string[]]$RecommendedChoice,
        [Parameter(Mandatory = $true)]
        [string[]]$AlternativeChoice,
        [Parameter(Mandatory = $true)]
        [string[]]$NextCommands
    )

    [ordered]@{
        id = $Id
        title = $Title
        current_state = $CurrentState
        recommended_choice = $RecommendedChoice
        alternative_choice = $AlternativeChoice
        next_commands = $NextCommands
    }
}

function Write-Decision {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Decision
    )

    Write-Host ""
    Write-Host ("## {0}" -f $Decision.title)
    Write-Host ("- id: {0}" -f $Decision.id)
    Write-Host ("- current_state: {0}" -f $Decision.current_state)
    Write-Host "- recommended_choice:"
    foreach ($line in $Decision.recommended_choice) {
        Write-Host ("  - {0}" -f $line)
    }
    Write-Host "- alternative_choice:"
    foreach ($line in $Decision.alternative_choice) {
        Write-Host ("  - {0}" -f $line)
    }
    Write-Host "- next_commands:"
    foreach ($line in $Decision.next_commands) {
        Write-Host ("  - {0}" -f $line)
    }
}

$manifestJson = & $manifestScript
if ($LASTEXITCODE -ne 0) {
    throw "export-life-demo-review-manifest.ps1 failed with exit code $LASTEXITCODE"
}
$manifest = $manifestJson | ConvertFrom-Json
$groups = $manifest.groups

$core = @(Get-GroupItems -Groups $groups -Name "core-life-demo")
$support = @(Get-GroupItems -Groups $groups -Name "review-and-recording-support")
$manual = @(Get-GroupItems -Groups $groups -Name "manual-decision-time-compute")
$runtime = @(Get-GroupItems -Groups $groups -Name "local-runtime-only")
$unexpected = @(Get-GroupItems -Groups $groups -Name "unexpected-review-needed")

$runtimeDirs = @(".miloco-smoke", ".pytest-tmp", ".pytest-tmp-live")
$existingRuntimeDirs = @()
foreach ($dir in $runtimeDirs) {
    $fullPath = Join-Path $repoRoot $dir
    if (Test-Path -LiteralPath $fullPath) {
        $existingRuntimeDirs += $dir
    }
}

$localRunLiveDemo = "E:\new_job\MilocoDev\run-live-demo.ps1"
$localPcSpeaker = "E:\new_job\MilocoDev\pc-speaker-server.ps1"
$hasTtsKey = -not [string]::IsNullOrWhiteSpace($env:MIMO_TTS_API_KEY)

$decisions = @(
    New-Decision `
        -Id "time_compute_cli_scope" `
        -Title "time_compute.py package scope" `
        -CurrentState ("manual-decision-time-compute={0}; cli\src\miloco_cli\commands\time_compute.py remains outside core-life-demo by default" -f $manual.Count) `
        -RecommendedChoice @(
            "Keep time_compute.py out of the life demo staging preview unless the user explicitly accepts it.",
            "Review the file separately because it is not required for schema, mock MiMo, recommendation, fixture, CLI life, router, notify, or recording flow."
        ) `
        -AlternativeChoice @(
            "If the user confirms it belongs in this package, rerun the Staging command preview with -IncludeManualDecision.",
            "Then rerun the Final staging gate with -Strict after private-artifact warnings are resolved or accepted as out-of-git evidence."
        ) `
        -NextCommands @(
            "scripts\preview-life-demo-staging-commands.ps1",
            "scripts\preview-life-demo-staging-commands.ps1 -IncludeReviewSupport",
            "scripts\preview-life-demo-staging-commands.ps1 -IncludeReviewSupport -IncludeManualDecision"
        )
    New-Decision `
        -Id "review_support_scope" `
        -Title "Review support scripts" `
        -CurrentState ("review-and-recording-support={0}; core-life-demo={1}; unexpected-review-needed={2}" -f $support.Count, $core.Count, $unexpected.Count) `
        -RecommendedChoice @(
            "Review support scripts and docs as a second staging group after core-life-demo.",
            "Keep them if the reviewer wants repeatable smoke, proof bundle, readiness, secret boundary, staging preview, and recording readiness checks."
        ) `
        -AlternativeChoice @(
            "If the reviewer wants only source capability, stage core-life-demo first and leave review-and-recording-support for a follow-up package.",
            "Do not remove the support files before recording; they are the current verification map."
        ) `
        -NextCommands @(
            "scripts\plan-life-demo-review-split.ps1",
            "scripts\prepare-life-demo-staging-checklist.ps1",
            "scripts\preview-life-demo-staging-commands.ps1 -IncludeReviewSupport"
        )
    New-Decision `
        -Id "private_runtime_evidence" `
        -Title "Private runtime evidence boundary" `
        -CurrentState ("local-runtime-only={0}; known runtime dirs={1}; runtime SQLite proof DBs must stay out of git" -f $runtime.Count, (($existingRuntimeDirs -join ", ") -replace "^$", "none")) `
        -RecommendedChoice @(
            "Keep generated media, caches, raw MiMo responses, private LAN URLs, API keys, real household data, and runtime SQLite proof DBs out of git.",
            "Record exact commands and proof summaries in MILOCO_HACKATHON_DEMO_PROGRESS.md instead of staging local artifacts."
        ) `
        -AlternativeChoice @(
            "If a proof snapshot is needed, write it under .miloco-smoke and treat it as local-only evidence.",
            "Use Secret boundary audit -FailOnWarning only after local proof DBs and generated media are cleaned or accepted as not staged."
        ) `
        -NextCommands @(
            "scripts\test-life-demo-secret-boundary.ps1",
            "scripts\test-life-demo-secret-boundary.ps1 -FailOnWarning",
            "scripts\export-life-demo-proof-bundle.ps1 -OutputPath .miloco-smoke\life-demo-proof-bundle.md"
        )
    New-Decision `
        -Id "runtime_claims_and_recording" `
        -Title "1810/1811 and recording prerequisites" `
        -CurrentState ("1810 remains the official service claim; 1811 remains the life sidecar claim; MIMO_TTS_API_KEY set={0}; run-live-demo helper exists={1}; pc-speaker helper exists={2}" -f $hasTtsKey, (Test-Path -LiteralPath $localRunLiveDemo), (Test-Path -LiteralPath $localPcSpeaker)) `
        -RecommendedChoice @(
            "Keep 1810 official service and 1811 life sidecar evidence separate in review notes.",
            "Run recording readiness strict only before a real after-hours recording pass with helpers and MIMO_TTS_API_KEY available."
        ) `
        -AlternativeChoice @(
            "If no real data is available, stay on mock smoke and TTS dry-run output.",
            "Do not claim real MiMo, real camera, pc_speaker, ESP32, or Xiaomi speaker proof unless the exact path was rerun."
        ) `
        -NextCommands @(
            "scripts\test-life-demo-recording-ready.ps1",
            "scripts\test-life-demo-recording-ready.ps1 -RequireLiveHelpers -Strict",
            "scripts\test-life-tts-voice.ps1 -DryRun"
        )
)

$report = [ordered]@{
    report_version = 1
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    repo_root = $repoRoot
    safety_boundary = "No git add is executed. Do not commit, push, or open a PR until the user manually reviews these choices."
    manifest_summary = [ordered]@{
        "core-life-demo" = $core.Count
        "review-and-recording-support" = $support.Count
        "manual-decision-time-compute" = $manual.Count
        "local-runtime-only" = $runtime.Count
        "unexpected-review-needed" = $unexpected.Count
    }
    decisions = $decisions
}

if ($Json) {
    $report | ConvertTo-Json -Depth 8
    exit 0
}

Write-Host "# Manual decision explainer"
Write-Host ""
Write-Host "No git add is executed by this script."
Write-Host "Do not commit, push, or open a PR until the user manually reviews these choices."
Write-Host ""
Write-Host "## Manifest summary"
Write-Host ("- core-life-demo: {0}" -f $core.Count)
Write-Host ("- review-and-recording-support: {0}" -f $support.Count)
Write-Host ("- manual-decision-time-compute: {0}" -f $manual.Count)
Write-Host ("- local-runtime-only: {0}" -f $runtime.Count)
Write-Host ("- unexpected-review-needed: {0}" -f $unexpected.Count)

foreach ($decision in $decisions) {
    Write-Decision -Decision $decision
}
