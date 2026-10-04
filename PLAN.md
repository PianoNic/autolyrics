# Plan

## Flow

```
link ─► resolve ─► audio ─► lyrics search ─┬─ word-synced found ──────────────┐
                                           └─ line/plain only ─► demucs ─►     │
                                              whisperx align ─► (no lyrics:    │
                                              whisper transcribe + align) ─────┤
                                                                               ▼
                         export ◄─ validate ◄─ deepseek final touches ◄────────┘
                           │
                           └─► review screen ─► (optional) Composer editor
```

## Pipeline stages (backend)

1. **Resolve** – Spotify / YouTube / Apple Music link or search text → title, artists, album,
   duration. Spotify metadata via the Web API (client credentials), YouTube via yt-dlp.
2. **Audio** – yt-dlp. For non-YouTube links, search YouTube Music for `artist title` and take the
   result whose duration is closest to the resolved one (±2 s). ffmpeg converts to WAV.
3. **Lyrics** – Python ports of Composer's providers (binimum, boidu TTML, portato QRC, LRCLIB),
   queried in parallel and filtered by duration. Each result keeps its sync type.
4. **Route** – a word- or syllable-synced result skips to stage 7.
5. **Separate** – Demucs htdemucs_ft on the GPU → vocals stem (10–15 s per song on an RTX 5080).
6. **Align** – torchaudio MMS_FA forced alignment (one wav2vec2 model for 1,100+ languages, text
   romanised to a–z) instead of WhisperX's per-language models. A whole-song pass first; for
   line-synced text it also measures, per line, how far the given line times sit from the audio
   (a local median, because music videos insert skits mid-song), then aligns each line in its
   shifted window. Words with no letters ("—") are interpolated; isolated low-confidence words are
   re-anchored to their neighbour. With no lyrics anywhere, fall back to Whisper large-v3
   transcription and flag every word.
   Word-synced sources are not re-timed but **offset-checked**: their text is aligned and, if the
   source sits consistently off this audio (another master), all its times are shifted.
7. **Final touches (DeepSeek API)** – limited, JSON-only tasks: pick between sources where their
   text disagrees, mark background vocals and ad-libs, line breaks, consistent spelling, flag
   suspected errors. Never changes timings and never invents words outside the candidate texts.
   Output is validated against the input; every change is recorded in the report.
8. **Validate** – overlaps, impossible word durations, gaps, ordering → review flags.
9. **Export** – word-synced TTML in Composer's format, plus LRC, SRT, QRC and a JSON report of
   where each part came from.

## Frontend

- **Automatic flow (default):** paste link → live stage progress → review (flagged words
  highlighted, click to hear, accept/reject DeepSeek changes) → download.
- **Optional editor:** "Adjust in editor" opens the result in Composer's existing editor
  (timeline, edit, sync, preview, export) by importing the backend's TTML.
- **Removed:** landing/SEO/guide/converter pages, onboarding tour, in-browser Demucs, YouTube
  tunnel import, Cloudflare deploy config.

## Build order

1. CLI for songs with word-synced lyrics: resolve → lyrics → export.
2. Audio + Demucs + WhisperX alignment.
3. DeepSeek step and validation flags.
4. Local API server (FastAPI, progress over SSE) and the new frontend flow; strip the frontend.
5. Whisper-only fallback and polish.

Test track throughout: the COLORS version (153 s) from the original manual run.

## Alignment benchmark

`backend/scripts/benchmark_align.py` re-aligns songs whose real word timing is known and reports the
start error after removing the constant offset between the source's master and ours.

| Song | Input | median | < 250 ms | < 500 ms |
|---|---|---|---|---|
| Ufo361 – Emotions (German rap) | plain text | 59 ms | 87% | 90% |
| Ufo361 – Emotions | line-synced | 56 ms | 87% | 89% |
| Rick Astley – Never Gonna Give You Up | plain text | 56 ms | 83% | 86% |
| Rick Astley | line-synced | 66 ms | 79% | 82% |
| Kontra K – Erfolg ist kein Glück (video, +14.4 s intro) | line-synced LRCLIB | ~50 ms | 97–99% | 100% |

Misses cluster in choruses with heavy backing vocals; those words carry low confidence and are
flagged for review. Offsets found along the way: Rick Astley's Apple TTML is 0.81 s early for the
YouTube Music audio, Ufo361's binimum TTML 0.13 s.

## Notes

- lyrics-api.boidu.dev (Better Lyrics, Portato) answers cached songs without a key and returns 401
  for others; set `AUTOLYRICS_BOIDU_API_KEY` to use it fully.
- Length mismatches (album vs. video cut) demote a source to text-only instead of rejecting it.
