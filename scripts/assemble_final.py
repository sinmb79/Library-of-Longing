from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.scene_config import load_scene_config
except ImportError:
    from scene_config import load_scene_config


if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "final"


def get_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ]
    ).decode("utf-8", errors="replace").strip()
    return float(out)


def build_mux_command(*, video_path: Path, audio_path: Path, output_path: Path) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "256k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def _strip_duration_suffix(title: str) -> str:
    return title.split("|", 1)[0].strip()


def _format_duration_value(duration_sec: float) -> dict[str, str]:
    rounded = max(1, int(round(duration_sec)))
    if rounded >= 3600 and rounded % 3600 == 0:
        hours = rounded // 3600
        return {
            "ko": f"{hours}\uC2DC\uAC04",
            "en": f"{hours} Hour" if hours == 1 else f"{hours} Hours",
        }
    if rounded >= 60 and rounded % 60 == 0:
        minutes = rounded // 60
        return {
            "ko": f"{minutes}\uBD84",
            "en": f"{minutes} Minute" if minutes == 1 else f"{minutes} Minutes",
        }
    return {
        "ko": f"{rounded}\uCD08",
        "en": f"{rounded} Second" if rounded == 1 else f"{rounded} Seconds",
    }


def _full_length_duration_label(scene_config: dict[str, Any]) -> dict[str, str]:
    hours = int(scene_config.get("video", {}).get("target_duration_hours", 10))
    return {
        "ko": f"{hours}\uC2DC\uAC04",
        "en": f"{hours} Hour" if hours == 1 else f"{hours} Hours",
    }


def _resolve_duration_context(scene_config: dict[str, Any], duration_sec: float | None) -> dict[str, Any]:
    metadata = scene_config["metadata"]
    if duration_sec is None:
        return {
            "title_ko": metadata["title"]["ko"],
            "title_en": metadata["title"]["en"],
            "duration_label": _full_length_duration_label(scene_config),
            "prototype_note": None,
            "is_prototype": False,
        }

    target_hours = float(scene_config.get("video", {}).get("target_duration_hours", 0))
    target_duration_sec = target_hours * 3600
    is_prototype = bool(target_duration_sec and duration_sec < target_duration_sec * 0.95)
    if not is_prototype:
        return {
            "title_ko": metadata["title"]["ko"],
            "title_en": metadata["title"]["en"],
            "duration_label": _full_length_duration_label(scene_config),
            "prototype_note": None,
            "is_prototype": False,
        }

    short_label = _format_duration_value(duration_sec)
    prototype_label = {
        "ko": f"{short_label['ko']} \uD504\uB85C\uD1A0\uD0C0\uC785",
        "en": f"{short_label['en']} Prototype",
    }
    return {
        "title_ko": f"{_strip_duration_suffix(metadata['title']['ko'])} | {prototype_label['ko']}",
        "title_en": f"{_strip_duration_suffix(metadata['title']['en'])} | {prototype_label['en']}",
        "duration_label": prototype_label,
        "prototype_note": {
            "ko": f"\uD504\uB85C\uD1A0\uD0C0\uC785 \uAE38\uC774: {short_label['ko']}",
            "en": f"Prototype length: {short_label['en']}",
        },
        "is_prototype": True,
    }


def _description_text(
    scene_config: dict[str, Any],
    *,
    title_ko: str,
    title_en: str,
    prototype_note: dict[str, str] | None,
) -> str:
    metadata = scene_config["metadata"]
    lines = [title_ko, title_en]
    if prototype_note is not None:
        lines.extend(["", prototype_note["ko"], prototype_note["en"]])
    lines.extend(
        [
            "",
            metadata["description"]["ko"],
            "",
            metadata["description"]["en"],
            "",
            f"Storyline (KO): {metadata['storyline']['ko']}",
            "",
            f"Storyline (EN): {metadata['storyline']['en']}",
        ]
    )
    return "\n".join(lines)


def build_youtube_metadata(
    scene_config: dict[str, Any],
    *,
    final_video_path: Path,
    thumbnail_path: Path | None = None,
    duration_sec: float | None = None,
) -> dict[str, Any]:
    metadata = scene_config["metadata"]
    duration_context = _resolve_duration_context(scene_config, duration_sec)
    return {
        "sceneId": scene_config["scene"]["id"],
        "slug": scene_config["scene"]["slug"],
        "title": duration_context["title_ko"],
        "title_en": duration_context["title_en"],
        "description": _description_text(
            scene_config,
            title_ko=duration_context["title_ko"],
            title_en=duration_context["title_en"],
            prototype_note=duration_context["prototype_note"],
        ),
        "tags": metadata["tags"],
        "storyline": metadata["storyline"],
        "categoryId": "10",
        "defaultLanguage": "ko",
        "defaultAudioLanguage": "ko",
        "privacyStatus": "private",
        "madeForKids": False,
        "thumbnailPath": thumbnail_path.resolve().as_posix() if thumbnail_path else None,
        "videoPath": final_video_path.resolve().as_posix(),
        "culture": metadata["culture"],
        "season": metadata["season"],
        "durationSec": duration_sec,
        "durationLabel": duration_context["duration_label"],
        "isPrototype": duration_context["is_prototype"],
    }


def build_thumbnail_request(
    scene_config: dict[str, Any],
    *,
    base_image_path: Path | None = None,
    duration_sec: float | None = None,
) -> dict[str, Any]:
    duration_context = _resolve_duration_context(scene_config, duration_sec)
    return {
        "scene": scene_config["scene"],
        "title": {
            "ko": duration_context["title_ko"],
            "en": duration_context["title_en"],
        },
        "durationLabel": duration_context["duration_label"],
        "baseImagePath": base_image_path.resolve().as_posix() if base_image_path else None,
        "style": scene_config["visual"]["style"],
        "resolution": [1280, 720],
        "isPrototype": duration_context["is_prototype"],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _run_ffmpeg(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-1000:])


def assemble_final(
    *,
    video_path: Path,
    audio_path: Path,
    scene_config: dict[str, Any],
    output_path: Path,
    thumbnail_path: Path | None = None,
    base_image_path: Path | None = None,
    metadata_output_path: Path | None = None,
    thumbnail_request_output_path: Path | None = None,
) -> dict[str, Path]:
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(build_mux_command(video_path=video_path, audio_path=audio_path, output_path=output_path))
    final_duration_sec = get_duration(output_path)

    metadata_path = metadata_output_path or output_path.with_suffix(".youtube.json")
    thumbnail_request_path = thumbnail_request_output_path or output_path.with_suffix(".thumbnail_request.json")

    _write_json(
        metadata_path,
        build_youtube_metadata(
            scene_config,
            final_video_path=output_path,
            thumbnail_path=thumbnail_path,
            duration_sec=final_duration_sec,
        ),
    )
    _write_json(
        thumbnail_request_path,
        build_thumbnail_request(
            scene_config,
            base_image_path=base_image_path or thumbnail_path,
            duration_sec=final_duration_sec,
        ),
    )

    return {
        "final_video": output_path,
        "metadata_json": metadata_path,
        "thumbnail_request_json": thumbnail_request_path,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge a rendered video and audio bed into a final delivery file.")
    parser.add_argument("--scene", type=Path, required=True, help="Path to the scene YAML file.")
    parser.add_argument("--video", type=Path, required=True, help="Input video from C3.")
    parser.add_argument("--audio", type=Path, required=True, help="Input audio from C1.")
    parser.add_argument("--output", type=Path, default=None, help="Output final MP4 path.")
    parser.add_argument("--thumbnail", type=Path, default=None, help="Optional thumbnail JPG path for metadata.")
    parser.add_argument("--base-image", type=Path, default=None, help="Optional still image path used for thumbnail requests.")
    parser.add_argument("--metadata-output", type=Path, default=None, help="Override YouTube metadata JSON path.")
    parser.add_argument(
        "--thumbnail-request-output",
        type=Path,
        default=None,
        help="Override thumbnail request JSON path.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    scene_config = load_scene_config(args.scene)
    output_path = args.output or (DEFAULT_OUTPUT_DIR / f"{scene_config['scene']['slug']}_final.mp4")
    result = assemble_final(
        video_path=args.video,
        audio_path=args.audio,
        scene_config=scene_config,
        output_path=output_path,
        thumbnail_path=args.thumbnail,
        base_image_path=args.base_image,
        metadata_output_path=args.metadata_output,
        thumbnail_request_output_path=args.thumbnail_request_output,
    )
    print(json.dumps({key: value.as_posix() for key, value in result.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
