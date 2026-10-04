<p align="center">
  <img src="assets/logo.svg" width="140" alt="autolyrics Logo">
</p>

<p align="center">
  <strong>Paste a song link, get word- and syllable-synced lyrics. No syncing by hand.</strong>
</p>

<p align="center">
  <a href="https://github.com/PianoNic/autolyrics"><img src="https://badgetrack.pianonic.ch/badge?tag=autolyrics&label=visits&color=818cf8&style=flat" alt="visits"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-AGPL--3.0-818cf8.svg" alt="AGPL-3.0"/></a>
  <a href="docs/development.md"><img src="https://img.shields.io/badge/Development-Setup-818cf8.svg" alt="Development"/></a>
  <img src="https://img.shields.io/badge/Python-3.12-818cf8.svg" alt="Python 3.12"/>
  <img src="https://img.shields.io/badge/React-19-818cf8.svg" alt="React 19"/>
</p>

---

> **Heads up:** autolyrics is in early development and runs on your own machine. It is meant for
> personal use: lyrics and audio come from third-party sources.

## What is autolyrics?

Apple Music style lyrics, where every word and syllable lights up exactly when it is sung, are made
by hand. autolyrics makes them from a song link: it finds the lyrics, isolates the vocals, listens
to them with a model trained on singing and times every word and syllable. Where it is unsure, it
says so, and the result opens on a timeline where you drag a word to fix it.

Everything runs locally: a Python backend and a web editor based on
[Composer](https://github.com/better-lyrics/composer). Measured on 18 songs with hand-made syllable
timing, a word starts on average **0.066 s** from where a person put it, 98% within 300 ms.

## Features

- **Any song link**: Spotify, YouTube, SoundCloud and more, resolved through
  [ArgonFetch](https://app.argonfetch.dev).
- **Lyrics from several sources at once**: the first word-synced one that fits the recording ends
  the search; Apple Music with your own subscription, and pasted lyrics, work too.
- **Clean vocals**: RoFormer separation, lead split from backing vocals, reverb and echo removed.
- **A singing aligner**: one global solve over the whole song with a phoneme model trained on
  singing; line times from a source pull softly and live takes that drift are followed.
- **Words that last as long as they are sung**: word ends follow the voice, and words split into
  syllables where each one is heard.
- **A timing judge**: every word gets a calibrated confidence; doubtful ones are flagged for review
  instead of being patched.
- **Ad-libs and choruses**: background vocals stay with their line, repeated choruses share their
  rhythm.
- **Many languages**: English, German, French, Spanish and Italian with the singing model;
  Japanese, Korean, Chinese and Russian through MMS.
- **DeepSeek clean-up**: where sources disagree on the text, DeepSeek picks; it never sees audio.
- **Exports**: TTML (Apple / Better Lyrics), LRC, enhanced LRC, SRT and QRC.

## Quick start

Requirements: Python 3.12, Bun, ffmpeg and an NVIDIA GPU (CPU works, slowly).

```bash
python -m venv .venv
.venv/Scripts/python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128
.venv/Scripts/python -m pip install -e ".[ml,dev]"
.venv/Scripts/python -m pip install --no-deps audio-separator==0.47.0 swift-f0
cp .env.example .env                       # fill in AGENT_API_KEY for DeepSeek
cd src/Autolyrics.Frontend && bun install && bun run build && cd ../..
.venv/Scripts/autolyrics serve
```

Open <http://localhost:8765>.

## Get started

- 🛠️ **[Development setup](docs/development.md)** - install, configuration, command line, frontend.
- 🧱 **[Architecture](docs/ARCHITECTURE.md)** - layers, the job flow and the timing engine.
- 📈 **[Plan and benchmark](docs/PLAN.md)** - what is done and how it measures.

## Credits

[Composer](https://github.com/better-lyrics/composer) by Better Lyrics (the editor),
[Spicy Lyrics](https://github.com/Spikerko/spicy-lyrics) by Spikerko (the preview, with
[spr](https://github.com/Fraktality/spr) by Fraktality),
[LyricsAlignment-Multilingual](https://github.com/jhuang448/LyricsAlignment-Multilingual) by
Jiawen Huang and Emmanouil Benetos (the singing model),
[python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator) and the RoFormer
model authors, [SwiftF0](https://github.com/lars76/swift-f0), MMS (Meta) and Whisper (OpenAI).
Not affiliated with Better Lyrics or Spicy Lyrics.

## License

[AGPL-3.0](LICENSE), as the Composer and Spicy Lyrics code it builds on. Model weights keep their
own licenses, some of them noncommercial.

---

<p align="center">Made by <a href="https://github.com/PianoNic">PianoNic</a></p>
