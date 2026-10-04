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
        stale = FileJobRepository(tmp_path).get("song")
        assert stale.status == JobStatus.FAILED
        assert stale.error == "interrupted"

    def test_rejects_path_tricks(self, tmp_path):
        repository = FileJobRepository(tmp_path)
        for bad in ("..", "a/b", "a\\b", ""):
            with pytest.raises(JobNotFoundError):
                repository.get(bad)
