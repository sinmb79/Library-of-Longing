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


def _description_text(scene_config: dict[str, Any]) -> str:
    metadata = scene_config["metadata"]
    return (
        f"{metadata['title']['ko']}\n"
        f"{metadata['title']['en']}\n\n"
        f"{metadata['description']['ko']}\n\n"
        f"{metadata['description']['en']}\n\n"
        f"Storyline (KO): {metadata['storyline']['ko']}\n\n"
        f"Storyline (EN): {metadata['storyline']['en']}"
    )


def build_youtube_metadata(
    scene_config: dict[str, Any],
    *,
    final_video_path: Path,
    thumbnail_path: Path | None = None,
) -> dict[str, Any]:
    metadata = scene_config["metadata"]
    return {
        "sceneId": scene_config["scene"]["id"],
        "slug": scene_config["scene"]["slug"],
        "title": metadata["title"]["ko"],
        "title_en": metadata["title"]["en"],
        "description": _description_text(scene_config),
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
    }


def build_thumbnail_request(scene_config: dict[str, Any], *, base_image_path: Path | None = None) -> dict[str, Any]:
    metadata = scene_config["metadata"]
    return {
        "scene": scene_config["scene"],
        "title": metadata["title"],
        "durationLabel": {"ko": "10시간", "en": "10 Hours"},
        "baseImagePath": base_image_path.resolve().as_posix() if base_image_path else None,
        "style": scene_config["visual"]["style"],
        "resolution": [1280, 720],
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

    metadata_path = metadata_output_path or output_path.with_suffix(".youtube.json")
    thumbnail_request_path = thumbnail_request_output_path or output_path.with_suffix(".thumbnail_request.json")

    _write_json(
        metadata_path,
        build_youtube_metadata(scene_config, final_video_path=output_path, thumbnail_path=thumbnail_path),
    )
    _write_json(
        thumbnail_request_path,
        build_thumbnail_request(scene_config, base_image_path=base_image_path or thumbnail_path),
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
