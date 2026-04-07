from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import jsonschema
import yaml

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "scenes" / "schema.yaml"


def load_scene_schema(schema_path: Path | None = None) -> dict[str, Any]:
    target = schema_path or DEFAULT_SCHEMA_PATH
    with target.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _resolve_source_value(value: str, source_path: Path) -> str:
    if "://" in value or ":" in value and not value.startswith((".", "..")) and not Path(value).drive:
        return value
    path = Path(value)
    if not path.is_absolute():
        if value.startswith((".", "..")):
            path = (source_path.parent / path).resolve()
        else:
            path = (PROJECT_ROOT / path).resolve()
    else:
        path = (source_path.parent / path).resolve()
    return path.as_posix()


def normalize_scene_config(raw_config: dict[str, Any], source_path: Path) -> dict[str, Any]:
    config = deepcopy(raw_config)
    config.setdefault("_meta", {})
    config["_meta"]["source_path"] = source_path.resolve().as_posix()
    config["_meta"]["project_root"] = PROJECT_ROOT.as_posix()

    layers = config["audio"]["layers"]
    for key in ("room_tone", "continuous"):
        layers[key]["source_path"] = _resolve_source_value(layers[key]["source"], source_path)

    for key in ("periodic", "rare_events"):
        layers[key]["source_paths"] = [_resolve_source_value(item, source_path) for item in layers[key]["sources"]]
        layers[key]["interval"] = [int(layers[key]["interval"][0]), int(layers[key]["interval"][1])]

    config["visual"]["resolution"] = [int(config["visual"]["resolution"][0]), int(config["visual"]["resolution"][1])]
    config["visual"]["loop_duration_sec"] = int(config["visual"]["loop_duration_sec"])
    config["video"]["target_duration_hours"] = int(config["video"]["target_duration_hours"])
    config["video"]["film_grain"] = int(config["video"]["film_grain"])
    config["video"]["vignette"] = bool(config["video"]["vignette"])
    config["video"]["time_lapse"] = bool(config["video"]["time_lapse"])
    if "time_lapse_segments" in config["video"]:
        segments = []
        for segment in config["video"]["time_lapse_segments"]:
            normalized_segment = deepcopy(segment)
            normalized_segment["source_path"] = _resolve_source_value(segment["source"], source_path)
            segments.append(normalized_segment)
        config["video"]["time_lapse_segments"] = segments
    return config


def load_scene_config(config_path: Path, schema_path: Path | None = None) -> dict[str, Any]:
    target = config_path.resolve()
    with target.open("r", encoding="utf-8") as handle:
        raw_config = yaml.safe_load(handle)
    jsonschema.validate(instance=raw_config, schema=load_scene_schema(schema_path))
    return normalize_scene_config(raw_config, source_path=target)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load and validate a Library of Longing scene config.")
    parser.add_argument("scene", type=Path, help="Path to the scene YAML file.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_PATH, help="Path to the schema YAML file.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = load_scene_config(args.scene, schema_path=args.schema)
    indent = 2 if args.pretty else None
    print(json.dumps(config, ensure_ascii=False, indent=indent))


if __name__ == "__main__":
    main()
