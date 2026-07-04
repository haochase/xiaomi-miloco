param(
    [string]$BaseUrl = "http://127.0.0.1:1810",
    [string]$Token = $env:MILOCO_SERVER_TOKEN,
    [string]$SpeakerId = "",
    [string]$StatusIid = "",
    [string[]]$CandidateTerms = @(
        "mute",
        "muted",
        "microphone",
        "mic",
        "input",
        "voice",
        "asr",
        "speech",
        "recognition",
        "wake",
        "listen",
        "dialog"
    ),
    [switch]$Json
)

$ErrorActionPreference = "Stop"

function Invoke-MilocoGet {
    param([string]$Path)

    if (-not $Token) {
        throw "Token is required. Pass -Token or set MILOCO_SERVER_TOKEN."
    }

    $headers = @{ Authorization = "Bearer $Token" }
    $uri = ($BaseUrl.TrimEnd("/") + $Path)
    Invoke-RestMethod -Method Get -Uri $uri -Headers $headers
}

function ConvertTo-SearchText {
    param([object]$Value)

    if ($null -eq $Value) {
        return ""
    }
    return ($Value | ConvertTo-Json -Depth 32 -Compress)
}

function Test-SpeakerLikeDevice {
    param([object]$Device)

    $text = (ConvertTo-SearchText $Device).ToLowerInvariant()
    foreach ($term in @("speaker", "xiaomi.wifispeaker", "xiaoai")) {
        if ($text.Contains($term)) {
            return $true
        }
    }
    return $false
}

function Get-CandidateConfidence {
    param([string[]]$MatchedTerms)

    $terms = @($MatchedTerms | ForEach-Object { $_.ToLowerInvariant() })
    if ($terms -contains "microphone" -or $terms -contains "mic") {
        if ($terms -contains "mute" -or $terms -contains "muted") {
            return "high"
        }
        return "medium"
    }
    if ($terms -contains "mute" -or $terms -contains "muted") {
        return "medium"
    }
    return "low"
}

function Get-CandidateRank {
    param([string]$Confidence)

    switch ($Confidence) {
        "high" { return 3 }
        "medium" { return 2 }
        default { return 1 }
    }
}

function Get-CandidateReason {
    param(
        [string[]]$MatchedTerms,
        [string]$Confidence
    )

    $terms = @($MatchedTerms)
    if (-not $terms) {
        return "No microphone/mute terms matched."
    }
    return "Matched microphone/mute search terms: {0}; confidence={1}." -f ($terms -join ", "), $Confidence
}

function Get-DeviceId {
    param([object]$Device)

    foreach ($name in @("did", "id", "device_id", "deviceId")) {
        if ($Device.PSObject.Properties.Name -contains $name -and $Device.$name) {
            return [string]$Device.$name
        }
    }
    return $null
}

function Get-DeviceListItems {
    param([object]$DevicesResponse)

    if ($null -eq $DevicesResponse) {
        return @()
    }
    if (-not ($DevicesResponse.PSObject.Properties.Name -contains "data")) {
        return @()
    }

    $data = $DevicesResponse.data
    if ($data -is [System.Array]) {
        return @($data)
    }
    if ($null -ne $data -and $data.PSObject.Properties.Name -contains "devices") {
        return @($data.devices)
    }
    if ($null -ne $data) {
        return @($data)
    }
    return @()
}

function Get-SpecEntries {
    param([object]$SpecResponse)

    $spec = $null
    if ($SpecResponse.PSObject.Properties.Name -contains "data") {
        $spec = $SpecResponse.data.spec
    } elseif ($SpecResponse.PSObject.Properties.Name -contains "spec") {
        $spec = $SpecResponse.spec
    }
    if ($null -eq $spec) {
        return @()
    }

    $entries = @()
    foreach ($property in $spec.PSObject.Properties) {
        $iid = [string]$property.Name
        $entry = $property.Value
        $entryText = (ConvertTo-SearchText $entry).ToLowerInvariant()
        $matched = @()
        foreach ($term in $CandidateTerms) {
            if ($entryText.Contains($term.ToLowerInvariant())) {
                $matched += $term
            }
        }
        $confidence = Get-CandidateConfidence -MatchedTerms $matched
        $isProperty = $iid.StartsWith("prop.")
        $entries += [ordered]@{
            iid = $iid
            name = $entry.name
            type = $entry.type
            access = $entry.access
            format = $entry.format
            matched_terms = @($matched)
            confidence = $confidence
            rank = Get-CandidateRank -Confidence $confidence
            reason = Get-CandidateReason -MatchedTerms $matched -Confidence $confidence
            manual_check = "Read this iid before and after manually toggling speaker microphone mute."
            watcher_candidate = $isProperty -and $matched.Count -gt 0
        }
    }
    return @($entries)
}

function Get-SpecSignalSummary {
    param([object]$SpecResponse)

    $specText = (ConvertTo-SearchText $SpecResponse).ToLowerInvariant()
    $outputTerms = @("play-text", "execute-text-directive")
    $inputTerms = @(
        "asr",
        "speech",
        "voice",
        "recognition",
        "wake",
        "listen",
        "dialog",
        "microphone",
        "mute"
    )
    $matchedOutput = @()
    foreach ($term in $outputTerms) {
        if ($specText.Contains($term)) {
            $matchedOutput += $term
        }
    }
    $matchedInput = @()
    foreach ($term in $inputTerms) {
        if ($specText.Contains($term.ToLowerInvariant())) {
            $matchedInput += $term
        }
    }

    [ordered]@{
        matched_output_actions = @($matchedOutput)
        matched_input_signals = @($matchedInput)
        likely_supports_speaker_output = $matchedOutput.Count -gt 0
        likely_exposes_speaker_input = $matchedInput.Count -gt 0
    }
}

function Get-StatusValue {
    param(
        [string]$did,
        [string]$iid
    )

    if (-not $iid) {
        return $null
    }
    $encodedIid = [uri]::EscapeDataString($iid)
    $status = Invoke-MilocoGet -Path "/api/miot/devices/$did/status?iid=$encodedIid"
    $properties = @($status.data.properties)
    if (-not $properties) {
        return [ordered]@{
            iid = $iid
            found = $false
            value = $null
            code = $null
        }
    }
    $prop = $properties | Select-Object -First 1
    return [ordered]@{
        iid = $prop.iid
        found = $true
        value = $prop.value
        code = $prop.code
    }
}

function New-WatcherConfigHint {
    param(
        [string]$Did,
        [string]$Iid,
        [object]$StatusValue
    )

    $targetCandidates = @("true", "1", "on")
    if ($null -ne $StatusValue -and $StatusValue.found -and $null -ne $StatusValue.value) {
        $targetCandidates = @([string]$StatusValue.value)
    }
    [ordered]@{
        env = [ordered]@{
            MILOCO_LIFE_DEVICE_STATE_WATCHER_ENABLED = "true"
            MILOCO_LIFE_DEVICE_STATE_WATCHER_AUDIT_PASSED = "true"
            MILOCO_LIFE_DEVICE_STATE_DID = $Did
            MILOCO_LIFE_DEVICE_STATE_IID = $Iid
            MILOCO_LIFE_DEVICE_STATE_TARGET_VALUE = "<set after observing mute edge>"
        }
        target_value_candidates = @($targetCandidates)
        notes = @(
            "Read spec/status only.",
            "Toggle the speaker microphone mute switch manually, then rerun with -StatusIid.",
            "Use the value seen on the muted edge as MILOCO_LIFE_DEVICE_STATE_TARGET_VALUE."
        )
    }
}

Write-Host "Xiaomi speaker input/device-state watcher probe (read-only)."
Write-Host "Reads /api/miot/device_list, /api/miot/devices/{did}/spec, and optional /status?iid= only."
Write-Host "It does not call /control, record clips, trigger Life Agent, call MiMo, or play audio."

$devicesResponse = Invoke-MilocoGet -Path "/api/miot/device_list"
$devices = @(Get-DeviceListItems -DevicesResponse $devicesResponse)

if ($SpeakerId) {
    $devices = @($devices | Where-Object { (Get-DeviceId $_) -eq $SpeakerId })
} else {
    $devices = @($devices | Where-Object { Test-SpeakerLikeDevice $_ })
}

$results = @()
foreach ($device in $devices) {
    $did = Get-DeviceId $device
    if (-not $did) {
        continue
    }

    $spec = $null
    $specError = $null
    try {
        $spec = Invoke-MilocoGet -Path "/api/miot/devices/$did/spec"
    } catch {
        $specError = $_.Exception.Message
    }

    $statusValue = $null
    $statusError = $null
    if ($StatusIid) {
        try {
            $statusValue = Get-StatusValue -Did $did -Iid $StatusIid
        } catch {
            $statusError = $_.Exception.Message
        }
    }

    $entries = if ($spec) { Get-SpecEntries -SpecResponse $spec } else { @() }
    $candidates = @(
        $entries |
            Where-Object { $_.watcher_candidate } |
            Sort-Object -Property @{ Expression = "rank"; Descending = $true }, @{ Expression = "iid"; Descending = $false }
    )
    $summary = if ($spec) { Get-SpecSignalSummary -SpecResponse $spec } else { [ordered]@{} }
    $watcherIid = if ($StatusIid) { $StatusIid } elseif ($candidates.Count -gt 0) { $candidates[0].iid } else { "" }
    $results += [ordered]@{
        did = $did
        name = $device.name
        model = $device.model
        spec_error = $specError
        summary = $summary
        candidate_terms = @($CandidateTerms)
        watcher_candidates = @($candidates)
        status_iid = $StatusIid
        status_error = $statusError
        status_value = $statusValue
        watcher_config_hint = New-WatcherConfigHint `
            -Did $did `
            -Iid $watcherIid `
            -StatusValue $statusValue
    }
}

if ($Json) {
    [ordered]@{
        base_url = $BaseUrl
        read_only = $true
        checked_count = $results.Count
        devices = $results
    } | ConvertTo-Json -Depth 32
    exit 0
}

if (-not $results) {
    Write-Host "No speaker-like devices found. Pass -SpeakerId to inspect one explicit device."
    exit 0
}

foreach ($result in $results) {
    Write-Host ""
    Write-Host ("Device: {0} {1} {2}" -f $result.did, $result.name, $result.model)
    if ($result.spec_error) {
        Write-Host ("Spec: failed - {0}" -f $result.spec_error)
        continue
    }
    Write-Host (
        "Output actions: {0}" -f (($result.summary.matched_output_actions -join ", ") -replace "^$", "none")
    )
    Write-Host (
        "Input signals: {0}" -f (($result.summary.matched_input_signals -join ", ") -replace "^$", "none")
    )
    Write-Host (
        "Likely speaker output: {0}" -f $result.summary.likely_supports_speaker_output
    )
    Write-Host (
        "Likely exposed speaker input: {0}" -f $result.summary.likely_exposes_speaker_input
    )
    Write-Host ("Watcher candidate count: {0}" -f $result.watcher_candidates.Count)
    foreach ($candidate in $result.watcher_candidates) {
        Write-Host (
            "  {0} {1} confidence={2} terms={3}" -f $candidate.iid, $candidate.name, $candidate.confidence, ($candidate.matched_terms -join ",")
        )
        Write-Host ("    reason: {0}" -f $candidate.reason)
        Write-Host ("    manual_check: {0}" -f $candidate.manual_check)
    }
    if ($result.status_iid) {
        if ($result.status_error) {
            Write-Host ("Status {0}: failed - {1}" -f $result.status_iid, $result.status_error)
        } else {
            Write-Host (
                "Status {0}: value={1} code={2}" -f $result.status_value.iid, $result.status_value.value, $result.status_value.code
            )
        }
    }
    Write-Host "Watcher env hint:"
    foreach ($item in $result.watcher_config_hint.env.GetEnumerator()) {
        Write-Host ("  {0}={1}" -f $item.Key, $item.Value)
    }
}
