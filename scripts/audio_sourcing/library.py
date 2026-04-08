from __future__ import annotations

import argparse
import hashlib
import json
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
from scripts.audio_sourcing.archive_org_fetcher import search as search_archive
from scripts.audio_sourcing.freesound_fetcher import download_sound, search_cc0
from scripts.audio_sourcing.nps_fetcher import download as download_nps
from scripts.audio_sourcing.nps_fetcher import list_catalog
from scripts.audio_sourcing.procedural_gen import write_procedural_wav
from scripts.audio_sourcing.stable_audio_gen import generate_sfx
from scripts.scene_config import load_scene_config


DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "audio_sources" / "MANIFEST.json"
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


def _layer_targets(scene_config: dict[str, Any]) -> list[tuple[str, Path]]:
    layers = scene_config["audio"]["layers"]
    targets: list[tuple[str, Path]] = [
        ("room_tone", Path(layers["room_tone"]["source_path"])),
        ("continuous", Path(layers["continuous"]["source_path"])),
    ]
    targets.extend(("periodic", Path(path)) for path in layers["periodic"]["source_paths"])
    targets.extend(("rare_events", Path(path)) for path in layers["rare_events"]["source_paths"])
    return targets


def _infer_query(target_path: Path) -> str:
    return target_path.stem.replace("_", " ").replace("-", " ").strip().lower()


def _is_biological(query: str) -> bool:
    return any(keyword in query for keyword in BIOLOGICAL_KEYWORDS)


def _procedural_type(layer_name: str, query: str) -> str | None:
    if layer_name == "room_tone":
        return "room_tone"
    if layer_name == "continuous" and "fan" in query:
        return "fan"
    for keyword, generator in PROCEDURAL_MAP.items():
        if keyword in query:
            return generator
    return None


def _stable_prompt(query: str, layer_name: str) -> str:
    return f"clean isolated {query.replace('_', ' ')}, high quality ambient detail, no music, no voice"


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
) -> None:
    key = _relative_path(target_path)
    manifest["sources"][key] = {
        "tier": tier,
        **metadata,
        "sha256": _sha256(target_path),
    }


def _is_usable_audio(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 4096:
        return False
    try:
        info = sf.info(path)
    except Exception:
        return False
    return info.frames > 0 and info.samplerate > 0 and info.channels >= 1


def _acquire_with_freesound(query: str, target_path: Path) -> dict[str, Any] | None:
    results = search_cc0(query, min_duration=5, max_duration=60, max_results=3)
    if not results:
        return None
    selected = results[0]
    download_sound(selected["sound_id"], target_path)
    return {
        "license": selected["license"],
        "origin_url": selected["url"],
        "author": selected["author"],
        "original_title": selected["name"],
        "duration_sec": selected.get("duration"),
    }


def _acquire_with_nps(query: str, target_path: Path) -> dict[str, Any] | None:
    entries = list_catalog(rate_limit_sec=0.0)
    match = _find_nps_match(query, entries)
    if match is None:
        return None
    downloaded = download_nps(match, target_path.parent, output_filename=target_path.name)
    _move_into_place(downloaded, target_path)
    return {
        "license": "US Public Domain",
        "origin_url": match["page_url"],
        "author": "National Park Service",
        "original_title": match["title"],
        "category": match["category"],
    }


def _acquire_with_archive(query: str, target_path: Path) -> dict[str, Any] | None:
    docs = search_archive(query, collection=None, max_results=3)
    for doc in docs:
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
            "license": sidecar.get("license", "Public Domain"),
            "origin_url": sidecar.get("origin_url", ""),
            "author": sidecar.get("creator", doc.get("creator", "")),
            "original_title": sidecar.get("title", doc.get("title", "")),
            "item_id": doc["identifier"],
        }
    return None


def _acquire_with_procedural(layer_name: str, query: str, target_path: Path, seed: int) -> dict[str, Any] | None:
    generator = _procedural_type(layer_name, query)
    if generator is None:
        return None
    write_procedural_wav(generator, target_path, duration=30.0, seed=seed)
    return {
        "generator": generator,
        "license": "Synthetic / Internal",
        "origin_url": "",
        "duration_sec": 30.0,
        "seed": seed,
    }


def _acquire_with_stable(query: str, target_path: Path, seed: int) -> dict[str, Any]:
    generate_sfx(prompt=_stable_prompt(query, "rare_events"), duration=8.0, seed=seed, output_path=target_path)
    return {
        "license": "Synthetic / Internal",
        "origin_url": "",
        "prompt": _stable_prompt(query, "rare_events"),
        "seed": seed,
        "duration_sec": 8.0,
    }


def populate_scene_audio_sources(
    scene_path: Path,
    *,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    seed: int = 42,
) -> Path:
    scene_config = load_scene_config(scene_path)
    manifest = {
        "scene_id": scene_config["scene"]["id"],
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": {},
    }
    per_target_seed = seed
    for layer_name, target_path in _layer_targets(scene_config):
        relative_key = _relative_path(target_path)
        if _is_usable_audio(target_path):
            _record_entry(
                manifest,
                target_path,
                tier="local_existing",
                metadata={"license": "Local File", "origin_url": "", "author": "", "original_title": target_path.name},
            )
            continue

        query = _infer_query(target_path)
        metadata: dict[str, Any] | None = None
        tier = ""

        procedural_metadata = _acquire_with_procedural(layer_name, query, target_path, seed=per_target_seed)
        if procedural_metadata is not None:
            metadata = procedural_metadata
            tier = "procedural"
        elif _prefer_stable(layer_name, query):
            metadata = _acquire_with_stable(query, target_path, seed=per_target_seed)
            tier = "stable_audio"
        else:
            freesound_metadata = _acquire_with_freesound(query, target_path)
            if freesound_metadata is not None:
                metadata = freesound_metadata
                tier = "freesound_cc0"
            else:
                if _is_biological(query):
                    nps_metadata = _acquire_with_nps(query, target_path)
                    if nps_metadata is not None:
                        metadata = nps_metadata
                        tier = "nps_pd"
                if metadata is None:
                    archive_metadata = _acquire_with_archive(query, target_path)
                    if archive_metadata is not None:
                        metadata = archive_metadata
                        tier = "archive_pd"
                if metadata is None:
                    metadata = _acquire_with_stable(query, target_path, seed=per_target_seed)
                    tier = "stable_audio"

        _record_entry(manifest, target_path, tier=tier, metadata=metadata or {})
        per_target_seed += 1

    return _write_manifest(manifest_path, manifest)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Populate scene audio sources from Freesound, NPS, Archive.org, procedural, and Stable Audio.")
    parser.add_argument("--scene", type=Path, required=True, help="Scene YAML file.")
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH, help="Manifest output path.")
    parser.add_argument("--seed", type=int, default=42, help="Base seed for procedural and Stable Audio generation.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    print(populate_scene_audio_sources(args.scene, manifest_path=args.manifest_path, seed=args.seed))


if __name__ == "__main__":
    main()
