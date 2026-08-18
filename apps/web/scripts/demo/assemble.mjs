// Mixes narration onto the silent Playwright recording and transcodes to
// mp4: place each narration-<n>.wav at the *real* on-screen timestamp
// record.mjs measured for that beat (out/timeline.json) — not at the sum of
// assumed dwell times — so voice and screen stay in sync regardless of how
// long the real clicks/fills/fades between beats actually took. Mux that
// track onto out/clip.webm, output apps/web/public/demo/app-demo.mp4.
//
// Usage: node apps/web/scripts/demo/assemble.mjs
// Requires: out/clip.webm + out/timeline.json (record.mjs) and
// out/narration-<n>.wav (synthesize-narration.ps1) already present.

import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const outDir = path.join(__dirname, 'out')
const publicDemoDir = path.join(__dirname, '..', '..', 'public', 'demo')

const FFMPEG =
  'C:\\Users\\harshag_500107\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\\ffmpeg-9.0-full_build\\bin\\ffmpeg.exe'
const FFPROBE =
  'C:\\Users\\harshag_500107\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\\ffmpeg-9.0-full_build\\bin\\ffprobe.exe'

const narration = JSON.parse(readFileSync(path.join(__dirname, 'narration.json'), 'utf8'))
const timeline = JSON.parse(readFileSync(path.join(outDir, 'timeline.json'), 'utf8'))

function ffmpeg(args) {
  execFileSync(FFMPEG, ['-y', ...args], { stdio: ['ignore', 'ignore', 'ignore'] })
}

function getDuration(file) {
  return parseFloat(
    execFileSync(FFPROBE, ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file], {
      encoding: 'utf8',
    }),
  )
}

// timeline.json is written in the same order narration.json was walked, one
// entry per screen — index-aligned with narration-<n>.wav.
const inputs = narration.map((_, i) => path.join(outDir, `narration-${i}.wav`))
const delayFilters = timeline.map((beat, i) => `[${i}:a]adelay=${Math.max(0, Math.round(beat.atMs))}[a${i}]`)
const mixInputs = timeline.map((_, i) => `[a${i}]`).join('')
const filterComplex = `${delayFilters.join(';')};${mixInputs}amix=inputs=${timeline.length}:duration=longest:dropout_transition=0[aout]`

const narrationTrackRaw = path.join(outDir, 'narration-track-raw.wav')
ffmpeg([
  ...inputs.flatMap((f) => ['-i', f]),
  '-filter_complex', filterComplex,
  '-map', '[aout]',
  narrationTrackRaw,
])

const clipWebm = path.join(outDir, 'clip.webm')
// Pad/trim the mixed track to the video's *actual* measured length — the
// timeline already places every beat correctly, this just makes sure the
// tail (silence after the last line) covers the real recording length so
// `-shortest` below has no reason to cut real video.
const videoDuration = getDuration(clipWebm)
const narrationTrack = path.join(outDir, 'narration-track.wav')
ffmpeg(['-i', narrationTrackRaw, '-af', 'apad', '-t', String(videoDuration), narrationTrack])

const finalMp4 = path.join(publicDemoDir, 'app-demo.mp4')
// Pad the 1366x768 capture down onto a slightly bigger dark canvas rather
// than playing it edge-to-edge — reads as a framed product shot instead of
// a raw screen recording. crf 18 + preset slow: near-visually-lossless
// encode so on-screen text and icons stay crisp despite the extra scale.
const frame = 'scale=1160:652,pad=1600:900:220:124:color=0x0B1220'
ffmpeg([
  '-i', clipWebm,
  '-i', narrationTrack,
  '-vf', frame,
  '-c:v', 'libx264',
  '-preset', 'slow',
  '-crf', '18',
  '-pix_fmt', 'yuv420p',
  '-c:a', 'aac',
  '-shortest',
  finalMp4,
])

console.log(`done -> ${finalMp4}`)
