param(
    [switch]$Strict,
    [switch]$RequireLiveHelpers
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$milocoDevRoot = Split-Path -Parent $repoRoot
$manifestScript = Join-Path $PSScriptRoot "export-life-demo-review-manifest.ps1"
$finalStagingScript = Join-Path $PSScriptRoot "test-life-demo-final-staging.ps1"
$liveDemoScript = Join-Path $milocoDevRoot "run-live-demo.ps1"
$pcSpeakerScript = Join-Path $milocoDevRoot "pc-speaker-server.ps1"

function Invoke-RecordingStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host ("== {0} ==" -f $Label)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE"
    }
}

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

$warnings = [System.Collections.ArrayList]::new()

Write-Host "# Recording readiness gate"
Write-Host ""
Write-Host "No git add is executed by this script."
Write-Host "Do not commit, push, or open a PR until the user manually reviews this gate."
Write-Host "Default mode checks review state and after-hours prerequisites without calling real camera, real MiMo, pc_speaker, or MIMO_TTS_API_KEY."
Write-Host "Use -RequireLiveHelpers when preparing a real recording pass and -Strict when warnings should fail the gate."

Invoke-RecordingStep -Label "Review manifest parse" -Command {
    $script:ManifestJson = & $manifestScript
    if ($LASTEXITCODE -ne 0) {
        throw "export-life-demo-review-manifest.ps1 failed with exit code $LASTEXITCODE"
    }
    $script:Manifest = $script:ManifestJson | ConvertFrom-Json
}

$groups = $script:Manifest.groups
$unexpected = @(Get-GroupItems -Groups $groups -Name "unexpected-review-needed")
$manual = @(Get-GroupItems -Groups $groups -Name "manual-decision-time-compute")
$core = @(Get-GroupItems -Groups $groups -Name "core-life-demo")
$support = @(Get-GroupItems -Groups $groups -Name "review-and-recording-support")

Write-Host ""
Write-Host "## Review state"
Write-Host ("- unexpected-review-needed: {0}" -f $unexpected.Count)
Write-Host ("- manual-decision-time-compute: {0}" -f $manual.Count)
Write-Host ("- core-life-demo: {0}" -f $core.Count)
Write-Host ("- review-and-recording-support: {0}" -f $support.Count)

if ($unexpected.Count -gt 0) {
    $warnings.Add("unexpected-review-needed is not empty; review unknown files before recording.") | Out-Null
}
if ($manual.Count -gt 0) {
    $warnings.Add("manual-decision-time-compute still needs a user decision before final staging.") | Out-Null
}

Write-Host ""
Write-Host "## Live helper checks"
$liveDemoExists = Test-Path -LiteralPath $liveDemoScript
$pcSpeakerExists = Test-Path -LiteralPath $pcSpeakerScript
$ttsKeyPresent = -not [string]::IsNullOrWhiteSpace($env:MIMO_TTS_API_KEY)

Write-Host ("- run-live-demo.ps1: {0}" -f $(if ($liveDemoExists) { "found" } else { "missing" }))
Write-Host ("- pc-speaker-server.ps1: {0}" -f $(if ($pcSpeakerExists) { "found" } else { "missing" }))
Write-Host ("- MIMO_TTS_API_KEY: {0}" -f $(if ($ttsKeyPresent) { "present in environment; not printed" } else { "not set" }))
Write-Host "- real camera: not called by this script"
Write-Host "- real MiMo: not called by this script"
Write-Host "- pc_speaker: not called by this script"

if (-not $liveDemoExists) {
    $warnings.Add("E:\new_job\MilocoDev\run-live-demo.ps1 is missing; real camera/MiMo recording orchestration is unavailable.") | Out-Null
}
if (-not $pcSpeakerExists) {
    $warnings.Add("E:\new_job\MilocoDev\pc-speaker-server.ps1 is missing; pc_speaker recording proof is unavailable.") | Out-Null
}
if (-not $ttsKeyPresent) {
    $warnings.Add("MIMO_TTS_API_KEY is not set; real MiMo TTS voice proof cannot run yet.") | Out-Null
}

Write-Host ""
Write-Host "## Recording order"
Write-Host "- run scripts\preflight-life-demo-review.ps1 first"
Write-Host "- run scripts\test-life-demo-final-staging.ps1 before manual staging"
Write-Host "- run scripts\test-life-tts-voice.ps1 -DryRun before real TTS"
Write-Host "- only after manual approval, run E:\new_job\MilocoDev\run-live-demo.ps1 -Speak"
Write-Host "- record whether evidence came from mock data, real MiMo, real camera, or real audio in MILOCO_HACKATHON_DEMO_PROGRESS.md"

Invoke-RecordingStep -Label "Final staging gate default" -Command {
    & $finalStagingScript
}

Write-Host ""
Write-Host "## Recording readiness warnings"
if ($warnings.Count -eq 0) {
    Write-Host "- none"
}
else {
    foreach ($warning in $warnings) {
        Write-Host ("- {0}" -f $warning)
    }
}

if (($Strict -or $RequireLiveHelpers) -and $warnings.Count -gt 0) {
    throw "Recording readiness gate failed with $($warnings.Count) warning(s)."
}

Write-Host ""
Write-Host "## Recording readiness result"
if ($Strict -or $RequireLiveHelpers) {
    Write-Host "- strict recording readiness passed"
}
else {
    Write-Host "- default recording readiness finished; rerun with -RequireLiveHelpers -Strict before a real recording pass"
}
