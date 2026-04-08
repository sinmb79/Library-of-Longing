from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
API_BASE_URL = "https://freesound.org/apiv2"
SEARCH_URL = f"{API_BASE_URL}/search/"
DEFAULT_CREDENTIALS_PATH = Path(r"C:\Users\sinmb\key\freesound.json")
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "audio_sources"
SEARCH_FIELDS = "id,name,username,license,duration,type,url,previews"
CC0_LICENSE = "Creative Commons 0"
CC0_LICENSE_VALUES = {
    CC0_LICENSE,
    "http://creativecommons.org/publicdomain/zero/1.0/",
    "https://creativecommons.org/publicdomain/zero/1.0/",
}


def load_credentials(credentials_path: Path = DEFAULT_CREDENTIALS_PATH) -> dict[str, Any]:
    if not credentials_path.exists():
        raise FileNotFoundError(f"Freesound credentials not found: {credentials_path}")
    payload = json.loads(credentials_path.read_text(encoding="utf-8"))
    if not payload.get("api_key"):
        raise ValueError(f"Missing api_key in {credentials_path}")
    return payload


def _session(session: requests.Session | Any | None) -> requests.Session | Any:
    return session or requests.Session()


def _sound_detail_url(sound_id: int) -> str:
    return f"{API_BASE_URL}/sounds/{int(sound_id)}/"


def _sound_download_url(sound_id: int) -> str:
    return f"{API_BASE_URL}/sounds/{int(sound_id)}/download/"


def _is_cc0(license_name: str | None) -> bool:
    normalized = (license_name or "").strip().rstrip("/")
    return normalized in {value.rstrip("/") for value in CC0_LICENSE_VALUES}


def _build_filter(min_duration: float | None, max_duration: float | None) -> str:
    filters = [f'license:"{CC0_LICENSE}"']
    if min_duration is not None or max_duration is not None:
        start = "*" if min_duration is None else int(min_duration) if float(min_duration).is_integer() else float(min_duration)
        end = "*" if max_duration is None else int(max_duration) if float(max_duration).is_integer() else float(max_duration)
        filters.append(f"duration:[{start} TO {end}]")
    return " ".join(filters)


def _normalize_sound(raw_sound: dict[str, Any]) -> dict[str, Any]:
    previews = raw_sound.get("previews") or {}
    preview_hq_mp3 = previews.get("preview-hq-mp3")
    normalized_license = CC0_LICENSE if _is_cc0(raw_sound.get("license")) else raw_sound.get("license", "")
    return {
        "provider": "freesound",
        "sound_id": raw_sound["id"],
        "name": raw_sound.get("name", ""),
        "author": raw_sound.get("username", ""),
        "license": normalized_license,
        "duration": raw_sound.get("duration"),
        "url": raw_sound.get("url", ""),
        "file_type": raw_sound.get("type", ""),
        "preview_hq_mp3": preview_hq_mp3,
        "download_mode": "preview-hq-mp3" if preview_hq_mp3 else "oauth-original",
    }


def _read_sound_details(
    sound_id: int,
    *,
    credentials: dict[str, Any],
    session: requests.Session | Any | None = None,
) -> dict[str, Any]:
    response = _session(session).get(
        _sound_detail_url(sound_id),
        params={"token": credentials["api_key"], "fields": SEARCH_FIELDS},
        timeout=30,
    )
    response.raise_for_status()
    return _normalize_sound(response.json())


def search_cc0(
    query: str,
    min_duration: float | None = None,
    max_duration: float | None = None,
    max_results: int = 10,
    *,
    credentials_path: Path = DEFAULT_CREDENTIALS_PATH,
    session: requests.Session | Any | None = None,
) -> list[dict[str, Any]]:
    credentials = load_credentials(credentials_path)
    response = _session(session).get(
        SEARCH_URL,
        params={
            "query": query,
            "filter": _build_filter(min_duration, max_duration),
            "fields": SEARCH_FIELDS,
            "page_size": min(max_results, 150),
            "token": credentials["api_key"],
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    results = [_normalize_sound(item) for item in payload.get("results", []) if _is_cc0(item.get("license"))]
    return results[:max_results]


def _resolve_access_token(credentials: dict[str, Any], explicit_access_token: str | None) -> str | None:
    return explicit_access_token or credentials.get("access_token") or os.getenv("FREESOUND_ACCESS_TOKEN")


def _download_bytes(
    url: str,
    destination: Path,
    *,
    session: requests.Session | Any | None = None,
    headers: dict[str, str] | None = None,
) -> Path:
    response = _session(session).get(url, headers=headers, timeout=120, stream=True)
    response.raise_for_status()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(response.content)
    return destination


def _download_sound_impl(
    sound_id: int,
    destination: Path,
    *,
    credentials_path: Path = DEFAULT_CREDENTIALS_PATH,
    session: requests.Session | Any | None = None,
    access_token: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[Path, dict[str, Any], str]:
    credentials = load_credentials(credentials_path)
    normalized = metadata or _read_sound_details(sound_id, credentials=credentials, session=session)
    if not _is_cc0(normalized.get("license")):
        raise ValueError(f"Freesound sound {sound_id} is not licensed under {CC0_LICENSE}.")

    resolved_access_token = _resolve_access_token(credentials, access_token)
    if resolved_access_token:
        try:
            downloaded = _download_bytes(
                _sound_download_url(sound_id),
                destination,
                session=session,
                headers={"Authorization": f"Bearer {resolved_access_token}"},
            )
            return downloaded, normalized, "oauth-original"
        except Exception:
            pass

    preview_url = normalized.get("preview_hq_mp3")
    if not preview_url:
        raise FileNotFoundError(f"No preview-hq-mp3 available for Freesound sound {sound_id}.")
    downloaded = _download_bytes(preview_url, destination, session=session)
    return downloaded, normalized, "preview-hq-mp3"


def download_sound(
    sound_id: int,
    output_path: Path,
    *,
    credentials_path: Path = DEFAULT_CREDENTIALS_PATH,
    session: requests.Session | Any | None = None,
    access_token: str | None = None,
) -> Path:
    downloaded, _, _ = _download_sound_impl(
        sound_id,
        output_path,
        credentials_path=credentials_path,
        session=session,
        access_token=access_token,
    )
    return downloaded


def _cached_path(output_dir: Path, sound_id: int) -> Path | None:
    for path in sorted(output_dir.glob(f"freesound_{int(sound_id)}.*")):
        if path.suffix.lower() != ".json" and path.is_file():
            return path
    return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"sources": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _upsert_manifest(path: Path, entry: dict[str, Any]) -> None:
    manifest = _load_manifest(path)
    sources = [item for item in manifest.get("sources", []) if item.get("sound_id") != entry.get("sound_id")]
    sources.append(entry)
    manifest["sources"] = sorted(sources, key=lambda item: int(item["sound_id"]))
    manifest["updated_at"] = datetime.now(UTC).isoformat()
    _write_json(path, manifest)


def cache_locally(
    sound_id: int,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    credentials_path: Path = DEFAULT_CREDENTIALS_PATH,
    session: requests.Session | Any | None = None,
    access_token: str | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = output_dir / f"freesound_{int(sound_id)}.json"
    manifest_path = output_dir / "MANIFEST.json"
    existing_path = _cached_path(output_dir, sound_id)
    if existing_path and sidecar_path.exists():
        sidecar_payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        _upsert_manifest(
            manifest_path,
            {
                **sidecar_payload,
                "file": existing_path.name,
                "sidecar": sidecar_path.name,
            },
        )
        return existing_path

    metadata = _read_sound_details(sound_id, credentials=load_credentials(credentials_path), session=session)
    extension = ".mp3"
    if _resolve_access_token(load_credentials(credentials_path), access_token):
        original_type = metadata.get("file_type", "").strip().lower()
        if original_type:
            extension = f".{original_type}"
    cached_path = output_dir / f"freesound_{int(sound_id)}{extension}"
    downloaded_path, normalized, download_mode = _download_sound_impl(
        sound_id,
        cached_path,
        credentials_path=credentials_path,
        session=session,
        access_token=access_token,
        metadata=metadata,
    )

    sidecar_payload = {
        "provider": "freesound",
        "sound_id": normalized["sound_id"],
        "name": normalized["name"],
        "author": normalized["author"],
        "license": normalized["license"],
        "duration": normalized["duration"],
        "source_url": normalized["url"],
        "preview_hq_mp3": normalized["preview_hq_mp3"],
        "download_mode": download_mode,
        "original_type": normalized["file_type"],
        "cached_at": datetime.now(UTC).isoformat(),
    }
    _write_json(sidecar_path, sidecar_payload)
    _upsert_manifest(
        manifest_path,
        {
            **sidecar_payload,
            "file": downloaded_path.name,
            "sidecar": sidecar_path.name,
        },
    )
    return downloaded_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch CC0 Freesound audio for Library of Longing.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search Creative Commons 0 sounds.")
    search_parser.add_argument("--query", required=True, help="Search query.")
    search_parser.add_argument("--min-duration", type=float, default=None, help="Minimum duration in seconds.")
    search_parser.add_argument("--max-duration", type=float, default=None, help="Maximum duration in seconds.")
    search_parser.add_argument("--max-results", type=int, default=10, help="Maximum number of results.")
    search_parser.add_argument(
        "--credentials-path",
        type=Path,
        default=DEFAULT_CREDENTIALS_PATH,
        help="Path to Freesound credentials JSON.",
    )

    download_parser = subparsers.add_parser("download", help="Download a specific sound to a file.")
    download_parser.add_argument("--sound-id", type=int, required=True, help="Freesound sound id.")
    download_parser.add_argument("--output", type=Path, required=True, help="Destination audio path.")
    download_parser.add_argument(
        "--credentials-path",
        type=Path,
        default=DEFAULT_CREDENTIALS_PATH,
        help="Path to Freesound credentials JSON.",
    )

    cache_parser = subparsers.add_parser("cache", help="Cache a Freesound sound and provenance metadata.")
    cache_parser.add_argument("--sound-id", type=int, required=True, help="Freesound sound id.")
    cache_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Cache directory.")
    cache_parser.add_argument(
        "--credentials-path",
        type=Path,
        default=DEFAULT_CREDENTIALS_PATH,
        help="Path to Freesound credentials JSON.",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "search":
        results = search_cc0(
            args.query,
            min_duration=args.min_duration,
            max_duration=args.max_duration,
            max_results=args.max_results,
            credentials_path=args.credentials_path,
        )
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    if args.command == "download":
        destination = download_sound(args.sound_id, args.output, credentials_path=args.credentials_path)
        print(destination)
        return

    if args.command == "cache":
        destination = cache_locally(args.sound_id, args.output_dir, credentials_path=args.credentials_path)
        print(destination)
        return

    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
