import string

import pytest

from autolyrics.domain.errors import JobNotFoundError
from autolyrics.domain.job import JobOptions, JobStatus
from autolyrics.infrastructure.llm.openai_compatible_client import JsonReply
from autolyrics.infrastructure.media.argonfetch import YouTubeLink
from autolyrics.infrastructure.ml.text_normalizer import AlignmentTextNormalizer
from autolyrics.infrastructure.persistence.file_job_repository import FileJobRepository


class TestYouTubeLink:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://www.youtube.com/watch?v=abc123&t=4", "abc123"),
            ("https://music.youtube.com/watch?v=lYBUbBu4W08", "lYBUbBu4W08"),
            ("https://youtu.be/xyz", "xyz"),
            ("https://www.youtube.com/shorts/s1", "s1"),
            ("https://open.spotify.com/track/4PTG3Z6ehGkBFwjybzWkR8", None),
            (None, None),
        ],
    )
    def test_video_id(self, url, expected):
        assert YouTubeLink.video_id(url) == expected


class TestAlignmentTextNormalizer:
    @pytest.mark.parametrize(
        ("word", "language", "expected"),
        [
            ("Größe,", "de", "grosse"),
            ("Wellensteyn-Jacken", "de", "wellensteynjacken"),
            ("187", "de", "hundertsiebenundachtzig"),
            ("I'm", "en", "i'm"),
            ("don’t", "en", "don't"),
            ("&", "de", "und"),
            ("—", "de", ""),
            ("Çok", "tr", "cok"),
        ],
    )
    def test_normalize(self, word, language, expected):
        normalizer = AlignmentTextNormalizer(set(string.ascii_lowercase) | {"'"})
        assert normalizer.normalize(word, language) == expected


class TestJsonReply:
    def test_tolerates_fences(self):
        assert JsonReply('Sure!\n```json\n{"a": 1}\n```').parse() == {"a": 1}
        with pytest.raises(ValueError):
            JsonReply("no json here").parse()


class TestFileJobRepository:
    def test_identity_map_and_persistence(self, tmp_path):
        repository = FileJobRepository(tmp_path)
        job = repository.create(JobOptions(url="https://x"), job_id="song")
        assert repository.get("song") is job
        job.title = "Song"
        repository.save(job)

        reopened = FileJobRepository(tmp_path)
        assert reopened.get("song").title == "Song"
        assert [j.id for j in reopened.list()] == ["song"]

    def test_running_jobs_from_an_earlier_process_are_interrupted(self, tmp_path):
        repository = FileJobRepository(tmp_path)
        job = repository.create(JobOptions(url="https://x"), job_id="song")
        job.start()
        repository.save(job)
        import os
        import time

        long_ago = time.time() - 3600  # the process that ran it is gone
        os.utime(tmp_path / "song" / "job.json", (long_ago, long_ago))
        stale = FileJobRepository(tmp_path).get("song")
        assert stale.status == JobStatus.FAILED
        assert stale.error == "interrupted"

    def test_rejects_path_tricks(self, tmp_path):
        repository = FileJobRepository(tmp_path)
        for bad in ("..", "a/b", "a\\b", ""):
            with pytest.raises(JobNotFoundError):
                repository.get(bad)


class TestJapanese:
    def test_romaji_reads_kanji_as_japanese(self):
        from autolyrics.infrastructure.ml.japanese_text import JapaneseText

        normalizer = AlignmentTextNormalizer(set(string.ascii_lowercase) | {"'"}, JapaneseText())
        assert normalizer.normalize("太陽", "ja") == "taiyou"
        assert normalizer.normalize("Spinning", "ja") == "spinning"

    def test_segmenter_splits_words_and_keeps_the_display(self):
        from autolyrics.domain.lyrics import Line, Lyrics, Word
        from autolyrics.infrastructure.ml.japanese_text import JapaneseText, WordSegmenter

        line = Line(words=Word.tokenize("ハエの羽音 振り払い"))
        lyrics = Lyrics(lines=[line])
        assert WordSegmenter(JapaneseText()).segment(lyrics, "ja") == 2
        assert [w.text for w in line.words] == ["ハエ", "の", "羽音 ", "振り", "払い"]
        assert line.text == "ハエの羽音 振り払い"
        assert WordSegmenter(JapaneseText()).segment(Lyrics(lines=[line]), "de") == 0


class TestRepositoryFreshness:
    def test_a_job_rewritten_by_another_process_is_reloaded(self, tmp_path):
        import os
        import time

        server = FileJobRepository(tmp_path)
        cli = FileJobRepository(tmp_path)
        job = server.create(JobOptions(url="https://x"), job_id="song")
        job.fail("audio: dropped")
        server.save(job)

        rerun = cli.get("song")
        rerun.finish()
        rerun.title = "Done elsewhere"
        cli.save(rerun)
        path = tmp_path / "song" / "job.json"
        later = time.time() + 5
        os.utime(path, (later, later))

        assert server.get("song").status == JobStatus.DONE
        assert server.list()[0].title == "Done elsewhere"

    def test_a_running_job_is_not_overwritten_from_disk(self, tmp_path):
        import os
        import time

        repository = FileJobRepository(tmp_path)
        job = repository.create(JobOptions(url="https://x"), job_id="song")
        job.start()
        repository.save(job)
        path = tmp_path / "song" / "job.json"
        later = time.time() + 5
        os.utime(path, (later, later))
        assert repository.get("song") is job


class TestVocalActivity:
    def test_pieces_follow_singing_and_never_exceed_the_limit(self):
        import numpy as np

        from autolyrics.infrastructure.ml.vocal_activity import VocalActivity

        rate = 16000
        rng = np.random.default_rng(0)
        silence = np.zeros(rate * 5)
        sung = lambda seconds: rng.normal(0, 0.3, int(rate * seconds))
        # 5 s silence, 4 s singing, 5 s silence, 70 s continuous singing, 3 s silence
        audio = np.concatenate([silence, sung(4), silence, sung(70), np.zeros(rate * 3)])
        pieces = VocalActivity(sample_rate=rate).pieces(audio)
        starts = [p.start / rate for p in pieces]
        assert 4.5 < starts[0] < 5.0
        assert all((p.end - p.start) / rate <= 28.0 + 1e-6 for p in pieces)
        covered = sum(p.end - p.start for p in pieces) / rate
        assert covered >= 74  # every sung second is in some piece
        assert VocalActivity(sample_rate=rate).pieces(np.zeros(rate * 10)) == []


class TestRepositoryAcrossProcesses:
    def test_a_job_another_process_runs_is_followed_to_the_end(self, tmp_path):
        import os
        import time

        server = FileJobRepository(tmp_path)
        cli = FileJobRepository(tmp_path)
        job = cli.create(JobOptions(url="https://x"), job_id="song")
        job.start()
        cli.save(job)
        assert server.get("song").status == JobStatus.RUNNING  # fresh file: not "interrupted"

        job.finish()
        cli.save(job)
        path = tmp_path / "song" / "job.json"
        later = time.time() + 5
        os.utime(path, (later, later))
        assert server.get("song").status == JobStatus.DONE


class TestLateLineStart:
    @staticmethod
    def _line(first_begin: float):
        from autolyrics.domain.lyrics import Line, Word

        return Line(begin=35.27, end=37.37, words=[
            Word(text="Echo ", begin=first_begin, end=37.6, confidence=0.5),
            Word(text="the ", begin=37.6, end=37.84, confidence=0.5)])

    def test_a_first_word_heard_late_starts_where_the_source_says(self):
        from autolyrics.infrastructure.ml.mms_lyrics_aligner import MmsLyricsAligner

        aligner = object.__new__(MmsLyricsAligner)
        line = self._line(36.12)
        aligner._pull_late_start(line, 0.0, previous_end=35.13)
        assert line.words[0].begin == 35.27
        assert line.words[0].end == 37.6

    def test_never_into_the_previous_line_and_small_gaps_stay(self):
        from autolyrics.infrastructure.ml.mms_lyrics_aligner import MmsLyricsAligner

        aligner = object.__new__(MmsLyricsAligner)
        line = self._line(36.12)
        aligner._pull_late_start(line, 0.0, previous_end=35.9)
        assert line.words[0].begin == 36.12  # only 0.22 s after the previous line: stays
        line = self._line(35.5)
        aligner._pull_late_start(line, 0.0, previous_end=0.0)
        assert line.words[0].begin == 35.5

    def test_a_line_running_into_the_next_is_squeezed_into_its_span(self):
        from autolyrics.domain.lyrics import Line, Word
        from autolyrics.infrastructure.ml.mms_lyrics_aligner import MmsLyricsAligner

        aligner = object.__new__(MmsLyricsAligner)
        echo = Line(begin=35.27, end=37.37, words=[
            Word(text="Echo ", begin=35.27, end=37.6), Word(text="the ", begin=37.6, end=37.84),
            Word(text="sound", begin=37.84, end=38.36)])
        after = Line(begin=37.6, end=39.39, words=[Word(text="Can't", begin=37.46, end=37.64)])
        aligner._fit_overruns([echo, after], [0.0, 0.0])
        assert echo.words[0].begin == 35.27
        assert echo.words[-1].end == 37.37
        assert echo.words[0].end < echo.words[1].begin + 1e-9 < echo.words[2].begin


class TestAppleMusicProvider:
    UNSYNCED = ('<tt xmlns="http://www.w3.org/ns/ttml" '
                'xmlns:itunes="http://music.apple.com/lyric-ttml-internal" itunes:timing="None">'
                '<body><div><p>Yo, link up to the master, we live!</p>'
                '<p>We here for a reason right now</p></div></body></tt>')

    @staticmethod
    def _transport(seen: list):
        import httpx

        def handle(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            path = request.url.path
            if path == "/us/browse":
                return httpx.Response(200, text='<script src="/assets/index~abc123.js">')
            if path == "/assets/index~abc123.js":
                return httpx.Response(200, text='x="eyJ0eXAiOiJKV1Qi.eyJpc3Mi.c2lnbmF0dXJl"')
            if path == "/v1/me/storefront":
                return httpx.Response(200, json={"data": [{"id": "ch"}]})
            if path == "/v1/catalog/ch/search":
                return httpx.Response(200, json={"results": {"songs": {"data": [
                    {"id": "680", "attributes": {"name": "NEW & LOUDER", "artistName": "Paper Skies",
                                                 "durationInMillis": 152274, "hasLyrics": True,
                                                 "hasTimeSyncedLyrics": False}}]}}})
            if path == "/v1/catalog/ch/songs/680/lyrics":
                return httpx.Response(200, json={"data": [
                    {"attributes": {"ttml": TestAppleMusicProvider.UNSYNCED}}]})
            return httpx.Response(404)
        return httpx.MockTransport(handle)

    def test_reads_the_account_lyrics_with_the_user_token(self, ttml):
        import asyncio

        import httpx

        from autolyrics.domain.candidate import LyricsQuery
        from autolyrics.domain.lyrics import SyncType
        from autolyrics.infrastructure.providers.apple_music import AppleMusicProvider

        seen: list = []

        async def run():
            async with httpx.AsyncClient(transport=self._transport(seen)) as client:
                provider = AppleMusicProvider(client, "user-token")
                return await provider.search(LyricsQuery(track="NEW & LOUDER",
                                                         artist="Paper Skies"))

        [candidate] = asyncio.run(run())
        assert candidate.declared_sync == SyncType.UNSYNCED
        assert candidate.duration == 152.274 and candidate.label == "Apple Music"
        api = [r for r in seen if r.url.host == "amp-api.music.apple.com"]
        assert all(r.headers["media-user-token"] == "user-token" for r in api)
        assert all(r.headers["authorization"] == "Bearer eyJ0eXAiOiJKV1Qi.eyJpc3Mi.c2lnbmF0dXJl"
                   for r in api)
        lyrics = ttml.parse(candidate.content)
        assert lyrics.lines[0].display == "Yo, link up to the master, we live!"

    def test_stays_silent_without_a_user_token(self):
        import asyncio

        import httpx

        from autolyrics.domain.candidate import LyricsQuery
        from autolyrics.infrastructure.providers.apple_music import AppleMusicProvider

        seen: list = []

        async def run():
            async with httpx.AsyncClient(transport=self._transport(seen)) as client:
                return await AppleMusicProvider(client, None).search(
                    LyricsQuery(track="x", artist="y"))

        assert asyncio.run(run()) == [] and seen == []


class TestWhisperWords:
    def test_ghost_words_are_dropped_and_lines_break_at_pauses_and_sentence_ends(self):
        from autolyrics.infrastructure.ml.whisper_transcriber import WhisperTranscriber

        whisper = object.__new__(WhisperTranscriber)
        result = {"chunks": [
            {"text": " I", "timestamp": (0.0, 0.3)}, {"text": " need", "timestamp": (0.3, 0.5)},
            {"text": " you!", "timestamp": (0.5, 0.9)},
            {"text": " I", "timestamp": (0.9, 0.9)},  # Whisper repeating itself
            {"text": " Higher", "timestamp": (1.0, 1.4)},
            {"text": " Louder", "timestamp": (2.5, 3.0)}]}
        lyrics = whisper._to_lyrics([whisper._heard_words(result, 10.0)], 60.0)
        assert [line.display for line in lyrics.lines] == ["I need you!", "Higher", "Louder"]
        first = lyrics.lines[0]
        assert (first.begin, first.end) == (10.0, 10.9)
        assert [w.begin for w in first.words] == [10.0, 10.3, 10.5]
