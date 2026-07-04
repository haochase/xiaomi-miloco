param(
    [Parameter(Mandatory = $true)]
    [string]$BeforePath,
    [Parameter(Mandatory = $true)]
    [string]$AfterPath,
    [string]$DeviceId = "",
    [string]$StatusIid = "",
    [switch]$Json
)

$ErrorActionPreference = "Stop"

function Read-JsonFile {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "JSON file not found: $Path"
    }
    $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($raw)) {
        throw "JSON file is empty: $Path"
    }
    return $raw | ConvertFrom-Json
}

function ConvertTo-StableValue {
    param([object]$Value)

    if ($null -eq $Value) {
        return $null
    }
    if ($Value -is [bool]) {
        if ($Value) { return "true" }
        return "false"
    }
    if ($Value -is [string] -or $Value -is [int] -or $Value -is [long] -or $Value -is [double]) {
        return [string]$Value
    }
    return ($Value | ConvertTo-Json -Depth 16 -Compress)
}

function Get-DeviceStatusRecord {
    param(
        [object]$Probe,
        [string]$WantedDeviceId,
        [string]$WantedStatusIid
    )

    $devices = @($Probe.devices)
    if (-not $devices) {
        throw "Probe JSON does not contain devices."
    }

    foreach ($device in $devices) {
        if ($WantedDeviceId -and [string]$device.did -ne $WantedDeviceId) {
            continue
        }
        $status = $device.status_value
        if ($null -eq $status) {
            continue
        }
        $iid = if ($status.iid) { [string]$status.iid } else { [string]$device.status_iid }
        if ($WantedStatusIid -and $iid -ne $WantedStatusIid) {
            continue
        }
        return [ordered]@{
            did = [string]$device.did
            name = $device.name
            model = $device.model
            iid = $iid
            found = [bool]$status.found
            code = $status.code
            value = $status.value
            stable_value = ConvertTo-StableValue -Value $status.value
        }
    }

    throw "No matching status_value found. Use probe output generated with -StatusIid."
}

if (-not $Json) {
    Write-Host "Device-state watcher status compare (offline, read-only)."
    Write-Host "Compares two saved probe JSON files and suggests watcher env values."
    Write-Host "It does not read MiOT device status, does not call Life Agent, does not record camera clips, does not play speaker audio, and does not call MiMo."
}

$beforeProbe = Read-JsonFile -Path $BeforePath
$afterProbe = Read-JsonFile -Path $AfterPath
$before = Get-DeviceStatusRecord `
    -Probe $beforeProbe `
    -WantedDeviceId $DeviceId `
    -WantedStatusIid $StatusIid
$after = Get-DeviceStatusRecord `
    -Probe $afterProbe `
    -WantedDeviceId $DeviceId `
    -WantedStatusIid $StatusIid

if ($before.did -ne $after.did) {
    throw "Before and after files selected different devices: $($before.did) vs $($after.did)"
}
if ($before.iid -ne $after.iid) {
    throw "Before and after files selected different iids: $($before.iid) vs $($after.iid)"
}

$valueChanged = $before.stable_value -ne $after.stable_value
$targetValueHint = if ($valueChanged) { $after.stable_value } else { "" }

$result = [ordered]@{
    ok = $valueChanged
    read_only = $true
    offline = $true
    did = $after.did
    iid = $after.iid
    value_changed = $valueChanged
    before = $before
    after = $after
    target_value_hint = $targetValueHint
    watcher_env_hint = [ordered]@{
        MILOCO_LIFE_DEVICE_STATE_WATCHER_ENABLED = "true"
        MILOCO_LIFE_DEVICE_STATE_WATCHER_AUDIT_PASSED = "true"
        MILOCO_LIFE_DEVICE_STATE_DID = $after.did
        MILOCO_LIFE_DEVICE_STATE_IID = $after.iid
        MILOCO_LIFE_DEVICE_STATE_TARGET_VALUE = $(if ($targetValueHint) { $targetValueHint } else { "<rerun after toggling microphone mute>" })
    }
    next_steps = @(
        "If value_changed is true, use target_value_hint as the muted-edge target only after confirming the manual toggle direction.",
        "Run the readiness helper with -SkipServer first, then restart backend and require running diagnostics.",
        "Only after baseline is visible should you manually toggle the microphone mute edge."
    )
}

if ($Json) {
    $result | ConvertTo-Json -Depth 32
} else {
    Write-Host ("Device: {0} {1} {2}" -f $after.did, $after.name, $after.model)
    Write-Host ("Status iid: {0}" -f $after.iid)
    Write-Host ("Before value: {0}" -f $before.stable_value)
    Write-Host ("After value: {0}" -f $after.stable_value)
    Write-Host ("Value changed: {0}" -f $valueChanged)
    if ($targetValueHint) {
        Write-Host ("Target value hint: {0}" -f $targetValueHint)
    } else {
        Write-Host "Target value hint: unavailable until a changed value is observed."
    }
    Write-Host "Watcher env hint:"
    foreach ($item in $result.watcher_env_hint.GetEnumerator()) {
        Write-Host ("  {0}={1}" -f $item.Key, $item.Value)
    }
}

if (-not $result.ok) {
    exit 1
}
