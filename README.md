# autolyrics

Paste a song link, get word-synced lyrics (TTML, LRC, SRT, QRC) without syncing by hand.

Everything runs on your own machine. A local Python backend fetches the song, finds its lyrics,
times every word against the isolated vocals and has DeepSeek do the final text clean-up. A local
web frontend starts jobs, shows progress and lets you review the result. If you want to adjust
something, the full Composer editor (timeline, syllable splitting, agents, live preview) is one
click away, but you never have to open it.

Based on [Composer](https://github.com/better-lyrics/composer) by Better Lyrics, AGPL-3.0.

## Layout

| Folder | What it is |
|---|---|
| `backend/` | Python package `autolyrics`: the pipeline, a CLI and (later) the local API server |
| `frontend/` | React app forked from Composer: the automatic flow plus the optional editor |
| `PLAN.md` | Architecture and build order |

## Requirements

- Python 3.12, an NVIDIA GPU with CUDA for Demucs and WhisperX (CPU works, slowly)
- ffmpeg on `PATH`
- Node 24 and pnpm for the frontend
- A DeepSeek API key for the clean-up step (only lyrics text is sent, never audio)

## Credits

- [Composer](https://github.com/better-lyrics/composer) by Better Lyrics (AGPL-3.0): the editor
  this frontend is forked from.
- [Spicy Lyrics](https://github.com/Spikerko/spicy-lyrics) by Spikerko (AGPL-3.0): the default
  Preview renderer in `frontend/src/views/preview/spicy/` is adapted from its lyric layout,
  animator and styles. Its spring model is in turn a port of
  [spr](https://github.com/Fraktality/spr) by Fraktality (MIT).

## License

AGPL-3.0, see `LICENSE`.
