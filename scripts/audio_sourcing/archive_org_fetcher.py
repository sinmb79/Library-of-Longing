from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

import requests


ADVANCEDSEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL_TEMPLATE = "https://archive.org/metadata/{item_id}"
DOWNLOAD_URL_TEMPLATE = "https://archive.org/download/{item_id}/{filename}"
DETAILS_URL_TEMPLATE = "https://archive.org/details/{item_id}"
DEFAULT_OUTPUT_DIR = Path("audio_sources") / "archive"
OPEN_LICENSE_PATTERNS = (
    "public domain",
    "creativecommons.org/publicdomain/zero/1.0",
    "creative commons 0",
    "cc0",
)
FORMAT_MAP = {
    "mp3": {"vbr mp3", "mp3"},
    "flac": {"flac"},
    "wav": {"wav", "wave"},
}


def _session(session: requests.Session | Any | None) -> requests.Session | Any:
    return session or requests.Session()


def _normalize_license(metadata: dict[str, Any]) -> tuple[str, bool]:
    candidates = [
        metadata.get("licenseurl", ""),
        metadata.get("license", ""),
        metadata.get("rights", ""),
        metadata.get("possible-copyright-status", ""),
    ]
    combined = " | ".join(str(item).strip() for item in candidates if item).strip()
    lowered = combined.lower()
    allowed = any(pattern in lowered for pattern in OPEN_LICENSE_PATTERNS)
    if allowed and "creativecommons.org/publicdomain/zero/1.0" in lowered:
        return "Creative Commons 0", True
    if allowed:
        return combined or "Public Domain", True
    return combined or "Unknown", False


def _normalize_doc(doc: dict[str, Any], collection: str | None) -> dict[str, Any]:
    return {
        "identifier": doc["identifier"],
        "title": doc.get("title", doc["identifier"]),
        "creator": doc.get("creator", ""),
        "collection": collection,
    }


def search(
    query: str,
    collection: str | None = "NaturalSoundsFieldRecordingArchive",
    max_results: int = 10,
    *,
    session: requests.Session | Any | None = None,
) -> list[dict[str, Any]]:
    clauses = [query, "mediatype:(audio)"]
    if collection:
        clauses.append(f"collection:({collection})")
    response = _session(session).get(
        ADVANCEDSEARCH_URL,
        params={
            "q": " AND ".join(clauses),
            "fl[]": ["identifier", "title", "creator"],
            "rows": max_results,
            "output": "json",
        },
        timeout=30,
    )
    response.raise_for_status()
    docs = response.json().get("response", {}).get("docs", [])
    return [_normalize_doc(doc, collection) for doc in docs]


def get_metadata(item_id: str, *, session: requests.Session | Any | None = None) -> dict[str, Any]:
    response = _session(session).get(METADATA_URL_TEMPLATE.format(item_id=item_id), timeout=30)
    response.raise_for_status()
    payload = response.json()
    metadata = payload.get("metadata", {})
    files = payload.get("files", [])
    license_name, allowed_license = _normalize_license(metadata)
    return {
        "item_id": item_id,
        "title": metadata.get("title", item_id),
        "creator": metadata.get("creator", ""),
        "license": license_name,
        "allowed_license": allowed_license,
        "origin_url": DETAILS_URL_TEMPLATE.format(item_id=item_id),
        "files": files,
    }


def _wanted_files(files: Iterable[dict[str, Any]], formats: tuple[str, ...]) -> list[dict[str, Any]]:
    wanted: list[dict[str, Any]] = []
    normalized_formats = {item.lower() for item in formats}
    for file in files:
        name = file.get("name", "")
        extension = Path(name).suffix.lower().lstrip(".")
        format_name = str(file.get("format", "")).lower()
        if extension in normalized_formats:
            wanted.append(file)
            continue
        if any(format_name in FORMAT_MAP.get(target, {target}) for target in normalized_formats):
            wanted.append(file)
    return wanted


def _write_sidecar(path: Path, payload: dict[str, Any]) -> None:
    path.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def download_audio_files(
    item_id: str,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    formats: tuple[str, ...] = ("wav", "flac", "mp3"),
    *,
    session: requests.Session | Any | None = None,
) -> list[Path]:
    metadata = get_metadata(item_id, session=session)
    if not metadata["allowed_license"]:
        raise ValueError(f"Archive.org item {item_id} does not have an open license.")

    output_dir.mkdir(parents=True, exist_ok=True)
    active_session = _session(session)
    downloaded_paths: list[Path] = []
    for file in _wanted_files(metadata["files"], formats):
        filename = file["name"]
        response = active_session.get(
            DOWNLOAD_URL_TEMPLATE.format(item_id=item_id, filename=filename),
            timeout=120,
            stream=True,
        )
        response.raise_for_status()
        output_path = output_dir / filename
        output_path.write_bytes(response.content)
        _write_sidecar(
            output_path,
            {
                "provider": "archive.org",
                "item_id": item_id,
                "title": metadata["title"],
                "creator": metadata["creator"],
                "license": metadata["license"],
                "origin_url": metadata["origin_url"],
                "sha256": hashlib.sha256(response.content).hexdigest(),
            },
        )
        downloaded_paths.append(output_path)
    return downloaded_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch open-license field recordings from Archive.org.")
    parser.add_argument("--query", type=str, required=True, help="Search query.")
    parser.add_argument("--collection", type=str, default="NaturalSoundsFieldRecordingArchive", help="Optional collection filter.")
    parser.add_argument("--max-results", type=int, default=10, help="Maximum number of search results.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Where to save downloaded audio.")
    parser.add_argument("--download-first", action="store_true", help="Download the first matching item.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    collection = args.collection or None
    docs = search(args.query, collection=collection, max_results=args.max_results)
    if args.download_first:
        if not docs:
            raise SystemExit("No Archive.org items matched the query.")
        paths = download_audio_files(docs[0]["identifier"], args.output_dir)
        print(json.dumps([path.as_posix() for path in paths], ensure_ascii=False, indent=2))
        return
    print(json.dumps(docs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
