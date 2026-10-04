# autolyrics

Paste a song link, get word-synced lyrics (TTML, LRC, SRT, QRC) without syncing by hand.

Everything runs on your own machine. A local backend resolves the link with ArgonFetch, finds the
lyrics in several sources, isolates the vocals, times every word against them and has DeepSeek pick
between sources where they disagree. When no source has the song, Whisper transcribes it. The
result opens in an editor on the timeline, where you can drag words, fix text and preview it;
edits save back to the song automatically.

Based on [Composer](https://github.com/better-lyrics/composer) by Better Lyrics. Not affiliated
with Better Lyrics or Spicy Lyrics.

## Getting started

Requirements: Python 3.12, Node 22+, ffmpeg on `PATH`, and an NVIDIA GPU for reasonable speed
(CPU works, slowly).

```bash
# 1. Backend
python -m venv .venv
.venv/Scripts/python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
.venv/Scripts/python -m pip install -e "backend[ml,dev]"

# 2. Configuration
cp .env.example .env          # then fill in AGENT_API_KEY (DeepSeek)

# 3. Frontend
cd frontend && npx -y pnpm@latest install && npx -y pnpm@latest build && cd ..

# 4. Run
.venv/Scripts/autolyrics serve        # open http://localhost:8765
```

(`.venv/Scripts/` on Windows, `.venv/bin/` elsewhere.) The first song downloads the models: Demucs
(~300 MB), the MMS aligner (~1.2 GB) and, only when needed, Whisper (~1.6 GB).

Command line, without the web app:

```bash
.venv/Scripts/autolyrics run "https://open.spotify.com/track/…"   # files end up in jobs/<id>/output
.venv/Scripts/autolyrics run <link> --transcribe                   # ignore lyrics sources, use Whisper
```

For frontend development: `autolyrics serve` plus `cd frontend && npx -y pnpm@latest dev`
(Vite proxies `/api` to the backend).

## Layout

| Folder | What it is |
|---|---|
| `backend/` | Python package `autolyrics`: onion architecture with mediatorx, see `backend/ARCHITECTURE.md` |
| `frontend/` | React app: start page, job progress, and the editor (forked from Composer) |
| `PLAN.md` | Pipeline, status and the alignment benchmark |

## Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `AGENT_API_KEY`, `AGENT_BASE_URL`, `AGENT_MODEL` | OpenAI-compatible endpoint for DeepSeek (text clean-up only; never receives audio) |
| `AUTOLYRICS_BOIDU_API_KEY` | Optional: lets the Better Lyrics and QQ sources answer songs they have not cached |
| `AUTOLYRICS_JOBS_DIR` | Where jobs are stored (default `jobs/`) |
| `AUTOLYRICS_DEMUCS_MODEL`, `AUTOLYRICS_WHISPER_MODEL` | Model choices |

## Credits

- [Composer](https://github.com/better-lyrics/composer) by Better Lyrics (AGPL-3.0): the editor
  this frontend is forked from.
- [Spicy Lyrics](https://github.com/Spikerko/spicy-lyrics) by Spikerko (AGPL-3.0): the Preview
  renderer in `frontend/src/views/preview/spicy/` is adapted from its lyric layout, animator and
  styles. Its spring model is in turn a port of [spr](https://github.com/Fraktality/spr) by
  Fraktality (MIT).
- [ArgonFetch](https://app.argonfetch.dev) for resolving links and audio; LRCLIB, binimum and
  lyrics-api.boidu.dev for lyrics; Demucs, torchaudio MMS_FA, Whisper and pykakasi for audio and
  text processing.

## License

AGPL-3.0, see `LICENSE`.
