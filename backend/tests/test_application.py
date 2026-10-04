"""Use cases end to end through the mediator, with fakes for the outside world."""

import asyncio

import pytest

from autolyrics.application.jobs.create_job import CreateJobCommand
from autolyrics.application.jobs.edit_commands import RealignLineCommand, SaveLyricsCommand
from autolyrics.application.jobs.notifications import JobEventRaised
from autolyrics.application.jobs.queries import GetJobFileQuery, GetJobQuery, GetLyricsQuery
from autolyrics.application.jobs.run_job import RunJobCommand
from autolyrics.domain.errors import InvalidInputError, JobStateError, NotFoundError
from autolyrics.domain.job import JobOptions, JobStatus
from autolyrics.domain.lyrics import SyncType
from tests.fakes import (
    CrashingProvider,
    FakeAligner,
    FakeContainer,
    FakeLlm,
    FakeMedia,
    FixtureProvider,
)


class Harness:
    def __init__(self, container):
        self.container = container
        self.mediator = container.mediator

    def run(self, coroutine):
        return asyncio.run(coroutine)

    async def process(self, url="https://open.spotify.com/track/x", **options):
        created = await self.mediator.send(CreateJobCommand(JobOptions(url=url, **options),
                                                            enqueue=False))
        return await self.mediator.send(RunJobCommand(created.id))


@pytest.fixture
def harness(tmp_path):
    return Harness(FakeContainer.build(tmp_path))


class TestPipeline:
    def test_line_synced_lyrics_get_aligned_and_exported(self, harness):
        result = harness.run(harness.process())
        assert result.status == JobStatus.DONE
        assert result.title == "Never Gonna Give You Up"
        assert result.sync == SyncType.WORD

        async def inspect():
            job = await harness.mediator.send(GetJobQuery(result.id))
            lyrics = await harness.mediator.send(GetLyricsQuery(result.id))
            ttml = await harness.mediator.send(GetJobFileQuery(result.id, "lyrics.ttml"))
            return job, lyrics, ttml

        job, lyrics, ttml = harness.run(inspect())
        stages = [(e.stage.value, e.status.value) for e in job.events if e.status.value != "running"]
        assert stages == [("resolve", "done"), ("audio", "done"), ("lyrics", "done"),
                          ("polish", "skipped"), ("align", "done"), ("export", "done")]
        assert lyrics.lines[0].text == "We're no strangers to love"
        assert all(w.timed for w in lyrics.all_words)
        assert ttml.download_name == "Rick Astley - Never Gonna Give You Up.ttml"
        assert job.report["alignment"]["mode"] == "global"
        assert harness.container.aligner.released == 1

    def test_word_synced_source_is_offset_checked_and_shifted(self, tmp_path):
        container = FakeContainer.build(
            tmp_path, providers=[FixtureProvider("boidu", "ttml", "rick.ttml", SyncType.SYLLABLE)],
            aligner=FakeAligner(offset=0.81))
        harness = Harness(container)
        result = harness.run(harness.process())
        lyrics = harness.run(harness.mediator.send(GetLyricsQuery(result.id)))
        assert result.status == JobStatus.DONE
        assert lyrics.lines[0].words[0].begin == pytest.approx(18.893 + 0.81)
        report = harness.run(harness.mediator.send(GetJobQuery(result.id))).report
        assert report["offset_check"]["applied"] is True

    def test_a_crashing_provider_does_not_sink_the_search(self, tmp_path):
        container = FakeContainer.build(tmp_path, providers=[
            CrashingProvider(), FixtureProvider("lrclib", "lrc", "rick.lrc", SyncType.LINE, 212.0)])
        harness = Harness(container)
        assert harness.run(harness.process()).status == JobStatus.DONE

    def test_no_lyrics_fails_the_job_at_align(self, tmp_path):
        harness = Harness(FakeContainer.build(tmp_path, providers=[]))
        result = harness.run(harness.process())
        assert result.status == JobStatus.FAILED
        assert result.error.startswith("align:")

    def test_resolve_failure_fails_the_job(self, tmp_path):
        harness = Harness(FakeContainer.build(tmp_path, media=FakeMedia(fail=True)))
        result = harness.run(harness.process())
        assert result.status == JobStatus.FAILED
        assert "ArgonFetch is down" in result.error

    def test_llm_answer_is_applied_before_alignment(self, tmp_path):
        llm = FakeLlm({"language": "en", "remove_lines": [{"line": 0, "reason": "test"}]})
        container = FakeContainer.build(tmp_path, llm=llm)
        harness = Harness(container)
        result = harness.run(harness.process())
        lyrics = harness.run(harness.mediator.send(GetLyricsQuery(result.id)))
        assert lyrics.lines[0].text == "You know the rules and so do I"
        assert lyrics.metadata.language == "en"
        assert "Current lyrics" in llm.prompts[0]

    def test_events_reach_extra_notification_handlers(self, tmp_path):
        container = FakeContainer.build(tmp_path)
        seen = []

        class Recorder:
            async def handle(self, notification):
                seen.append(notification.event.stage.value)

        container.on(JobEventRaised, Recorder, Recorder)
        harness = Harness(container)
        harness.run(harness.process())
        assert seen[0] == "resolve" and seen[-1] == "export"


class TestEditing:
    def test_save_realign_and_guards(self, harness):
        result = harness.run(harness.process())

        async def edit():
            lyrics = await harness.mediator.send(GetLyricsQuery(result.id))
            lyrics.lines[0].words[0].text = "Were "
            saved = await harness.mediator.send(SaveLyricsCommand(result.id, lyrics))
            realigned = await harness.mediator.send(
                RealignLineCommand(result.id, 1, text="You know the rules (and so do I)"))
            return saved, realigned

        saved, realigned = harness.run(edit())
        assert saved.files["ttml"] == "lyrics.ttml"
        assert realigned.aligned
        assert [w["text"].strip() for w in realigned.line["background"]] == ["and", "so", "do",
                                                                              "I"]
        assert harness.container.aligner.realigned

        with pytest.raises(NotFoundError):
            harness.run(harness.mediator.send(RealignLineCommand(result.id, 999)))
        with pytest.raises(InvalidInputError):
            harness.run(harness.mediator.send(RealignLineCommand(result.id, 0, text="  ")))

    def test_unfinished_jobs_cannot_be_edited(self, harness):
        created = harness.run(harness.mediator.send(
            CreateJobCommand(JobOptions(url="https://x"), enqueue=False)))
        with pytest.raises(JobStateError):
            harness.run(harness.mediator.send(RealignLineCommand(created.id, 0)))
