from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import soundfile as sf

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.audio_sourcing.archive_org_fetcher import download_audio_files as download_archive_audio_files
from scripts.audio_sourcing.archive_org_fetcher import get_metadata as get_archive_metadata
from scripts.audio_sourcing.archive_org_fetcher import search as search_archive
from scripts.audio_sourcing.freesound_fetcher import download_sound, search_cc0
from scripts.audio_sourcing.nps_fetcher import download as download_nps
from scripts.audio_sourcing.nps_fetcher import list_catalog
from scripts.audio_sourcing.procedural_gen import write_procedural_wav
from scripts.audio_sourcing.stable_audio_gen import generate_sfx
from scripts.scene_config import load_scene_config


DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "audio_sources" / "MANIFEST.json"
AUTO_TIER = "auto"
BIOLOGICAL_KEYWORDS = {
    "sparrow",
    "robin",
    "eagle",
    "owl",
    "raven",
    "bird",
    "frog",
    "toad",
    "crane",
    "gull",
    "cicada",
}
PROCEDURAL_MAP = {
    "room_tone": "room_tone",
    "room": "room_tone",
    "fan": "fan",
    "wind": "wind",
    "breeze": "wind",
    "hum": "hum",
}
STABLE_KEYWORDS = {"glass", "clink", "kitchen", "cup", "ice", "plate"}
EXPECTED_FORMATS = {
    ".wav": {"WAV"},
    ".mp3": {"MP3"},
    ".flac": {"FLAC"},
}
PROVIDER_BY_TIER = {
    "freesound_cc0": "freesound",
    "nps_pd": "nps",
    "archive_pd": "archive.org",
    "procedural": "procedural",
    "stable_audio": "stable_audio",
    "local_existing": "local_existing",
}
logger = logging.getLogger(__name__)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        parts = list(path.resolve().parts)
        if "audio_sources" in parts:
            index = parts.index("audio_sources")
            return Path(*parts[index:]).as_posix()
        return path.resolve().as_posix()


def _sidecar_path(audio_path: Path) -> Path:
    return audio_path.with_suffix(".json")


def _read_existing_sidecar(audio_path: Path) -> dict[str, Any] | None:
    sidecar_path = _sidecar_path(audio_path)
    if not sidecar_path.exists():
        return None
    try:
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning("Rejecting invalid provenance sidecar for %s: %s", audio_path, exc)
        return None
    license_value = str(payload.get("license", "")).strip()
    if not license_value:
        logger.warning("Rejecting provenance sidecar without license for %s", audio_path)
        return None
    return payload


def _cleanup_target_family(target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    for sibling in target_path.parent.glob(f"{target_path.stem}.*"):
        if sibling.suffix.lower() not in EXPECTED_FORMATS and sibling.suffix.lower() != ".json":
            continue
        if sibling.exists():
            sibling.unlink()


def _write_provenance_sidecar(audio_path: Path, *, tier: str, metadata: dict[str, Any]) -> dict[str, Any]:
    payload = {key: value for key, value in metadata.items() if value is not None}
    payload.setdefault("provider", PROVIDER_BY_TIER.get(tier, tier))
    payload.setdefault("tier", tier)
    payload.setdefault("original_title", audio_path.name)
    payload.setdefault("origin_url", "")
    payload.setdefault("author", "")
    payload["license"] = str(payload.get("license", "")).strip()
    payload["sha256"] = _sha256(audio_path)
    payload["stored_path"] = _relative_path(audio_path)
    payload["stored_at"] = datetime.now(UTC).isoformat()
    sidecar_path = _sidecar_path(audio_path)
    sidecar_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _layer_targets(scene_config: dict[str, Any]) -> list[dict[str, Any]]:
    layers = scene_config["audio"]["layers"]
    targets: list[dict[str, Any]] = [
        {
            "layer_name": "room_tone",
            "target_path": Path(layers["room_tone"]["source_path"]),
            "layer_config": layers["room_tone"],
            "source_index": None,
        },
        {
            "layer_name": "continuous",
            "target_path": Path(layers["continuous"]["source_path"]),
            "layer_config": layers["continuous"],
            "source_index": None,
        },
    ]
    targets.extend(
        {
            "layer_name": "periodic",
            "target_path": Path(path),
            "layer_config": layers["periodic"],
            "source_index": index,
        }
        for index, path in enumerate(layers["periodic"]["source_paths"])
    )
    targets.extend(
        {
            "layer_name": "rare_events",
            "target_path": Path(path),
            "layer_config": layers["rare_events"],
            "source_index": index,
        }
        for index, path in enumerate(layers["rare_events"]["source_paths"])
    )
    return targets


def _infer_query(target_path: Path) -> str:
    return target_path.stem.replace("_", " ").replace("-", " ").strip().lower()


def _sourcing_config(layer_config: dict[str, Any]) -> dict[str, Any]:
    return dict(layer_config.get("sourcing") or {})


def _pick_query(default_query: str, sourcing: dict[str, Any], source_index: int | None) -> str:
    queries = [str(item).strip().lower() for item in sourcing.get("queries", []) if str(item).strip()]
    if not queries:
        return default_query
    if source_index is not None and 0 <= source_index < len(queries):
        return queries[source_index]
    return queries[0]


def _query_candidates(default_query: str, sourcing: dict[str, Any], source_index: int | None) -> list[str]:
    primary = _pick_query(default_query, sourcing, source_index)
    candidates = [primary]
    if primary != default_query:
        candidates.append(default_query)
    return candidates


def _pick_duration_range(sourcing: dict[str, Any]) -> tuple[float | None, float | None]:
    return sourcing.get("min_duration"), sourcing.get("max_duration")


def _is_biological(query: str) -> bool:
    return any(keyword in query for keyword in BIOLOGICAL_KEYWORDS)


def _procedural_type(layer_name: str, query: str, sourcing: dict[str, Any]) -> str | None:
    if sourcing.get("type"):
        return str(sourcing["type"])
    if layer_name == "room_tone":
        return "room_tone"
    if layer_name != "continuous":
        return None
    for keyword, generator in PROCEDURAL_MAP.items():
        if keyword in query:
            return generator
    return None


def _stable_prompt(query: str, sourcing: dict[str, Any]) -> str:
    return str(sourcing.get("prompt") or f"clean isolated {query.replace('_', ' ')}, high quality ambient detail, no music, no voice")


def _prefer_stable(layer_name: str, query: str) -> bool:
    return layer_name == "rare_events" and any(keyword in query for keyword in STABLE_KEYWORDS)


def _write_manifest(manifest_path: Path, payload: dict[str, Any]) -> Path:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def _find_nps_match(query: str, entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    words = [word for word in query.split() if word]
    for entry in entries:
        haystack = f"{entry['title']} {entry['category']}".lower()
        if all(word in haystack for word in words):
            return entry
    for entry in entries:
        haystack = f"{entry['title']} {entry['category']}".lower()
        if any(word in haystack for word in words):
            return entry
    return None


def _move_into_place(source_path: Path, target_path: Path) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.resolve() != target_path.resolve():
        shutil.move(str(source_path), str(target_path))
        sidecar = source_path.with_suffix(".json")
        if sidecar.exists():
            shutil.move(str(sidecar), str(target_path.with_suffix(".json")))
    return target_path


def _record_entry(
    manifest: dict[str, Any],
    target_path: Path,
    *,
    tier: str,
    metadata: dict[str, Any],
    dry_run: bool,
) -> None:
    key = _relative_path(target_path)
    entry = {"tier": tier, **metadata}
    if dry_run:
        entry["planned"] = True
    elif target_path.exists():
        entry["sha256"] = _sha256(target_path)
    manifest["sources"][key] = entry


def _is_usable_audio(path: Path) -> bool:
    if not path.exists():
        return False
    if path.stat().st_size < 4096:
        logger.warning("Rejecting legacy_stub audio for %s (size=%s)", path, path.stat().st_size)
        return False
    try:
        info = sf.info(path)
    except Exception as exc:
        logger.warning("Rejecting undecodable audio for %s: %s", path, exc)
        return False
    expected_formats = EXPECTED_FORMATS.get(path.suffix.lower())
    if expected_formats is not None and info.format not in expected_formats:
        logger.warning(
            "Rejecting mismatched audio for %s: expected %s, got %s",
            path,
            sorted(expected_formats),
            info.format,
        )
        return False
    return info.frames > 0 and info.samplerate > 0 and info.channels >= 1


def _acquire_with_freesound(
    query: str,
    target_path: Path,
    *,
    min_duration: float | None = 5,
    max_duration: float | None = 60,
    dry_run: bool,
) -> dict[str, Any] | None:
    results = search_cc0(query, min_duration=min_duration, max_duration=max_duration, max_results=3)
    if not results:
        return None
    selected = results[0]
    if not dry_run:
        download_sound(selected["sound_id"], target_path)
    return {
        "provider": "freesound",
        "sound_id": selected["sound_id"],
        "license": selected["license"],
        "origin_url": selected["url"],
        "author": selected["author"],
        "original_title": selected["name"],
        "duration_sec": selected.get("duration"),
    }


def _acquire_with_nps(query: str, target_path: Path, *, dry_run: bool) -> dict[str, Any] | None:
    entries = list_catalog(rate_limit_sec=0.0)
    match = _find_nps_match(query, entries)
    if match is None:
        return None
    if not dry_run:
        downloaded = download_nps(match, target_path.parent, output_filename=target_path.name)
        _move_into_place(downloaded, target_path)
    return {
        "provider": "nps",
        "license": "US Public Domain",
        "origin_url": match["page_url"],
        "author": "National Park Service",
        "original_title": match["title"],
        "category": match["category"],
    }


def _acquire_with_archive(query: str, target_path: Path, *, dry_run: bool) -> dict[str, Any] | None:
    docs = search_archive(query, collection=None, max_results=3)
    for doc in docs:
        if dry_run:
            metadata = get_archive_metadata(doc["identifier"])
            if not metadata["allowed_license"]:
                continue
            return {
                "provider": "archive.org",
                "license": metadata["license"],
                "origin_url": metadata["origin_url"],
                "author": metadata["creator"],
                "original_title": metadata["title"],
                "item_id": doc["identifier"],
            }
        try:
            downloaded_paths = download_archive_audio_files(
                doc["identifier"],
                target_path.parent,
                formats=(target_path.suffix.lstrip(".") or "mp3", "mp3"),
            )
        except ValueError:
            continue
        if not downloaded_paths:
            continue
        _move_into_place(downloaded_paths[0], target_path)
        sidecar_path = target_path.with_suffix(".json")
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8")) if sidecar_path.exists() else {}
        return {
            "provider": "archive.org",
            "license": sidecar.get("license", "Public Domain"),
            "origin_url": sidecar.get("origin_url", ""),
            "author": sidecar.get("creator", doc.get("creator", "")),
            "original_title": sidecar.get("title", doc.get("title", "")),
            "item_id": doc["identifier"],
        }
    return None


def _acquire_with_procedural(
    layer_name: str,
    query: str,
    target_path: Path,
    seed: int,
    *,
    sourcing: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any] | None:
    generator = _procedural_type(layer_name, query, sourcing)
    if generator is None:
        return None
    params = dict(sourcing.get("params") or {})
    duration = float(params.pop("duration", 30.0))
    if not dry_run:
        write_procedural_wav(generator, target_path, duration=duration, seed=seed, **params)
    return {
        "provider": "procedural",
        "generator": generator,
        "params": params,
        "license": "Procedural",
        "origin_url": "",
        "duration_sec": duration,
        "seed": seed,
    }


def _acquire_with_stable(
    query: str,
    target_path: Path,
    seed: int,
    *,
    sourcing: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    params = dict(sourcing.get("params") or {})
    duration = float(params.pop("duration", 8.0))
    prompt = _stable_prompt(query, sourcing)
    if not dry_run:
        generate_sfx(prompt=prompt, duration=duration, seed=seed, output_path=target_path)
    return {
        "provider": "stable_audio",
        "license": "Stable Audio",
        "origin_url": "",
        "prompt": prompt,
        "seed": seed,
        "duration_sec": duration,
    }


def _acquire_explicit(
    layer_name: str,
    query: str,
    default_query: str,
    target_path: Path,
    seed: int,
    *,
    sourcing: dict[str, Any],
    source_index: int | None,
    dry_run: bool,
) -> tuple[str, dict[str, Any] | None]:
    explicit_tier = str(sourcing.get("tier") or AUTO_TIER)
    min_duration, max_duration = _pick_duration_range(sourcing)
    if explicit_tier == "procedural":
        return "procedural", _acquire_with_procedural(layer_name, query, target_path, seed, sourcing=sourcing, dry_run=dry_run)
    if explicit_tier == "freesound_cc0":
        for candidate in _query_candidates(default_query, sourcing, source_index):
            metadata = _acquire_with_freesound(candidate, target_path, min_duration=min_duration, max_duration=max_duration, dry_run=dry_run)
            if metadata is not None:
                return "freesound_cc0", metadata
        return "freesound_cc0", None
    if explicit_tier == "nps_pd":
        for candidate in _query_candidates(default_query, sourcing, source_index):
            metadata = _acquire_with_nps(candidate, target_path, dry_run=dry_run)
            if metadata is not None:
                return "nps_pd", metadata
        return "nps_pd", None
    if explicit_tier == "archive_pd":
        for candidate in _query_candidates(default_query, sourcing, source_index):
            metadata = _acquire_with_archive(candidate, target_path, dry_run=dry_run)
            if metadata is not None:
                return "archive_pd", metadata
        return "archive_pd", None
    if explicit_tier == "stable_audio":
        return "stable_audio", _acquire_with_stable(query, target_path, seed, sourcing=sourcing, dry_run=dry_run)
    return AUTO_TIER, None


def _acquire_auto(
    layer_name: str,
    query: str,
    target_path: Path,
    seed: int,
    *,
    sourcing: dict[str, Any],
    dry_run: bool,
) -> tuple[str, dict[str, Any]]:
    min_duration, max_duration = _pick_duration_range(sourcing)

    procedural_metadata = _acquire_with_procedural(layer_name, query, target_path, seed, sourcing=sourcing, dry_run=dry_run)
    if procedural_metadata is not None:
        return "procedural", procedural_metadata

    if _prefer_stable(layer_name, query):
        return "stable_audio", _acquire_with_stable(query, target_path, seed, sourcing=sourcing, dry_run=dry_run)

    freesound_metadata = _acquire_with_freesound(query, target_path, min_duration=min_duration, max_duration=max_duration, dry_run=dry_run)
    if freesound_metadata is not None:
        return "freesound_cc0", freesound_metadata

    if _is_biological(query):
        nps_metadata = _acquire_with_nps(query, target_path, dry_run=dry_run)
        if nps_metadata is not None:
            return "nps_pd", nps_metadata

    archive_metadata = _acquire_with_archive(query, target_path, dry_run=dry_run)
    if archive_metadata is not None:
        return "archive_pd", archive_metadata

    return "stable_audio", _acquire_with_stable(query, target_path, seed, sourcing=sourcing, dry_run=dry_run)


def populate_scene_audio_sources(
    scene_path: Path,
    *,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    seed: int = 42,
    dry_run: bool = False,
    force: bool = False,
) -> Path | dict[str, Any]:
    scene_config = load_scene_config(scene_path)
    manifest = {
        "scene_id": scene_config["scene"]["id"],
        "generated_at": datetime.now(UTC).isoformat(),
        "dry_run": dry_run,
        "sources": {},
    }
    per_target_seed = seed

    for target in _layer_targets(scene_config):
        layer_name = target["layer_name"]
        target_path = target["target_path"]
        layer_config = target["layer_config"]
        source_index = target["source_index"]
        existing_sidecar = _read_existing_sidecar(target_path) if _is_usable_audio(target_path) and not force else None
        if existing_sidecar is not None:
            _record_entry(
                manifest,
                target_path,
                tier="local_existing",
                metadata=existing_sidecar,
                dry_run=dry_run,
            )
            continue

        sourcing = _sourcing_config(layer_config)
        default_query = _infer_query(target_path)
        query = _pick_query(default_query, sourcing, source_index)
        if not dry_run:
            _cleanup_target_family(target_path)
        tier, metadata = _acquire_explicit(
            layer_name,
            query,
            default_query,
            target_path,
            per_target_seed,
            sourcing=sourcing,
            source_index=source_index,
            dry_run=dry_run,
        )
        if metadata is None:
            tier, metadata = _acquire_auto(
                layer_name,
                query,
                target_path,
                per_target_seed,
                sourcing=sourcing,
                dry_run=dry_run,
            )

        if not dry_run and target_path.exists():
            metadata = _write_provenance_sidecar(target_path, tier=tier, metadata=metadata)

        _record_entry(manifest, target_path, tier=tier, metadata=metadata, dry_run=dry_run)
        per_target_seed += 1

    if dry_run:
        return manifest
    return _write_manifest(manifest_path, manifest)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Populate scene audio sources from Freesound, NPS, Archive.org, procedural, and Stable Audio.")
    parser.add_argument("--scene", type=Path, required=True, help="Scene YAML file.")
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH, help="Manifest output path.")
    parser.add_argument("--seed", type=int, default=42, help="Base seed for procedural and Stable Audio generation.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve sourcing decisions without writing files.")
    parser.add_argument("--force", action="store_true", help="Rebuild sources even if valid local files already exist.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print dry-run JSON output.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = populate_scene_audio_sources(
        args.scene,
        manifest_path=args.manifest_path,
        seed=args.seed,
        dry_run=args.dry_run,
        force=args.force,
    )
    if args.dry_run:
        indent = 2 if args.pretty or args.dry_run else None
        print(json.dumps(result, ensure_ascii=False, indent=indent))
        return
    print(result)


if __name__ == "__main__":
    main()
