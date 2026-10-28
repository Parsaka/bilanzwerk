from __future__ import annotations

import hashlib

import responses

from ingestion.common.http import PoliteSession


@responses.activate
def test_retries_on_503_and_declares_user_agent(settings, tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    url = "https://example.test/file.zip"
    responses.get(url, status=503)
    responses.get(url, body=b"payload")
    session = PoliteSession(settings)
    session.get.retry.sleep = lambda s: None
    digest, size = session.download(url, tmp_path / "f.zip")
    assert size == 7 and digest == hashlib.sha256(b"payload").hexdigest()
    assert len(responses.calls) == 2
    assert responses.calls[0].request.headers["User-Agent"] == "Bilanzwerk test test@example.com"
    assert not (tmp_path / "f.zip.part").exists()
