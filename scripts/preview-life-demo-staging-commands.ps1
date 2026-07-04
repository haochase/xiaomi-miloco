param(
    [switch]$IncludeReviewSupport,
    [switch]$IncludeManualDecision,
    [switch]$All,
    [switch]$OneCommand
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

function Format-GitPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    '"' + $Path.Replace('"', '\"') + '"'
}

function Write-PreviewCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title,
        [object[]]$Items
    )

    Write-Host ""
    Write-Host ("## {0}" -f $Title)
    if ($Items.Count -eq 0) {
        Write-Host "- no files currently reported by the manifest"
        return
    }

    if ($OneCommand) {
        $paths = @($Items | ForEach-Object { Format-GitPath -Path $_.path })
        Write-Host ("git add -- {0}" -f ($paths -join " "))
        return
    }

    foreach ($item in $Items) {
        Write-Host ("git add -- {0}" -f (Format-GitPath -Path $item.path))
    }
}

Write-Host "# Staging command preview"
Write-Host ""
Write-Host "No git add is executed by this script."
Write-Host "Do not commit, push, or open a PR until the user manually reviews this preview."
Write-Host "Default mode previews core-life-demo only."
Write-Host "Use -IncludeReviewSupport for review-and-recording-support, -IncludeManualDecision for time_compute.py, or -All for both."

$manifestJson = & $manifestScript
if ($LASTEXITCODE -ne 0) {
    throw "export-life-demo-review-manifest.ps1 failed with exit code $LASTEXITCODE"
}
$manifest = $manifestJson | ConvertFrom-Json
$groups = $manifest.groups

$core = @(Get-GroupItems -Groups $groups -Name "core-life-demo")
$support = @(Get-GroupItems -Groups $groups -Name "review-and-recording-support")
$manual = @(Get-GroupItems -Groups $groups -Name "manual-decision-time-compute")
$localRuntime = @(Get-GroupItems -Groups $groups -Name "local-runtime-only")
$unexpected = @(Get-GroupItems -Groups $groups -Name "unexpected-review-needed")

Write-Host ""
Write-Host "## Manifest summary"
Write-Host ("- repo_root: {0}" -f $repoRoot)
Write-Host ("- core-life-demo: {0}" -f $core.Count)
Write-Host ("- review-and-recording-support: {0}" -f $support.Count)
Write-Host ("- manual-decision-time-compute: {0}" -f $manual.Count)
Write-Host ("- local-runtime-only: {0}" -f $localRuntime.Count)
Write-Host ("- unexpected-review-needed: {0}" -f $unexpected.Count)

if ($unexpected.Count -gt 0) {
    Write-Host ""
    Write-Host "## Blocking warning"
    Write-Host "- unexpected-review-needed is not empty; review these files before using any previewed command."
    foreach ($item in $unexpected) {
        Write-Host ("  - {0} {1}" -f $item.status, $item.path)
    }
}

Write-PreviewCommand -Title "core-life-demo" -Items $core

if ($IncludeReviewSupport -or $All) {
    Write-PreviewCommand -Title "review-and-recording-support" -Items $support
}
else {
    Write-Host ""
    Write-Host "## review-and-recording-support"
    Write-Host "- omitted by default; rerun with -IncludeReviewSupport after reviewing support scripts and docs"
}

if ($IncludeManualDecision -or $All) {
    Write-PreviewCommand -Title "manual-decision-time-compute" -Items $manual
}
else {
    Write-Host ""
    Write-Host "## manual-decision-time-compute"
    Write-Host "- omitted by default; rerun with -IncludeManualDecision only if the user decides time_compute.py belongs in this package"
}

Write-Host ""
Write-Host "## Excluded from staging preview"
Write-Host "- local-runtime-only is never printed as git add commands by this script."
Write-Host "- Do not stage generated media, SQLite proof DBs, caches, private LAN URLs, API keys, real household data, or raw MiMo responses."
