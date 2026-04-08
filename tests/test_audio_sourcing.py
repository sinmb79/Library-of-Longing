from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.audio_sourcing.freesound_fetcher import (
    cache_locally,
    download_sound,
    search_cc0,
)


class FakeResponse:
    def __init__(self, payload: dict | None = None, *, content: bytes = b"", status_code: int = 200) -> None:
        self._payload = payload or {}
        self.content = content
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, routes: dict[str, list[FakeResponse]]) -> None:
        self.routes = {url: list(responses) for url, responses in routes.items()}
        self.calls: list[tuple[str, str, dict | None, dict | None]] = []

    def get(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        timeout: int | float | None = None,
        stream: bool | None = None,
    ) -> FakeResponse:
        self.calls.append(("GET", url, params, headers))
        responses = self.routes.get(url)
        if not responses:
            raise AssertionError(f"Unexpected GET {url}")
        return responses.pop(0)


def _write_credentials(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "client_id": "demo-client",
                "api_key": "demo-key",
                "name": "Library of Longing",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_search_cc0_adds_license_and_duration_filters(tmp_path: Path) -> None:
    credentials_path = _write_credentials(tmp_path / "freesound.json")
    search_url = "https://freesound.org/apiv2/search/"
    session = FakeSession(
        {
            search_url: [
                FakeResponse(
                    {
                        "results": [
                            {
                                "id": 111,
                                "name": "Cicadas Close",
                                "username": "recordist",
                                "license": "http://creativecommons.org/publicdomain/zero/1.0/",
                                "duration": 6.5,
                                "type": "wav",
                                "url": "https://freesound.org/people/recordist/sounds/111/",
                                "previews": {"preview-hq-mp3": "https://cdn.example.com/111.mp3"},
                            },
                            {
                                "id": 222,
                                "name": "Wrong License",
                                "username": "other",
                                "license": "Attribution",
                                "duration": 5.0,
                                "type": "wav",
                                "url": "https://freesound.org/people/other/sounds/222/",
                                "previews": {"preview-hq-mp3": "https://cdn.example.com/222.mp3"},
                            },
                        ]
                    }
                )
            ]
        }
    )

    results = search_cc0(
        "cicada breeze",
        min_duration=4,
        max_duration=8,
        max_results=5,
        credentials_path=credentials_path,
        session=session,
    )

    assert [item["sound_id"] for item in results] == [111]
    assert results[0]["license"] == "Creative Commons 0"
    assert results[0]["download_mode"] == "preview-hq-mp3"

    method, url, params, headers = session.calls[0]
    assert method == "GET"
    assert url == search_url
    assert params is not None
    assert params["query"] == "cicada breeze"
    assert 'license:"Creative Commons 0"' in params["filter"]
    assert "duration:[4 TO 8]" in params["filter"]
    assert params["page_size"] == 5
    assert params["token"] == "demo-key"
    assert headers is None


def test_download_sound_refuses_non_cc0_sources(tmp_path: Path) -> None:
    credentials_path = _write_credentials(tmp_path / "freesound.json")
    detail_url = "https://freesound.org/apiv2/sounds/333/"
    session = FakeSession(
        {
            detail_url: [
                FakeResponse(
                    {
                        "id": 333,
                        "name": "Not Allowed",
                        "username": "other",
                        "license": "Attribution",
                        "type": "wav",
                        "url": "https://freesound.org/people/other/sounds/333/",
                        "previews": {"preview-hq-mp3": "https://cdn.example.com/333.mp3"},
                    }
                )
            ]
        }
    )

    with pytest.raises(ValueError, match="Creative Commons 0"):
        download_sound(333, tmp_path / "blocked.wav", credentials_path=credentials_path, session=session)

    assert len(session.calls) == 1


def test_download_sound_falls_back_to_preview_when_oauth_is_missing(tmp_path: Path) -> None:
    credentials_path = _write_credentials(tmp_path / "freesound.json")
    detail_url = "https://freesound.org/apiv2/sounds/444/"
    preview_url = "https://cdn.example.com/444.mp3"
    session = FakeSession(
        {
            detail_url: [
                FakeResponse(
                    {
                        "id": 444,
                        "name": "Cicadas W breeze",
                        "username": "recordist",
                        "license": "http://creativecommons.org/publicdomain/zero/1.0/",
                        "type": "wav",
                        "url": "https://freesound.org/people/recordist/sounds/444/",
                        "previews": {"preview-hq-mp3": preview_url},
                    }
                )
            ],
            preview_url: [FakeResponse(content=b"preview-audio")],
        }
    )

    destination = download_sound(
        444,
        tmp_path / "cicadas.mp3",
        credentials_path=credentials_path,
        session=session,
    )

    assert destination.read_bytes() == b"preview-audio"
    assert session.calls[1][1] == preview_url
    assert session.calls[1][3] is None


def test_cache_locally_deduplicates_and_writes_sidecar_and_manifest(tmp_path: Path) -> None:
    credentials_path = _write_credentials(tmp_path / "freesound.json")
    output_dir = tmp_path / "audio_sources"
    detail_url = "https://freesound.org/apiv2/sounds/555/"
    preview_url = "https://cdn.example.com/555.mp3"
    session = FakeSession(
        {
            detail_url: [
                FakeResponse(
                    {
                        "id": 555,
                        "name": "Cicadas Close 2",
                        "username": "recordist",
                        "license": "http://creativecommons.org/publicdomain/zero/1.0/",
                        "duration": 10.2,
                        "type": "wav",
                        "url": "https://freesound.org/people/recordist/sounds/555/",
                        "previews": {"preview-hq-mp3": preview_url},
                    }
                )
            ],
            preview_url: [FakeResponse(content=b"cached-preview")],
        }
    )

    first = cache_locally(555, output_dir, credentials_path=credentials_path, session=session)
    second = cache_locally(555, output_dir, credentials_path=credentials_path, session=session)

    assert first == second
    assert first.name == "freesound_555.mp3"
    assert first.read_bytes() == b"cached-preview"

    sidecar = first.with_suffix(".json")
    manifest = output_dir / "MANIFEST.json"
    sidecar_data = json.loads(sidecar.read_text(encoding="utf-8"))
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))

    assert sidecar_data["sound_id"] == 555
    assert sidecar_data["author"] == "recordist"
    assert sidecar_data["license"] == "Creative Commons 0"
    assert sidecar_data["download_mode"] == "preview-hq-mp3"
    assert manifest_data["sources"][0]["sound_id"] == 555
    assert manifest_data["sources"][0]["file"] == "freesound_555.mp3"
    assert len(session.calls) == 2
