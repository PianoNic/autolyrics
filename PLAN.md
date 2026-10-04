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
5. **Separate** – Demucs htdemucs on the GPU → vocals stem.
6. **Align** – WhisperX forced alignment of the known text against the vocals, line by line, using
   LRC line times as windows when present. Every word gets a confidence. With no lyrics anywhere,
   fall back to Whisper large-v3 transcription and flag every word.
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
