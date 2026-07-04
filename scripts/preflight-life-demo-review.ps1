param(
    [switch]$SkipSmoke,
    [switch]$SkipOpenClaw,
    [bool]$SkipLiveCli = $true
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$openClawDir = Join-Path $repoRoot "plugins\openclaw"
$openClawVitest = Join-Path $openClawDir "node_modules\.bin\vitest.CMD"

function Invoke-PreflightStep {
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

Write-Host "# Life Demo Review Preflight"
Write-Host ""
Write-Host "No commit, push, or PR is performed by this script."
Write-Host "Manual decision required: review cli\src\miloco_cli\commands\time_compute.py before staging."

Invoke-PreflightStep -Label "Review status buckets" -Command {
    & (Join-Path $PSScriptRoot "review-life-demo-status.ps1")
}

Invoke-PreflightStep -Label "Review split plan" -Command {
    & (Join-Path $PSScriptRoot "plan-life-demo-review-split.ps1")
}

Invoke-PreflightStep -Label "Review manifest" -Command {
    & (Join-Path $PSScriptRoot "export-life-demo-review-manifest.ps1")
}

Invoke-PreflightStep -Label "Manual staging checklist" -Command {
    & (Join-Path $PSScriptRoot "prepare-life-demo-staging-checklist.ps1")
}

Invoke-PreflightStep -Label "Manual decision explainer" -Command {
    & (Join-Path $PSScriptRoot "explain-life-demo-manual-decisions.ps1")
}

Invoke-PreflightStep -Label "Staging command preview" -Command {
    & (Join-Path $PSScriptRoot "preview-life-demo-staging-commands.ps1")
}

Invoke-PreflightStep -Label "Review readiness gate" -Command {
    & (Join-Path $PSScriptRoot "test-life-demo-review-ready.ps1")
}

Invoke-PreflightStep -Label "Secret boundary audit" -Command {
    & (Join-Path $PSScriptRoot "test-life-demo-secret-boundary.ps1")
}

Invoke-PreflightStep -Label "Proof bundle snapshot" -Command {
    & (Join-Path $PSScriptRoot "export-life-demo-proof-bundle.ps1")
}

Invoke-PreflightStep -Label "Final staging gate" -Command {
    & (Join-Path $PSScriptRoot "test-life-demo-final-staging.ps1")
}

Invoke-PreflightStep -Label "Recording readiness gate" -Command {
    & (Join-Path $PSScriptRoot "test-life-demo-recording-ready.ps1")
}

if ($SkipSmoke) {
    Write-Host ""
    Write-Host "== Mock smoke skipped =="
    Write-Host "Run without -SkipSmoke to execute scripts\smoke-life-demo.ps1."
}
else {
    Invoke-PreflightStep -Label "Mock demo smoke" -Command {
        & (Join-Path $PSScriptRoot "smoke-life-demo.ps1") -SkipLiveCli:$SkipLiveCli
    }
}

if ($SkipOpenClaw) {
    Write-Host ""
    Write-Host "== OpenClaw life skill test skipped =="
    Write-Host "Run without -SkipOpenClaw to execute life-skill.test.ts."
}
elseif (-not (Test-Path -LiteralPath $openClawVitest)) {
    Write-Host ""
    Write-Host "== OpenClaw life skill test unavailable =="
    Write-Host ("Missing {0}; run plugin dependency setup before requiring this check." -f $openClawVitest)
}
else {
    Invoke-PreflightStep -Label "OpenClaw life skill test" -Command {
        Push-Location $openClawDir
        try {
            & $openClawVitest run tests\life-skill.test.ts
        }
        finally {
            Pop-Location
        }
    }
}

Invoke-PreflightStep -Label "Whitespace diff check" -Command {
    Push-Location $repoRoot
    try {
        git diff --check
    }
    finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "Review preflight finished. Re-read the status buckets before staging."
