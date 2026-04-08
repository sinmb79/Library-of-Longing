from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from scripts.audio_sourcing.archive_org_fetcher import download_audio_files, get_metadata, search


class FakeResponse:
    def __init__(self, payload: dict | None = None, *, content: bytes = b"", status_code: int = 200) -> None:
        self._payload = payload or {}
        self.content = content
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, routes: dict[str, list[FakeResponse]]) -> None:
        self.routes = {url: list(responses) for url, responses in routes.items()}
        self.calls: list[tuple[str, dict | None]] = []

    def get(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        timeout: int | float | None = None,
        stream: bool | None = None,
    ) -> FakeResponse:
        self.calls.append((url, params))
        responses = self.routes.get(url)
        if not responses:
            raise AssertionError(f"Unexpected GET {url}")
        return responses.pop(0)


def test_search_returns_normalized_docs() -> None:
    session = FakeSession(
        {
            "https://archive.org/advancedsearch.php": [
                FakeResponse(
                    {
                        "response": {
                            "docs": [
                                {
                                    "identifier": "field-recording-001",
                                    "title": "Summer Cicadas",
                                    "creator": "Recordist",
                                }
                            ]
                        }
                    }
                )
            ]
        }
    )

    docs = search("cicada forest", collection="NaturalSoundsFieldRecordingArchive", max_results=5, session=session)

    assert docs == [
        {
            "identifier": "field-recording-001",
            "title": "Summer Cicadas",
            "creator": "Recordist",
            "collection": "NaturalSoundsFieldRecordingArchive",
        }
    ]
    assert "collection:(NaturalSoundsFieldRecordingArchive)" in (session.calls[0][1] or {})["q"]


def test_get_metadata_marks_non_open_license_as_rejected() -> None:
    session = FakeSession(
        {
            "https://archive.org/metadata/field-recording-002": [
                FakeResponse(
                    {
                        "metadata": {
                            "title": "Restricted Birds",
                            "creator": "Archivist",
                            "rights": "All Rights Reserved",
                        },
                        "files": [],
                    }
                )
            ]
        }
    )

    metadata = get_metadata("field-recording-002", session=session)

    assert metadata["allowed_license"] is False
    assert metadata["license"] == "All Rights Reserved"


def test_download_audio_files_writes_allowed_formats_and_sidecars(tmp_path: Path) -> None:
    item_id = "field-recording-003"
    metadata_url = f"https://archive.org/metadata/{item_id}"
    audio_url = f"https://archive.org/download/{item_id}/summer-cicadas.mp3"
    session = FakeSession(
        {
            metadata_url: [
                FakeResponse(
                    {
                        "metadata": {
                            "title": "Summer Cicadas",
                            "creator": "Archivist",
                            "licenseurl": "https://creativecommons.org/publicdomain/zero/1.0/",
                        },
                        "files": [
                            {"name": "summer-cicadas.mp3", "format": "VBR MP3"},
                            {"name": "readme.txt", "format": "Text"},
                        ],
                    }
                )
            ],
            audio_url: [FakeResponse(content=b"archive-audio")],
        }
    )

    paths = download_audio_files(item_id, tmp_path, formats=("mp3",), session=session)

    assert [path.name for path in paths] == ["summer-cicadas.mp3"]
    assert paths[0].read_bytes() == b"archive-audio"

    sidecar = json.loads(paths[0].with_suffix(".json").read_text(encoding="utf-8"))
    assert sidecar["item_id"] == item_id
    assert sidecar["license"] == "Creative Commons 0"
    assert sidecar["origin_url"] == metadata_url.replace("/metadata/", "/details/")


def test_download_audio_files_rejects_non_open_license(tmp_path: Path) -> None:
    item_id = "field-recording-004"
    session = FakeSession(
        {
            f"https://archive.org/metadata/{item_id}": [
                FakeResponse(
                    {
                        "metadata": {
                            "title": "Restricted Birds",
                            "creator": "Archivist",
                            "rights": "All Rights Reserved",
                        },
                        "files": [{"name": "birds.mp3", "format": "VBR MP3"}],
                    }
                )
            ]
        }
    )

    with pytest.raises(ValueError, match="open license"):
        download_audio_files(item_id, tmp_path, formats=("mp3",), session=session)
