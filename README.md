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
.venv/Scripts/python -m pip install --no-deps audio-separator==0.47.0 swift-f0

# 2. Configuration
cp .env.example .env          # then fill in AGENT_API_KEY (DeepSeek)

# 3. Frontend
cd frontend && npx -y pnpm@latest install && npx -y pnpm@latest build && cd ..

# 4. Run
.venv/Scripts/autolyrics serve        # open http://localhost:8765
```

(`.venv/Scripts/` on Windows, `.venv/bin/` elsewhere.) `audio-separator` goes in without its
dependencies because it pins a torch release that would replace the CUDA build. The first song
downloads the models into `models/`: three RoFormer separation models (~0.9 GB), the singing
acoustic model (57 MB), MMS (~1.2 GB, for languages the singing model does not cover) and, only
when needed, Whisper (~1.6 GB). Heavy work runs below normal priority with a few CPU threads, so
the desktop stays responsive.

## How the timing works (pipeline v2)

1. **Separation** (RoFormer, ~2.5 dB cleaner than Demucs): vocals from the mix, then lead from
   backing vocals, then reverb and echo off the lead.
2. **Listening**: a phoneme model trained on singing (LyricsAlignment-Multilingual, DALI) hears
   the dry lead and all vocals; the two hearings are averaged.
3. **One global solve**: a CTC Viterbi places every word of the song at once. A lyrics source's
   line times are a soft pull and a soft window, never a hard box, after measuring the constant
   offset between the source's master and this recording.
4. **Following the voice** (SwiftF0 pitch and voicing): a held word lasts while it sounds.
5. **Syllables**: words whose written syllables match their sung vowels are split, each syllable
   starting at the consonant before its vowel.
6. **Background vocals** are placed on the backing stem, near their main line.
7. **The judge**: every word gets a calibrated probability that its timing is right (fitted on
   the benchmark), and doubtful words are flagged in the editor instead of being patched.

`backend/scripts/collect_benchmark.py` builds a benchmark from songs with hand-made syllable
timing; `benchmark_suite.py` measures the pipeline on it and `fit_judge.py` calibrates the judge.

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
