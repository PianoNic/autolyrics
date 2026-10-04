# Backend architecture

Onion / clean architecture. Dependencies point inwards only; every class gets its collaborators
through its constructor, and one composition root wires them. Use cases are
[mediatorx](https://pypi.org/project/mediatorx/) commands, queries and notifications.

```
presentation ──► application ──► domain
      │               ▲
      ▼               │ implements ports
 composition ──► infrastructure
```

| Layer | Package | Contents |
|---|---|---|
| Domain | `autolyrics.domain` | Entities (`Lyrics`, `Line`, `Word`, `Job`, `Track`, `LyricsCandidate`) and pure services (`CandidateSelector`, `SourceComparer`, `DecisionApplier`, `TimingRepairer`, `OffsetEstimator`, `LyricsValidator`, …). No I/O. |
| Application | `autolyrics.application` | Ports (`interfaces/`: abstract classes the outside world implements), the pipeline (one command + handler per stage), job use cases (create, run, query, edit, delete), notifications and the logging behavior. |
| Infrastructure | `autolyrics.infrastructure` | Adapters: ArgonFetch, the four lyrics providers, ffmpeg, Demucs, the MMS aligner, the OpenAI-compatible LLM client, file formats, the file job repository, the event broadcaster and the job queue. |
| Presentation | `autolyrics.presentation` | FastAPI controllers (class-based, via the vendored `controller` decorator) and the CLI. They only send mediator messages. |
| Composition | `autolyrics.composition` | `Container`: builds every object and registers each handler with the mediator through a `DictResolver`. |

## Flow of a job

`CreateJobCommand` stores the job and queues it. The `AsyncJobQueue` worker sends `RunJobCommand`,
whose handler sends one command per stage through the mediator:

`ResolveTrackCommand → FetchAudioCommand → FindLyricsCommand → PolishLyricsCommand →
AlignLyricsCommand → FinalizeLyricsCommand`

Stages report progress through `StageReporter`, which publishes `JobEventRaised` notifications.
Handlers record them on the job (`RecordJobEventHandler`) and fan them out to open event streams
(`BroadcastJobEventHandler`); the CLI adds a `ConsoleProgressPrinter`.

The job repository is an identity map: one `Job` instance per id, so the stages and the
notification handlers update the same object.

## Timing engine (pipeline v2)

`infrastructure/ml/singing/` holds the engine; `AUTOLYRICS_SEPARATOR=demucs` and
`AUTOLYRICS_ALIGNER=mms` switch back to the previous one.

| Piece | Role |
|---|---|
| `RoformerVocalSeparator` (`ml/roformer_separator.py`) | `VocalStems`: all vocals, dry lead, backing |
| `IAcousticModel` → `SingingPhonemeModel`, `MmsCharacterModel` | token probabilities per frame; words → tokens |
| `GlobalCtcSolver` | one Viterbi over the song; soft line pull and window; optional gaps |
| `VocalAnalyzer` → `VocalEvents` | SwiftF0 voicing, loudness, pitch, notes |
| `TimingJudge` + `WordEvidence` | calibrated "timing is right" probability per word |
| `RepeatMemory` | doubtful chorus repeats borrow the rhythm of trusted ones |
| `SyllableTimer` + `Syllabifier` | words split into syllables timed from their vowels |
| `SingingLyricsAligner` | orchestrates the above behind `ILyricsAligner` |

Benchmarking lives in `scripts/`: `collect_benchmark.py` (songs with hand-made syllable timing),
`separate_benchmark.py`, `benchmark_suite.py` and `fit_judge.py`.

## HTTP API

| Method | Path | Message |
|---|---|---|
| GET | `/api/health` | – |
| POST | `/api/jobs` | `CreateJobCommand` |
| GET | `/api/jobs` | `ListJobsQuery` |
| GET | `/api/jobs/{id}` | `GetJobQuery` |
| DELETE | `/api/jobs/{id}` | `DeleteJobCommand` |
| GET | `/api/jobs/{id}/events` | history + live progress (Server-Sent Events) |
| GET / PUT | `/api/jobs/{id}/lyrics` | `GetLyricsQuery` / `SaveLyricsCommand` |
| PUT | `/api/jobs/{id}/ttml` | `ImportTtmlCommand` (save from the Composer editor) |
| POST | `/api/jobs/{id}/lines/{index}/realign` | `RealignLineCommand` |
| GET | `/api/jobs/{id}/audio` | `GetJobAudioQuery` |
| GET | `/api/jobs/{id}/files/{name}` | `GetJobFileQuery` |

## Tests

`tests/fakes.py` replaces every port that touches the network, the GPU or ffmpeg, so
`test_application.py` and `test_api.py` run whole jobs in milliseconds. `scripts/benchmark_align.py`
measures the real aligner against songs with known word timing.
