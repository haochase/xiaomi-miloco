param(
    [string]$BaseUrl = "http://127.0.0.1:1810",
    [string]$Token = $env:MILOCO_SERVER_TOKEN,
    [switch]$RequireRunning,
    [switch]$SkipServer,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

function Add-Check {
    param(
        [System.Collections.ArrayList]$Checks,
        [string]$Name,
        [bool]$Ok,
        [string]$Detail
    )

    [void]$Checks.Add([ordered]@{
        name = $Name
        ok = $Ok
        detail = $Detail
    })
}

function Test-TruthyEnv {
    param([string]$Name)

    $value = [Environment]::GetEnvironmentVariable($Name)
    if (-not $value) {
        return $false
    }
    return @("1", "true", "yes", "on") -contains $value.Trim().ToLowerInvariant()
}

function Test-PresentEnv {
    param([string]$Name)

    $value = [Environment]::GetEnvironmentVariable($Name)
    return -not [string]::IsNullOrWhiteSpace($value)
}

function Get-SceneDefaults {
    if (-not $Token) {
        throw "Token is required for /api/voice/scene-defaults. Pass -Token or set MILOCO_SERVER_TOKEN."
    }
    $headers = @{ Authorization = "Bearer $Token" }
    $uri = $BaseUrl.TrimEnd("/") + "/api/voice/scene-defaults"
    Invoke-RestMethod -Method Get -Uri $uri -Headers $headers
}

if (-not $Json) {
    Write-Host "Device-state watcher readiness (read-only)."
    Write-Host "Checks local watcher env and the safe /api/voice/scene-defaults diagnostics."
    Write-Host "It does not read MiOT device status, does not call Life Agent, does not record camera clips, does not play speaker audio, and does not call MiMo."
}

$checks = [System.Collections.ArrayList]::new()

Add-Check $checks "env_enabled" `
    (Test-TruthyEnv "MILOCO_LIFE_DEVICE_STATE_WATCHER_ENABLED") `
    "MILOCO_LIFE_DEVICE_STATE_WATCHER_ENABLED must be true."
Add-Check $checks "env_audit_passed" `
    (Test-TruthyEnv "MILOCO_LIFE_DEVICE_STATE_WATCHER_AUDIT_PASSED") `
    "MILOCO_LIFE_DEVICE_STATE_WATCHER_AUDIT_PASSED must be true after manual read-only audit."
Add-Check $checks "env_did_configured" `
    (Test-PresentEnv "MILOCO_LIFE_DEVICE_STATE_DID") `
    "MILOCO_LIFE_DEVICE_STATE_DID must be set."
Add-Check $checks "env_iid_configured" `
    (Test-PresentEnv "MILOCO_LIFE_DEVICE_STATE_IID") `
    "MILOCO_LIFE_DEVICE_STATE_IID must be set from the read-only speaker probe."
Add-Check $checks "env_target_value_configured" `
    (Test-PresentEnv "MILOCO_LIFE_DEVICE_STATE_TARGET_VALUE") `
    "MILOCO_LIFE_DEVICE_STATE_TARGET_VALUE must be set from the observed mute edge."

$sceneDefaults = $null
$watcher = $null
if ($SkipServer) {
    Add-Check $checks "scene_defaults_skipped" $true "Skipped by -SkipServer."
} else {
    try {
        $sceneDefaults = Get-SceneDefaults
        $watcher = $sceneDefaults.data.device_state_watcher
        Add-Check $checks "scene_defaults_read" ($null -ne $watcher) `
            "Read /api/voice/scene-defaults device_state_watcher diagnostics."
    } catch {
        Add-Check $checks "scene_defaults_read" $false $_.Exception.Message
    }
}

if ($watcher) {
    Add-Check $checks "scene_defaults_ready" ([bool]$watcher.ready) `
        "device_state_watcher.ready should be true when env gates are complete."
    Add-Check $checks "scene_defaults_autostart_allowed" ([bool]$watcher.autostart_allowed) `
        "device_state_watcher.autostart_allowed should be true after safety/config gates pass."
    Add-Check $checks "scene_defaults_source" ($watcher.trigger_source -eq "device_state") `
        "device_state_watcher.trigger_source should be device_state."
    Add-Check $checks "scene_defaults_status_is_sanitized" `
        (-not ($watcher.PSObject.Properties.Name -contains "did") -and -not ($watcher.PSObject.Properties.Name -contains "iid") -and -not ($watcher.PSObject.Properties.Name -contains "target_value")) `
        "Diagnostics should expose configured booleans, not raw did/iid/target_value."
    if ($RequireRunning) {
        Add-Check $checks "scene_defaults_running" ([bool]$watcher.running) `
            "device_state_watcher.running should be true after backend restart with safe env."
    }
}

$failed = @($checks | Where-Object { -not $_.ok })
$result = [ordered]@{
    ok = $failed.Count -eq 0
    read_only = $true
    base_url = $BaseUrl
    require_running = [bool]$RequireRunning
    skipped_server = [bool]$SkipServer
    device_state_watcher = $watcher
    checks = @($checks)
    next_steps = @(
        "If env checks fail, set the MILOCO_LIFE_DEVICE_STATE_* variables from the read-only speaker probe.",
        "If ready is true but running is false, restart the backend and rerun with -RequireRunning.",
        "Only after baseline is visible should you manually toggle speaker microphone mute to test the edge trigger."
    )
}

if ($Json) {
    $result | ConvertTo-Json -Depth 32
} else {
    foreach ($check in $checks) {
        $status = if ($check.ok) { "ok" } else { "fail" }
        Write-Host ("[{0}] {1}: {2}" -f $status, $check.name, $check.detail)
    }
    if ($watcher) {
        Write-Host ("Watcher ready: {0}" -f $watcher.ready)
        Write-Host ("Watcher running: {0}" -f $watcher.running)
        Write-Host ("Watcher last_poll: {0}" -f ($watcher.last_poll | ConvertTo-Json -Compress -Depth 8))
    }
}

if (-not $result.ok) {
    exit 1
}
