<#
Synthesizes each narration.json entry to a WAV via Windows SAPI and measures
its spoken duration (via ffprobe) so record.mjs can pace its on-screen dwell
time to match. Writes out/narration-<n>.wav and out/durations.json.

Usage: powershell -File apps/web/scripts/demo/synthesize-narration.ps1
#>

$ErrorActionPreference = 'Stop'
$outDir = Join-Path $PSScriptRoot 'out'
$ffprobe = 'C:\Users\harshag_500107\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0-full_build\bin\ffprobe.exe'

New-Item -ItemType Directory -Force -Path $outDir | Out-Null

# This machine only has the two legacy SAPI voices (David, Zira) — no
# Windows OneCore/neural voice is installed (that needs an elevated
# `Add-WindowsCapability` + a Microsoft Store/Update download, which this
# script won't do without being asked). Back to David (male) per feedback.
# Rate 0, a touch slower than the +1 tried earlier — everything past the
# intro was reading too fast at +1.
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SelectVoice('Microsoft David Desktop')
$synth.Rate = 0
$synth.Volume = 100

# The product name is spoken plain — no special vocal emphasis, just
# another word. Every sentence is plain text too now, question or not:
# PromptEmphasis (like PromptStyle.Rate before it) turned out to carry its
# own built-in prosodic slowdown, which is exactly what was making the
# intro's question sentence read slower than everything else — uniform
# rate wins over a "sound like a question" effect that can't be had without
# perturbing pace. The intro's problem statement still gets a genuine
# volume boost (PromptVolume, not text styling) since it's the hook.
function New-Prompt([string]$text, [bool]$loud) {
    $builder = New-Object System.Speech.Synthesis.PromptBuilder
    if ($loud) {
        $style = New-Object System.Speech.Synthesis.PromptStyle
        $style.Volume = [System.Speech.Synthesis.PromptVolume]::ExtraLoud
        $builder.StartStyle($style)
    }
    $builder.AppendText($text)
    if ($loud) { $builder.EndStyle() }
    return $builder
}

$narration = Get-Content (Join-Path $PSScriptRoot 'narration.json') -Raw | ConvertFrom-Json
$durations = @()

for ($i = 0; $i -lt $narration.Count; $i++) {
    $wavPath = Join-Path $outDir "narration-$i.wav"
    $synth.SetOutputToWaveFile($wavPath)
    $isProblemStatement = $narration[$i].screen -eq 'intro'
    # Same Rate for every line — no per-line rate override. Only Volume
    # (intro) and per-sentence question emphasis vary.
    $synth.Speak((New-Prompt $narration[$i].narration $isProblemStatement))
    $synth.SetOutputToNull()

    $durationSec = [double](& $ffprobe -v quiet -show_entries format=duration -of csv=p=0 $wavPath)
    # Dwell = speech length + a short 0.4s breath, not a long static silent
    # hold — voice should only go quiet during an actual screen transition,
    # not while just sitting on a screen after the line's finished.
    $dwellSec = [math]::Round($durationSec + 0.4, 2)
    $durations += $dwellSec
    Write-Host "narration $i`: $($durationSec.ToString('0.00'))s speech -> $($dwellSec)s dwell"
}

$durations | ConvertTo-Json | Set-Content (Join-Path $outDir 'durations.json')
Write-Host 'done'
