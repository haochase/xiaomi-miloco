param(
    [string]$Text = "",
    [string]$Voice = "Chloe",
    [string]$Model = "mimo-v2.5-tts",
    [string]$BaseUrl = $env:MIMO_TTS_BASE_URL,
    [string]$ApiKey = $env:MIMO_TTS_API_KEY,
    [ValidateSet("wav")]
    [string]$Format = "wav",
    [string]$OutputPath = "",
    [string]$SpeakerUrl = "",
    [switch]$DryRun,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0

$defaultTextBase64 = "6KGj6aOf55+l5a625rWL6K+V5pKt5oql77ya5oiR55yL5Yiw5LiA5Lu25rWF6JOd6ImyIFQg5oGk44CC6K+356Gu6K6k546w5Zy6546v5aKD5ZCO5YaN6YeH57qz5bu66K6u44CC"
if ([string]::IsNullOrWhiteSpace($Text)) {
    $Text = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($defaultTextBase64))
}

function Show-Usage {
    Write-Host @"
Usage:
  scripts/test-life-tts-voice.ps1 -DryRun
  `$env:MIMO_TTS_BASE_URL="https://api.xiaomimimo.com/v1"
  `$env:MIMO_TTS_API_KEY="<redacted>"
  scripts/test-life-tts-voice.ps1 -Voice Chloe -OutputPath .miloco-smoke\tts-Chloe.wav
  scripts/test-life-tts-voice.ps1 -Voice Chloe -SpeakerUrl http://127.0.0.1:18888/say

What it does:
  Synthesizes one Chinese demo sentence with MiMo TTS, then optionally writes WAV
  output or posts audio_base64 to a local PC speaker server.

Safety:
  This script does not record camera clips, does not call live-demo, does not
  persist household data, and does not print the API key.
"@
}

function New-TtsRequestBody {
    param(
        [string]$RequestText,
        [string]$RequestVoice,
        [string]$RequestModel,
        [string]$RequestFormat
    )

    # MiMo TTS currently uses /chat/completions with JSON keys "modalities",
    # "audio", and an empty "assistant" message turn to request audio output.
    return @{
        model = $RequestModel
        modalities = @("text", "audio")
        audio = @{
            voice = $RequestVoice
            format = $RequestFormat
        }
        messages = @(
            @{
                role = "user"
                content = $RequestText
            },
            @{
                role = "assistant"
                content = ""
            }
        )
    }
}

function Find-AudioBase64 {
    param([object]$Value)

    if ($null -eq $Value) {
        return $null
    }

    if ($Value -is [string]) {
        if ($Value.Length -lt 80) {
            return $null
        }
        $candidate = $Value
        if ($candidate.StartsWith("data:") -and $candidate.Contains(",")) {
            $candidate = $candidate.Split(",", 2)[1]
        }
        try {
            $bytes = [Convert]::FromBase64String($candidate)
        }
        catch {
            return $null
        }
        if ($bytes.Length -ge 4) {
            $prefix = [System.Text.Encoding]::ASCII.GetString($bytes, 0, 4)
            if ($prefix -eq "RIFF" -or $prefix -eq "OggS") {
                return $candidate
            }
        }
        if ($bytes.Length -ge 3) {
            $prefix3 = [System.Text.Encoding]::ASCII.GetString($bytes, 0, 3)
            if ($prefix3 -eq "ID3") {
                return $candidate
            }
        }
        return $null
    }

    if ($Value -is [System.Collections.IDictionary]) {
        foreach ($key in @("audio_base64", "data", "audio")) {
            if ($Value.Contains($key)) {
                $found = Find-AudioBase64 -Value $Value[$key]
                if ($found) {
                    return $found
                }
            }
        }
        foreach ($item in $Value.Values) {
            $found = Find-AudioBase64 -Value $item
            if ($found) {
                return $found
            }
        }
        return $null
    }

    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
        foreach ($item in $Value) {
            $found = Find-AudioBase64 -Value $item
            if ($found) {
                return $found
            }
        }
    }

    return $null
}

if ($Help) {
    Show-Usage
    exit 0
}

$requestBody = New-TtsRequestBody -RequestText $Text -RequestVoice $Voice -RequestModel $Model -RequestFormat $Format
$endpoint = ""
if (-not [string]::IsNullOrWhiteSpace($BaseUrl)) {
    $endpoint = $BaseUrl.TrimEnd("/") + "/chat/completions"
}

if ($DryRun) {
    Write-Host "MiMo TTS voice probe dry run"
    Write-Host "Endpoint: $endpoint"
    Write-Host "Model: $Model"
    Write-Host "Voice: $Voice"
    Write-Host "Format: $Format"
    Write-Host "This dry run does not record camera clips and does not print the API key."
    $requestBody | ConvertTo-Json -Depth 8
    exit 0
}

if ([string]::IsNullOrWhiteSpace($BaseUrl)) {
    throw "MIMO_TTS_BASE_URL is required. Set the environment variable or pass -BaseUrl."
}
if ([string]::IsNullOrWhiteSpace($ApiKey)) {
    throw "MIMO_TTS_API_KEY is required. Set the environment variable or pass -ApiKey."
}

$headers = @{
    Authorization = "Bearer $ApiKey"
}

Write-Host "Calling MiMo TTS without printing the API key..."
$response = Invoke-RestMethod -Method Post -Uri $endpoint -Headers $headers -ContentType "application/json" -Body ($requestBody | ConvertTo-Json -Depth 8)
$audioBase64 = Find-AudioBase64 -Value $response
if ([string]::IsNullOrWhiteSpace($audioBase64)) {
    throw "MiMo TTS response did not include audio_base64 data."
}

Write-Host "TTS OK: model=$Model, voice=$Voice, format=$Format, endpoint=$endpoint"

if (-not [string]::IsNullOrWhiteSpace($OutputPath)) {
    $resolvedOutput = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath)
    $outputDir = Split-Path -Parent $resolvedOutput
    if (-not [string]::IsNullOrWhiteSpace($outputDir)) {
        New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
    }
    [System.IO.File]::WriteAllBytes($resolvedOutput, [Convert]::FromBase64String($audioBase64))
    Write-Host "Wrote audio: $resolvedOutput"
}

if (-not [string]::IsNullOrWhiteSpace($SpeakerUrl)) {
    $speakerPayload = @{
        message = $Text
        audio_base64 = $audioBase64
        audio_format = $Format
        domain = "outfit"
        urgency = "low"
        requires_ack = $false
    }
    Invoke-RestMethod -Method Post -Uri $SpeakerUrl -ContentType "application/json" -Body ($speakerPayload | ConvertTo-Json -Depth 8) | Out-Null
    Write-Host "Posted audio_base64 to speaker: $SpeakerUrl"
}
