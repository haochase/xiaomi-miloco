param(
    [switch]$Strict,
    [switch]$FailOnManualDecision
)

$ErrorActionPreference = "Stop"

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

function Write-Count {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]]$Items
    )

    Write-Host ("- {0}: {1}" -f $Name, $Items.Count)
    foreach ($item in $Items) {
        Write-Host ("  - {0} {1}" -f $item.status, $item.path)
    }
}

Write-Host "# Review readiness gate"
Write-Host ""
Write-Host "No commit, push, or PR is performed by this script."

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

Write-Host ""
Write-Host "## Current gate counts"
Write-Count -Name "unexpected-review-needed" -Items $unexpected
Write-Count -Name "manual-decision-time-compute" -Items $manual
Write-Count -Name "core-life-demo" -Items $core
Write-Count -Name "review-and-recording-support" -Items $support
Write-Count -Name "local-runtime-only" -Items $runtimeOnly

$errors = [System.Collections.ArrayList]::new()

if ($unexpected.Count -gt 0) {
    $errors.Add("unexpected-review-needed is not empty; review these paths before staging.") | Out-Null
}

if (($Strict -or $FailOnManualDecision) -and $manual.Count -gt 0) {
    $errors.Add("manual-decision-time-compute is not empty; decide whether time_compute.py is included or split out.") | Out-Null
}

if ($core.Count -eq 0) {
    $errors.Add("core-life-demo is empty; there is no source package to review.") | Out-Null
}

if ($support.Count -eq 0) {
    $errors.Add("review-and-recording-support is empty; review helpers are not visible in git status.") | Out-Null
}

Write-Host ""
Write-Host "## Readiness result"
if ($errors.Count -eq 0) {
    Write-Host "- ready for manual review checklist comparison"
    if ($manual.Count -gt 0) {
        Write-Host "- manual decision still visible: time_compute.py; default mode reports it without failing"
    }
    Write-Host "- run with -Strict or -FailOnManualDecision before final staging if manual-decision items must fail the gate"
}
else {
    foreach ($errorMessage in $errors) {
        Write-Host ("- blocked: {0}" -f $errorMessage)
    }
    exit 1
}
