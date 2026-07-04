param(
    [string[]]$Values = @("false", "true", "true", "false", "true", "false", "true"),
    [string]$TargetValue = $(if ($env:MILOCO_LIFE_DEVICE_STATE_TARGET_VALUE) { $env:MILOCO_LIFE_DEVICE_STATE_TARGET_VALUE } else { "true" }),
    [string]$DeviceId = "mock-speaker",
    [string]$StatusIid = "mock-microphone-mute",
    [string]$Intent = "outfit_suggest",
    [int]$PollIntervalMs = 30000,
    [int]$CooldownMs = 120000,
    [int]$StepMs = 30000,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

function ConvertTo-StableValue {
    param([object]$Value)

    if ($null -eq $Value) {
        return "null"
    }
    if ($Value -is [bool]) {
        if ($Value) { return "true" }
        return "false"
    }
    return ([string]$Value).Trim().ToLowerInvariant()
}

function Test-TargetMatch {
    param(
        [object]$Value,
        [string]$Target
    )

    return (ConvertTo-StableValue -Value $Value) -eq (ConvertTo-StableValue -Value $Target)
}

if (-not $Json) {
    Write-Host "Device-state watcher mock sequence (offline, read-only)."
    Write-Host "Simulates baseline, edge trigger, held suppression, cooldown, and re-arm behavior from mock values."
    Write-Host "It does not read MiOT device status, does not call Life Agent, does not record camera clips, does not play speaker audio, and does not call MiMo."
    Write-Host "Set MILOCO_LIFE_DEVICE_STATE_TARGET_VALUE or pass -TargetValue to try the confirmed muted-edge value."
}

$baselineSeen = $false
$lastValue = $null
$armed = $false
$lastTriggeredAtMs = $null
$nowMs = 0
$enqueueCount = 0
$events = [System.Collections.ArrayList]::new()

for ($index = 0; $index -lt $Values.Count; $index++) {
    $currentValue = $Values[$index]
    $currentMatches = Test-TargetMatch -Value $currentValue -Target $TargetValue
    $triggered = $false
    $action = "idle"
    $nextPollAfterMs = $nowMs + $PollIntervalMs

    if (-not $baselineSeen) {
        $baselineSeen = $true
        $armed = -not $currentMatches
        $action = "baseline"
    } else {
        $previousMatches = Test-TargetMatch -Value $lastValue -Target $TargetValue

        if (-not $currentMatches) {
            $armed = $true
            if ($previousMatches) {
                $action = "rearmed"
            } else {
                $action = "idle"
            }
        } elseif (-not $armed) {
            $action = "held"
        } elseif ($null -ne $lastTriggeredAtMs -and $nowMs -lt ($lastTriggeredAtMs + $CooldownMs)) {
            $action = "cooldown"
            $nextPollAfterMs = [Math]::Min($lastTriggeredAtMs + $CooldownMs, $nowMs + $PollIntervalMs)
        } else {
            $action = "triggered"
            $triggered = $true
            $armed = $false
            $lastTriggeredAtMs = $nowMs
            $enqueueCount += 1
            $nextPollAfterMs = $nowMs + $CooldownMs
        }
    }

    $lastValue = $currentValue
    [void]$events.Add([ordered]@{
        index = $index
        now_ms = $nowMs
        value = $currentValue
        target_value = $TargetValue
        matches_target = $currentMatches
        action = $action
        triggered = $triggered
        armed_after = $armed
        next_poll_after_ms = $nextPollAfterMs
    })
    $nowMs += $StepMs
}

$result = [ordered]@{
    ok = $true
    read_only = $true
    offline = $true
    device_id = $DeviceId
    iid = $StatusIid
    target_value = $TargetValue
    poll_interval_ms = $PollIntervalMs
    cooldown_ms = $CooldownMs
    step_ms = $StepMs
    enqueue_count = $enqueueCount
    trigger_source = "device_state"
    payload_hint = [ordered]@{
        intent = $Intent
        trigger_source = "device_state"
        source_id = ("device_state:{0}:{1}" -f $DeviceId, $StatusIid)
    }
    events = @($events)
    expected_contract = @(
        "First sample establishes baseline and does not enqueue.",
        "A non-target to target edge enqueues once with trigger_source=device_state.",
        "A held target does not repeat.",
        "Leaving target re-arms the watcher.",
        "A re-entered target before cooldown expires is suppressed.",
        "A later re-entered target after cooldown can enqueue again."
    )
}

if ($Json) {
    $result | ConvertTo-Json -Depth 32
} else {
    Write-Host ""
    Write-Host ("Target value: {0}" -f $TargetValue)
    Write-Host ("enqueue_count: {0}" -f $enqueueCount)
    Write-Host ("trigger_source: {0}" -f $result.trigger_source)
    Write-Host ""
    Write-Host "## Events"
    foreach ($event in $events) {
        Write-Host (
            "- #{0} t={1} value={2} action={3} triggered={4} armed_after={5}" -f `
                $event.index,
                $event.now_ms,
                $event.value,
                $event.action,
                $event.triggered,
                $event.armed_after
        )
    }
}
