param(
    [string]$BaseUrl = "http://127.0.0.1:1810",
    [string]$SpeakerId = $env:MILOCO_LIFE_DEVICE_STATE_DID,
    [string]$ConfirmedStatusIid = $env:MILOCO_LIFE_DEVICE_STATE_IID,
    [string]$ConfirmedTargetValue = $env:MILOCO_LIFE_DEVICE_STATE_TARGET_VALUE,
    [string]$Intent = "outfit_suggest",
    [int]$PollIntervalMs = 30000,
    [int]$CooldownMs = 300000,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

$readyScript = Join-Path $PSScriptRoot "test-device-state-watcher-ready.ps1"
$probeScript = Join-Path $PSScriptRoot "probe-xiaomi-speaker-input.ps1"

function New-EnvLine {
    param(
        [string]$Name,
        [string]$Value
    )

    return ("{0}={1}" -f $Name, $Value)
}

$speakerIdForPlan = if ([string]::IsNullOrWhiteSpace($SpeakerId)) { "<confirmed speaker did>" } else { $SpeakerId }
$statusIidForPlan = if ([string]::IsNullOrWhiteSpace($ConfirmedStatusIid)) { "<confirmed microphone mute iid>" } else { $ConfirmedStatusIid }
$targetValueForPlan = if ([string]::IsNullOrWhiteSpace($ConfirmedTargetValue)) { "<value observed on muted edge>" } else { $ConfirmedTargetValue }

if (-not $Json) {
    Write-Host "Device-state watcher activation plan (offline, read-only)."
    Write-Host "Builds the manual supervisord/env activation checklist for one Xiaomi speaker microphone mute edge."
    Write-Host "No SSH command is executed; this script does not edit local or remote configuration."
    Write-Host "It does not read MiOT device status, does not call Life Agent, does not record camera clips, does not play speaker audio, and does not call MiMo."
}

$envLines = @(
    (New-EnvLine "MILOCO_LIFE_DEVICE_STATE_WATCHER_ENABLED" "true")
    (New-EnvLine "MILOCO_LIFE_DEVICE_STATE_WATCHER_AUDIT_PASSED" "true")
    (New-EnvLine "MILOCO_LIFE_DEVICE_STATE_DID" $speakerIdForPlan)
    (New-EnvLine "MILOCO_LIFE_DEVICE_STATE_IID" $statusIidForPlan)
    (New-EnvLine "MILOCO_LIFE_DEVICE_STATE_TARGET_VALUE" $targetValueForPlan)
    (New-EnvLine "MILOCO_LIFE_DEVICE_STATE_INTENT" $Intent)
    (New-EnvLine "MILOCO_LIFE_DEVICE_STATE_POLL_INTERVAL_MS" ([string]$PollIntervalMs))
    (New-EnvLine "MILOCO_LIFE_DEVICE_STATE_COOLDOWN_MS" ([string]$CooldownMs))
)

$supervisordHint = "Add the MILOCO_LIFE_DEVICE_STATE_* lines to the miloco-backend supervisord environment, then restart miloco-backend manually."
$readyCommand = "powershell -ExecutionPolicy Bypass -File `"$readyScript`" -BaseUrl $BaseUrl -RequireRunning -Json"
$probeCommand = "powershell -ExecutionPolicy Bypass -File `"$probeScript`" -BaseUrl $BaseUrl -SpeakerId $speakerIdForPlan -StatusIid $statusIidForPlan -Json"

$steps = @(
    [ordered]@{
        name = "confirm_source"
        action = "Confirm the candidate IID and muted-edge value from saved read-only probe evidence before changing runtime env."
        command = $probeCommand
        expectation = "The confirmed IID and target value should match the manual microphone-mute edge observed in read-only probe evidence."
    },
    [ordered]@{
        name = "stage_supervisord_env"
        action = $supervisordHint
        environment = @($envLines)
    },
    [ordered]@{
        name = "restart_and_check_baseline"
        action = "Restart the backend manually, then verify watcher running=true and wait for last_poll.action=baseline."
        command = $readyCommand
        expectation = "The first poll establishes baseline and must not enqueue Life Agent."
    },
    [ordered]@{
        name = "edge_trigger_once"
        action = "After baseline is visible, manually toggle Xiaomi speaker microphone mute into the target value once."
        expectation = "Exactly one edge trigger enqueues trigger_source=device_state; keeping mute on must not repeat."
    },
    [ordered]@{
        name = "cooldown_and_rearm"
        action = "Toggle away from the target, wait past cooldown, then toggle into target again if a second proof is needed."
        expectation = "Re-arm requires leaving target; cooldown suppresses fast repeats."
    },
    [ordered]@{
        name = "rollback"
        action = "Disable the watcher env gates and restart backend manually after validation."
        environment = @(
            (New-EnvLine "MILOCO_LIFE_DEVICE_STATE_WATCHER_ENABLED" "false")
            (New-EnvLine "MILOCO_LIFE_DEVICE_STATE_WATCHER_AUDIT_PASSED" "false")
        )
        expectation = "After rollback, readiness should report running=false or fail the env gate intentionally."
    }
)

$result = [ordered]@{
    ok = $true
    offline = $true
    read_only = $true
    base_url = $BaseUrl
    speaker_id = $speakerIdForPlan
    confirmed_status_iid = $statusIidForPlan
    confirmed_target_value = $targetValueForPlan
    technical_validation_note = "Use a read-only probe to confirm the microphone mute IID and target edge before enabling the watcher."
    supervisord = [ordered]@{
        hint = $supervisordHint
        environment = @($envLines)
    }
    readiness_command = $readyCommand
    manual_steps = @($steps)
    guardrails = @(
        "This plan is offline and read-only.",
        "No SSH command is executed.",
        "No local or remote file is edited by this script.",
        "Idle watcher polling may only read MiOT status.",
        "First poll establishes baseline and must not trigger.",
        "Only a target edge may call enqueue_life_scene_trigger_service.",
        "The plan script itself performs no MiOT status read, no control call, no camera capture, no speaker playback, no MiMo call, and no Life Agent trigger."
    )
}

if ($Json) {
    $result | ConvertTo-Json -Depth 32
} else {
    Write-Host ""
    Write-Host "## Confirmed candidate"
    Write-Host ("- did: {0}" -f $speakerIdForPlan)
    Write-Host ("- iid: {0}" -f $statusIidForPlan)
    Write-Host ("- target_value: {0}" -f $targetValueForPlan)
    Write-Host "- note: confirm the microphone-mute technical validation edge with the read-only probe before activation."

    Write-Host ""
    Write-Host "## supervisord environment"
    foreach ($line in $envLines) {
        Write-Host ("- {0}" -f $line)
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
