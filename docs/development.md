# Development

## Layout

The repository follows the layout of a .NET solution: one folder per project in `src/`.

| Folder | What it is |
|---|---|
| `src/Autolyrics.Domain` | `autolyrics.domain`: lyrics, jobs, candidates and the domain services |
| `src/Autolyrics.Application` | `autolyrics.application`: commands, queries, DTOs, interfaces, behaviors, notifications and the pipeline stages (mediatorx) |
| `src/Autolyrics.Infrastructure` | `autolyrics.infrastructure`: clients (ArgonFetch, lyrics providers, LLM) and services (ML, formats, persistence, runtime) |
| `src/Autolyrics.API` | `autolyrics.api`, `autolyrics.cli`, `autolyrics.composition`: HTTP API, command line, dependency wiring |
| `src/Autolyrics.Frontend` | React app: start page, job progress and the editor (forked from Composer) |
| `src/Autolyrics.Tests` | pytest suite |
| `scripts/` | benchmark, training and data collection |
| `docs/` | architecture and plan |

`autolyrics` is one namespace package spread over the projects; an editable install
(`pip install -e .`) puts every project folder on the path, so imports read
`autolyrics.domain…`, `autolyrics.application…` and so on.

## Install

Requirements: Python 3.12, [Bun](https://bun.sh), ffmpeg on `PATH`, and an NVIDIA GPU for
reasonable speed.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
.venv/Scripts/python -m pip install -e ".[ml,dev]"
.venv/Scripts/python -m pip install --no-deps audio-separator==0.47.0 swift-f0
cp .env.example .env
cd src/Autolyrics.Frontend && bun install && bun run build && cd ../..
.venv/Scripts/autolyrics serve        # http://localhost:8765
```

(`.venv/Scripts/` on Windows, `.venv/bin/` elsewhere.) `audio-separator` goes in without its
dependencies because it pins a torch release that would replace the CUDA build. The first song
downloads the models into `models/`: three RoFormer separation models (~0.9 GB), the singing
acoustic model (57 MB), MMS (~1.2 GB) and, only when needed, Whisper (~1.6 GB). Heavy work runs
below normal priority with a few CPU threads, so the desktop stays responsive.

## Command line

```bash
.venv/Scripts/autolyrics run "https://open.spotify.com/track/…"   # files end up in jobs/<id>/output
.venv/Scripts/autolyrics run <link> --transcribe                   # ignore lyrics sources, use Whisper
.venv/Scripts/autolyrics run <link> --lyrics my-lyrics.txt         # your own text, timed
```

## Frontend

```bash
cd src/Autolyrics.Frontend
bun run dev            # Vite with hot reload; /api is proxied to `autolyrics serve`
bun run test:unit      # unit tests (jsdom)
bun run test:component # component tests (Chromium via Playwright)
bun run typecheck
bun run lint:fix
```

## Tests

```bash
.venv/Scripts/python -m pytest
.venv/Scripts/ruff check .
```

## Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `AGENT_API_KEY`, `AGENT_BASE_URL`, `AGENT_MODEL` | OpenAI-compatible endpoint for DeepSeek (text clean-up only; never receives audio) |
| `APPLE_MUSIC_USER_TOKEN` | Apple Music lyrics with your own subscription (`media-user-token` cookie of music.apple.com) |
| `AUTOLYRICS_BOIDU_API_KEY` | Optional: lets the Better Lyrics and QQ sources answer songs they have not cached |
| `AUTOLYRICS_JOBS_DIR` | Where jobs are stored (default `jobs/`) |
| `AUTOLYRICS_SEPARATOR`, `AUTOLYRICS_ALIGNER` | `roformer` / `v2` (default) or the previous `demucs` / `mms` |
| `AUTOLYRICS_SEPARATION_OVERLAP` | 2 (default, fast) up to 8 (the models' own, ~3.5x slower) |
| `AUTOLYRICS_WHISPER_WITNESS` | Whisper as a second opinion on the text when all sources agree (off) |
| `AUTOLYRICS_MODELS_DIR` | Where model weights are kept (default `models/`) |

## Benchmark and training

| Script | What it does |
|---|---|
| `collect_benchmark.py` | Songs with hand-made syllable timing plus matching audio (`benchmarks/`, or chart songs into `training/`) |
| `separate_benchmark.py` | Separates the benchmark songs once |
| `benchmark_suite.py` | Word start, end and syllable errors of the pipeline per song |
| `fit_judge.py` | Calibrates the timing judge |
| `train_singing.py` | Fine-tunes the singing acoustic model (`prepare`, `train`, `install`) |
