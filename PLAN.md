# Plan and status

## Flow

```
song link ─► resolve (ArgonFetch) ─► audio ─► lyrics sources ─┬─ found ──────────────┐
                                                              └─ none: Whisper ──────┤
                                                                                     ▼
   editor (timeline, preview) ◄─ export ◄─ validate ◄─ align / offset check ◄─ DeepSeek clean-up
            │
            └─ Save to autolyrics ─► every format re-exported
```

## Pipeline (backend, one mediatorx command per stage)

1. **Resolve** – ArgonFetch turns a Spotify / YouTube / SoundCloud link into title, artists, cover
   and, for Spotify, the matching YouTube Music upload. YouTube titles are cleaned
   ("Artist - "Title" (Official Video) prod. by X" → artist + title).
2. **Audio** – ArgonFetch stream, highest bitrate in the source container; retried, cached per job.
3. **Lyrics** – Better Lyrics (Apple-style TTML), binimum, QQ Music via Portato (QRC) and LRCLIB,
   queried in parallel, parsed, judged against the audio length and ranked by sync granularity and
   source. A source whose length or timing does not fit this cut becomes text-only.
4. **Transcribe** – only when no source has the song (or `--transcribe`): Whisper large-v3-turbo on
   the isolated vocals; segments become lines, every word stays flagged.
5. **DeepSeek clean-up** – code cross-checks every other version and builds the decisions (line
   variants, missing lines, non-lyric lines); DeepSeek only picks between them, in JSON, and every
   answer is validated before it is applied. Runs before alignment.
6. **Align** – Demucs isolates the vocals; torchaudio MMS_FA forced alignment times every word
   (whole-song pass, then line windows shifted by a per-line local offset). Word-synced sources are
   offset-checked instead and shifted when they sit consistently off this audio.
7. **Export** – validation flags, then TTML (Composer dialect), word LRC, LRC, SRT, QRC, lyrics JSON
   and a report of where everything came from.

Architecture: see `backend/ARCHITECTURE.md`.

## Frontend

- `/` – paste a link, options, recent songs.
- `/jobs/:id` – live progress; when done it opens the song in the editor.
- `/editor` – Composer's editor on the Timeline with the song loaded, plus the autolyrics bar:
  lines to check (jump there), files, Save to autolyrics.

## Status

| Milestone | State |
|---|---|
| 1. Link → lyrics sources → export | done |
| 2. Demucs + forced alignment + offset checks | done, benchmarked |
| 3. DeepSeek clean-up and validation | done |
| 4. Local API, new frontend flow, editor hand-off, rebrand | done |
| Onion architecture with mediatorx | done |
| 5. Whisper fallback | in progress |
| Spicy Lyrics–style preview | in progress |
| Strip the editor to what the flow needs | next |

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
- ArgonFetch occasionally drops connections; calls are retried four times with backoff.
- Spicy Lyrics is AGPL-3.0 and may be adapted with attribution; Beautiful Lyrics has no license and
  is not used.
