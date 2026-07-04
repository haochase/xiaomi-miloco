param(
    [switch]$Strict
)

$ErrorActionPreference = "Stop"

$manifestScript = Join-Path $PSScriptRoot "export-life-demo-review-manifest.ps1"
$readinessScript = Join-Path $PSScriptRoot "test-life-demo-review-ready.ps1"
$secretBoundaryScript = Join-Path $PSScriptRoot "test-life-demo-secret-boundary.ps1"
$proofBundleScript = Join-Path $PSScriptRoot "export-life-demo-proof-bundle.ps1"

function Invoke-GateStep {
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

Write-Host "# Final staging gate"
Write-Host ""
Write-Host "No git add is executed by this script."
Write-Host "Do not commit, push, or open a PR until the user manually reviews this gate."
Write-Host "Default mode reports known blockers without failing; -Strict fails on manual-decision-time-compute and runtime SQLite proof DBs."

Invoke-GateStep -Label "Review manifest parse" -Command {
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
$runtimeOnly = @(Get-GroupItems -Groups $groups -Name "local-runtime-only")

Write-Host ""
Write-Host "## Final gate counts"
Write-Host ("- unexpected-review-needed: {0}" -f $unexpected.Count)
Write-Host ("- manual-decision-time-compute: {0}" -f $manual.Count)
Write-Host ("- core-life-demo: {0}" -f $core.Count)
Write-Host ("- review-and-recording-support: {0}" -f $support.Count)
Write-Host ("- local-runtime-only: {0}" -f $runtimeOnly.Count)

if ($manual.Count -gt 0) {
    Write-Host "- blocker note: manual-decision-time-compute must be decided before final staging."
}
if ($runtimeOnly.Count -gt 0) {
    Write-Host "- blocker note: local-runtime-only paths must stay unstaged."
}
Write-Host "- private artifact note: runtime SQLite proof DBs, generated media, real household data, private LAN URLs, and MIMO_TTS_API_KEY must stay out of git."

if ($Strict) {
    Invoke-GateStep -Label "Review readiness gate strict" -Command {
        & $readinessScript -Strict
    }
    Invoke-GateStep -Label "Secret boundary audit strict" -Command {
        & $secretBoundaryScript -FailOnWarning
    }
}
else {
    Invoke-GateStep -Label "Review readiness gate" -Command {
        & $readinessScript
    }
    Invoke-GateStep -Label "Secret boundary audit" -Command {
        & $secretBoundaryScript
    }
}

Invoke-GateStep -Label "Proof bundle JSON parse" -Command {
    $proofJson = & $proofBundleScript -Json
    if ($LASTEXITCODE -ne 0) {
        throw "export-life-demo-proof-bundle.ps1 failed with exit code $LASTEXITCODE"
    }
    $proof = $proofJson | ConvertFrom-Json
    if ($proof.bundle_version -ne 1) {
        throw "Unexpected proof bundle version: $($proof.bundle_version)"
    }
    Write-Host ("- proof bundle version: {0}" -f $proof.bundle_version)
    Write-Host ("- verification commands: {0}" -f @($proof.verification_commands).Count)
    Write-Host ("- recording steps: {0}" -f @($proof.recording_order).Count)
}

Write-Host ""
Write-Host "## Final staging result"
if ($Strict) {
    Write-Host "- strict gate passed; manual blockers and private artifact warnings did not fail this run"
}
else {
    Write-Host "- default gate finished; run with -Strict after resolving manual decisions and runtime warnings"
}
