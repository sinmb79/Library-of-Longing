from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup


NPS_BASE_URL = "https://www.nps.gov"
NPS_GALLERY_URL = f"{NPS_BASE_URL}/subjects/sound/gallery.htm"
NPS_ROBOTS_URL = f"{NPS_BASE_URL}/robots.txt"
DEFAULT_OUTPUT_DIR = Path("audio_sources") / "nps"
DEFAULT_RATE_LIMIT_SEC = 1.0
DEFAULT_HEADERS = {"User-Agent": "LibraryOfLongingBot/1.0 (+https://github.com/sinmb79/Library-of-Longing)"}


def _session(session: requests.Session | Any | None) -> requests.Session | Any:
    return session or requests.Session()


def _throttle(last_request_at: float | None, rate_limit_sec: float) -> float:
    if last_request_at is not None and rate_limit_sec > 0:
        elapsed = time.monotonic() - last_request_at
        remaining = rate_limit_sec - elapsed
        if remaining > 0:
            time.sleep(remaining)
    return time.monotonic()


def _ensure_scraping_allowed(session: requests.Session | Any | None = None) -> None:
    response = _session(session).get(NPS_ROBOTS_URL, headers=DEFAULT_HEADERS, timeout=30)
    response.raise_for_status()
    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    if not parser.can_fetch(DEFAULT_HEADERS["User-Agent"], urlparse(NPS_GALLERY_URL).path):
        raise PermissionError(f"robots.txt disallows scraping {NPS_GALLERY_URL}")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "nps_sound"


def _normalize_category(text: str) -> str:
    return _slugify(text).replace("_", " ")


def list_catalog(
    *,
    session: requests.Session | Any | None = None,
    rate_limit_sec: float = DEFAULT_RATE_LIMIT_SEC,
) -> list[dict[str, Any]]:
    _ensure_scraping_allowed(session=session)
    _throttle(None, rate_limit_sec)
    response = _session(session).get(NPS_GALLERY_URL, headers=DEFAULT_HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    entries: list[dict[str, Any]] = []
    current_category = "uncategorized"
    for node in soup.find_all(["h1", "h2", "h3", "a"]):
        if node.name in {"h1", "h2", "h3"}:
            heading = node.get_text(" ", strip=True)
            if heading:
                current_category = _normalize_category(heading)
            continue

        href = node.get("href", "")
        title = node.get_text(" ", strip=True)
        if not title or "/subjects/sound/" not in href or not href.endswith(".htm"):
            continue
        page_url = urljoin(NPS_BASE_URL, href)
        entries.append(
            {
                "title": title,
                "page_url": page_url,
                "category": current_category,
                "license": "US Public Domain",
                "tier": "nps_pd",
            }
        )

    deduped: dict[str, dict[str, Any]] = {}
    for entry in entries:
        deduped[entry["page_url"]] = entry
    return list(deduped.values())


def categorize_by_species(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        grouped[entry["category"]].append(entry)
    return {key: grouped[key] for key in sorted(grouped)}


def _extract_audio_url(detail_html: str, page_url: str) -> str:
    soup = BeautifulSoup(detail_html, "html.parser")
    audio_source = soup.select_one("audio source[src]")
    if audio_source is not None:
        return urljoin(page_url, audio_source["src"])
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "")
        if href.lower().endswith((".mp3", ".wav", ".m4a")):
            return urljoin(page_url, href)
    raise FileNotFoundError(f"No downloadable audio source found at {page_url}")


def download(
    entry: dict[str, Any],
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    output_filename: str | None = None,
    session: requests.Session | Any | None = None,
    rate_limit_sec: float = DEFAULT_RATE_LIMIT_SEC,
) -> Path:
    active_session = _session(session)
    output_dir.mkdir(parents=True, exist_ok=True)

    _ensure_scraping_allowed(session=active_session)
    _throttle(None, rate_limit_sec)
    detail_response = active_session.get(entry["page_url"], headers=DEFAULT_HEADERS, timeout=30)
    detail_response.raise_for_status()
    audio_url = _extract_audio_url(detail_response.text, entry["page_url"])

    _throttle(time.monotonic(), rate_limit_sec)
    audio_response = active_session.get(audio_url, headers=DEFAULT_HEADERS, timeout=120)
    audio_response.raise_for_status()

    extension = Path(urlparse(audio_url).path).suffix or ".mp3"
    output_name = output_filename or f"{_slugify(entry['title'])}{extension}"
    output_path = output_dir / output_name
    output_path.write_bytes(audio_response.content)

    sidecar = {
        "provider": "nps",
        "title": entry["title"],
        "category": entry["category"],
        "license": "US Public Domain",
        "origin_url": entry["page_url"],
        "audio_url": audio_url,
    }
    output_path.with_suffix(".json").write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch public domain audio from the NPS Natural Sounds gallery.")
    parser.add_argument("--list", action="store_true", help="List catalog entries.")
    parser.add_argument("--category", type=str, default=None, help="Only list/download entries matching this category.")
    parser.add_argument("--title", type=str, default=None, help="Download the first entry whose title contains this text.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Where to save downloaded audio.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    entries = list_catalog()
    if args.category:
        needle = _normalize_category(args.category)
        entries = [entry for entry in entries if entry["category"] == needle]
    if args.list or not args.title:
        print(json.dumps(entries, ensure_ascii=False, indent=2))
        if not args.title:
            return

    if args.title:
        lowered = args.title.lower()
        for entry in entries:
            if lowered in entry["title"].lower():
                print(download(entry, args.output_dir))
                return
        raise SystemExit(f"No NPS catalog entry found for title fragment: {args.title}")


if __name__ == "__main__":
    main()
