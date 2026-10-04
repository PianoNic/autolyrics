"""The HTTP API: class-based controllers, the background worker and the event stream."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from autolyrics.api.api_application import ApiApplication
from fakes import FakeContainer


@pytest.fixture
def client(tmp_path):
    app = ApiApplication(FakeContainer.build(tmp_path / "jobs"),
                         frontend_dist=tmp_path / "no-frontend").build()
    with TestClient(app) as test_client:
        yield test_client


class ApiFlow:
    def __init__(self, client: TestClient):
        self.client = client

    def create_and_wait(self) -> dict:
        created = self.client.post("/api/jobs", json={"url": "https://open.spotify.com/track/x"})
        assert created.status_code == 201
        job_id = created.json()["id"]
        for _ in range(100):
            job = self.client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in ("done", "failed"):
                return job
            time.sleep(0.05)
        raise AssertionError("job did not finish")


class TestJobsApi:
    def test_health(self, client):
        body = client.get("/api/health").json()
        assert body["ok"] is True and body["llm"] is False

    def test_create_run_and_fetch(self, client):
        job = ApiFlow(client).create_and_wait()
        assert job["status"] == "done", job
        assert job["title"] == "Never Gonna Give You Up"
        assert job["report"]["chosen"]["source"] == "lrclib"

        listed = client.get("/api/jobs").json()
        assert [j["id"] for j in listed] == [job["id"]]

        lyrics = client.get(f"/api/jobs/{job['id']}/lyrics").json()
        assert lyrics["lines"][0]["words"][0]["begin"] is not None

        ttml = client.get(f"/api/jobs/{job['id']}/files/lyrics.ttml")
        assert ttml.status_code == 200
        assert "Rick%20Astley%20-%20Never%20Gonna%20Give%20You%20Up.ttml" in ttml.headers["content-disposition"]
        assert client.get(f"/api/jobs/{job['id']}/files/secrets.txt").status_code == 404
        assert client.get(f"/api/jobs/{job['id']}/audio").content == b"audio"

    def test_event_stream_replays_a_finished_job(self, client):
        job = ApiFlow(client).create_and_wait()
        with client.stream("GET", f"/api/jobs/{job['id']}/events") as response:
            assert response.headers["content-type"].startswith("text/event-stream")
            payloads = [json.loads(line[6:]) for line in response.iter_lines()
                        if line.startswith("data: ")]
        assert payloads[0] == {"type": "status", "status": "done", "error": None}
        stages = [p["event"]["stage"] for p in payloads[1:] if p["event"]["status"] == "done"]
        assert stages == ["resolve", "audio", "lyrics", "align", "export"]

    def test_editing_endpoints(self, client):
        job_id = ApiFlow(client).create_and_wait()["id"]
        lyrics = client.get(f"/api/jobs/{job_id}/lyrics").json()
        lyrics["lines"][0]["words"][0]["text"] = "Were "
        saved = client.put(f"/api/jobs/{job_id}/lyrics", json=lyrics)
        assert saved.status_code == 200 and saved.json()["sync"] == "word"
        assert client.get(f"/api/jobs/{job_id}/lyrics").json()["lines"][0]["words"][0][
            "text"] == "Were "

        realigned = client.post(f"/api/jobs/{job_id}/lines/2/realign",
                                json={"text": "A full commitment"})
        assert realigned.status_code == 200 and realigned.json()["aligned"]

        ttml = client.get(f"/api/jobs/{job_id}/files/lyrics.ttml").text
        imported = client.put(f"/api/jobs/{job_id}/ttml", content=ttml,
                              headers={"content-type": "application/ttml+xml"})
        assert imported.status_code == 200
        bad = client.put(f"/api/jobs/{job_id}/ttml", content="<nope",
                         headers={"content-type": "application/ttml+xml"})
        assert bad.status_code == 400

    def test_errors_and_delete(self, client):
        assert client.get("/api/jobs/missing").status_code == 404
        assert client.post("/api/jobs", json={"url": " "}).status_code == 400
        job_id = ApiFlow(client).create_and_wait()["id"]
        assert client.delete(f"/api/jobs/{job_id}").status_code == 204
        assert client.get(f"/api/jobs/{job_id}").status_code == 404
