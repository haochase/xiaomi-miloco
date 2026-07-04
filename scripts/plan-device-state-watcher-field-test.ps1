param(
    [string]$BaseUrl = "http://127.0.0.1:1810",
    [string]$Token = $env:MILOCO_SERVER_TOKEN,
    [string]$SpeakerId = $env:MILOCO_LIFE_DEVICE_STATE_DID,
    [switch]$SkipServer,
    [switch]$RequireRunning,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

$probeScript = Join-Path $PSScriptRoot "probe-xiaomi-speaker-input.ps1"
$readyScript = Join-Path $PSScriptRoot "test-device-state-watcher-ready.ps1"

function New-EnvSnapshot {
    $names = @(
        "MILOCO_LIFE_DEVICE_STATE_WATCHER_ENABLED",
        "MILOCO_LIFE_DEVICE_STATE_WATCHER_AUDIT_PASSED",
        "MILOCO_LIFE_DEVICE_STATE_DID",
        "MILOCO_LIFE_DEVICE_STATE_IID",
        "MILOCO_LIFE_DEVICE_STATE_TARGET_VALUE"
    )

    $items = [System.Collections.ArrayList]::new()
    foreach ($name in $names) {
        $value = [Environment]::GetEnvironmentVariable($name)
        [void]$items.Add([ordered]@{
            name = $name
            configured = -not [string]::IsNullOrWhiteSpace($value)
        })
    }
    return @($items)
}

function Invoke-Readiness {
    $readyParams = @{
        BaseUrl = $BaseUrl
        Json = $true
    }
    if ($Token) {
        $readyParams.Token = $Token
    }
    if ($SkipServer) {
        $readyParams.SkipServer = $true
    }
    if ($RequireRunning) {
        $readyParams.RequireRunning = $true
    }

    $output = & $readyScript @readyParams
    $exitCode = $LASTEXITCODE
    $parsed = $null
    if ($output) {
        try {
            $parsed = $output | ConvertFrom-Json
        } catch {
            $parsed = [ordered]@{
                parse_error = $_.Exception.Message
                raw = $output
            }
        }
    }
    return [ordered]@{
        exit_code = $exitCode
        result = $parsed
    }
}

if (-not $Json) {
    Write-Host "Device-state watcher field test plan (read-only)."
    Write-Host "This plans the after-hours Xiaomi speaker microphone mute watcher test."
    Write-Host "It does not read MiOT device status, does not call Life Agent, does not record camera clips, does not play speaker audio, and does not call MiMo."
}

$speakerIdForPlan = if ([string]::IsNullOrWhiteSpace($SpeakerId)) { "<confirmed speaker did>" } else { $SpeakerId }

$readiness = Invoke-Readiness
$envSnapshot = New-EnvSnapshot

$probeBase = "powershell -ExecutionPolicy Bypass -File `"$probeScript`" -BaseUrl $BaseUrl -SpeakerId $speakerIdForPlan"
if ($Token) {
    $probeBase = "$probeBase -Token <token>"
}

$commands = [ordered]@{
    scan = "$probeBase -Json"
    status = "$probeBase -StatusIid <candidate-iid> -Json"
    env_enabled = '$env:MILOCO_LIFE_DEVICE_STATE_WATCHER_ENABLED = "true"'
    env_audit = '$env:MILOCO_LIFE_DEVICE_STATE_WATCHER_AUDIT_PASSED = "true"'
    env_did = '$env:MILOCO_LIFE_DEVICE_STATE_DID = "' + $speakerIdForPlan + '"'
    env_iid = '$env:MILOCO_LIFE_DEVICE_STATE_IID = "<confirmed microphone mute iid>"'
    env_target = '$env:MILOCO_LIFE_DEVICE_STATE_TARGET_VALUE = "<value observed on muted edge>"'
    readiness = "powershell -ExecutionPolicy Bypass -File `"$readyScript`" -BaseUrl $BaseUrl -RequireRunning -Json"
}

$steps = @(
    [ordered]@{
        name = "scan_candidates"
        action = "Run the probe without StatusIid to list microphone/mute watcher candidates."
        command = $commands.scan
    },
    [ordered]@{
        name = "confirm_iid_value"
        action = "Manually toggle Xiaomi speaker microphone mute and rerun the same StatusIid read before and after."
        command = $commands.status
    },
    [ordered]@{
        name = "configure_env"
        action = "Set the five MILOCO_LIFE_DEVICE_STATE_* gates from the observed did/iid/value."
        command = (@(
            $commands.env_enabled,
            $commands.env_audit,
            $commands.env_did,
            $commands.env_iid,
            $commands.env_target
        ) -join "; ")
    },
    [ordered]@{
        name = "restart_and_verify_baseline"
        action = "Restart backend, then use readiness diagnostics to confirm running=true and first poll baseline."
        command = $commands.readiness
    },
    [ordered]@{
        name = "edge_trigger_once"
        action = "After baseline is visible, manually toggle mute into the target edge once and inspect normal scene run evidence."
        expectation = "One edge trigger enters trigger_source=device_state; held target does not repeat during cooldown."
    },
    [ordered]@{
        name = "re-arm"
        action = "Manually toggle mute away from target, wait past cooldown, then toggle into target again."
        expectation = "Watcher re-arm allows a second edge trigger only after leaving target and cooldown."
    }
)

$planOk = if ($RequireRunning) { $readiness.exit_code -eq 0 } else { $true }

$result = [ordered]@{
    ok = $planOk
    read_only = $true
    base_url = $BaseUrl
    speaker_id = $speakerIdForPlan
    skip_server = [bool]$SkipServer
    require_running = [bool]$RequireRunning
    env_snapshot = @($envSnapshot)
    readiness = $readiness
    scripts = [ordered]@{
        probe = $probeScript
        readiness = $readyScript
    }
    manual_steps = @($steps)
    guardrails = @(
        "Idle watcher polling may only read MiOT status.",
        "First poll establishes baseline and must not trigger.",
        "Only a target edge may call enqueue_life_scene_trigger_service.",
        "Held target must not repeat because cooldown and re-arm are required.",
        "This planning script itself performs no MiOT status read, no control call, no camera capture, no speaker playback, no MiMo call, and no Life Agent trigger."
    )
}

if ($Json) {
    $result | ConvertTo-Json -Depth 32
} else {
    Write-Host ""
    Write-Host "## Env gates"
    foreach ($item in $envSnapshot) {
        Write-Host ("- {0}: {1}" -f $item.name, $(if ($item.configured) { "configured" } else { "missing" }))
    }

    Write-Host ""
    Write-Host "## Readiness"
    Write-Host ("- exit_code: {0}" -f $readiness.exit_code)
    if ($readiness.result) {
        Write-Host ("- ok: {0}" -f $readiness.result.ok)
    }

    Write-Host ""
    Write-Host "## Manual steps"
    foreach ($step in $steps) {
        Write-Host ("- {0}: {1}" -f $step.name, $step.action)
        if ($step.command) {
            Write-Host ("  command: {0}" -f $step.command)
        }
        if ($step.expectation) {
            Write-Host ("  expectation: {0}" -f $step.expectation)
        }
    }

    Write-Host ""
    Write-Host "## Guardrails"
    foreach ($guardrail in $result.guardrails) {
        Write-Host ("- {0}" -f $guardrail)
    }
}

if ($RequireRunning -and $readiness.exit_code -ne 0) {
    exit $readiness.exit_code
}
