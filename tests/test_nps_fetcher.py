from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from scripts.audio_sourcing.nps_fetcher import categorize_by_species, download, list_catalog


class FakeResponse:
    def __init__(self, text: str = "", *, content: bytes = b"", status_code: int = 200) -> None:
        self.text = text
        self.content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, routes: dict[str, list[FakeResponse]]) -> None:
        self.routes = {url: list(responses) for url, responses in routes.items()}
        self.calls: list[str] = []

    def get(self, url: str, *, timeout: int | float | None = None, headers: dict | None = None) -> FakeResponse:
        self.calls.append(url)
        responses = self.routes.get(url)
        if not responses:
            raise AssertionError(f"Unexpected GET {url}")
        return responses.pop(0)


def test_list_catalog_parses_gallery_entries() -> None:
    gallery_html = """
    <html><body>
      <h2>Birds</h2>
      <a href="/subjects/sound/sounds-american-robin.htm">American Robin</a>
      <a href="/subjects/sound/sounds-osprey.htm">Osprey</a>
      <h2>Amphibians</h2>
      <a href="/subjects/sound/sounds-green-treefrog.htm">Green Tree Frog</a>
    </body></html>
    """
    session = FakeSession(
        {
            "https://www.nps.gov/robots.txt": [FakeResponse("User-agent: *\nAllow: /subjects/sound/\n")],
            "https://www.nps.gov/subjects/sound/gallery.htm": [FakeResponse(gallery_html)],
        }
    )

    entries = list_catalog(session=session, rate_limit_sec=0.0)

    assert [entry["title"] for entry in entries] == ["American Robin", "Osprey", "Green Tree Frog"]
    assert entries[0]["category"] == "birds"
    assert entries[0]["page_url"] == "https://www.nps.gov/subjects/sound/sounds-american-robin.htm"
    assert entries[0]["license"] == "US Public Domain"


def test_categorize_by_species_groups_by_category() -> None:
    entries = [
        {"title": "American Robin", "category": "birds"},
        {"title": "Osprey", "category": "birds"},
        {"title": "Green Tree Frog", "category": "amphibians"},
    ]

    grouped = categorize_by_species(entries)

    assert list(grouped.keys()) == ["amphibians", "birds"]
    assert [entry["title"] for entry in grouped["birds"]] == ["American Robin", "Osprey"]


def test_download_resolves_audio_and_writes_sidecar(tmp_path: Path) -> None:
    entry = {
        "title": "American Robin",
        "category": "birds",
        "page_url": "https://www.nps.gov/subjects/sound/sounds-american-robin.htm",
        "license": "US Public Domain",
    }
    detail_html = """
    <html><body>
      <audio controls>
        <source src="https://www.nps.gov/nps-audiovideo/legacy/mp3/nri/avElement/nri-AmericanRobinYELL.mp3" type="audio/mp3" />
      </audio>
    </body></html>
    """
    audio_url = "https://www.nps.gov/nps-audiovideo/legacy/mp3/nri/avElement/nri-AmericanRobinYELL.mp3"
    session = FakeSession(
        {
            "https://www.nps.gov/robots.txt": [FakeResponse("User-agent: *\nAllow: /subjects/sound/\n")],
            entry["page_url"]: [FakeResponse(detail_html)],
            audio_url: [FakeResponse(content=b"nps-audio")],
        }
    )

    output_path = download(entry, tmp_path, session=session, rate_limit_sec=0.0)

    assert output_path.exists()
    assert output_path.name == "american_robin.mp3"
    assert output_path.read_bytes() == b"nps-audio"

    sidecar = output_path.with_suffix(".json")
    sidecar_data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert sidecar_data["title"] == "American Robin"
    assert sidecar_data["license"] == "US Public Domain"
    assert sidecar_data["origin_url"] == entry["page_url"]
    assert sidecar_data["audio_url"] == audio_url


def test_download_requires_audio_source(tmp_path: Path) -> None:
    entry = {
        "title": "Missing Audio",
        "category": "birds",
        "page_url": "https://www.nps.gov/subjects/sound/missing-audio.htm",
        "license": "US Public Domain",
    }
    session = FakeSession(
        {
            "https://www.nps.gov/robots.txt": [FakeResponse("User-agent: *\nAllow: /subjects/sound/\n")],
            entry["page_url"]: [FakeResponse("<html><body>No audio</body></html>")],
        }
    )

    with pytest.raises(FileNotFoundError):
        download(entry, tmp_path, session=session, rate_limit_sec=0.0)
