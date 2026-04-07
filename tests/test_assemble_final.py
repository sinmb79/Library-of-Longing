from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.assemble_final import (
    assemble_final,
    build_mux_command,
    build_thumbnail_request,
    build_youtube_metadata,
    get_duration,
)
from scripts.scene_config import load_scene_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _make_test_video(path: Path, duration_sec: float = 1.0) -> Path:
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=640x360:rate=24:duration={duration_sec}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return path


def _make_test_audio(path: Path, duration_sec: float = 1.0) -> Path:
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=220:sample_rate=48000:duration={duration_sec}",
        "-c:a",
        "pcm_s24le",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return path


def test_build_youtube_metadata_from_scene() -> None:
    scene = load_scene_config(PROJECT_ROOT / "scenes" / "001_grandma_porch_summer.yaml")

    metadata = build_youtube_metadata(
        scene,
        final_video_path=Path("output/final/grandma.mp4"),
        thumbnail_path=Path("output/thumbnails/grandma.jpg"),
    )

    assert metadata["title"] == scene["metadata"]["title"]["ko"]
    assert metadata["defaultLanguage"] == "ko"
    assert metadata["thumbnailPath"].endswith("grandma.jpg")
    assert "Grandmother's Porch" in metadata["description"]
    assert metadata["tags"] == scene["metadata"]["tags"]


def test_build_mux_command_sets_expected_ffmpeg_flags() -> None:
    cmd = build_mux_command(
        video_path=Path("video.mp4"),
        audio_path=Path("audio.wav"),
        output_path=Path("final.mp4"),
    )

    assert cmd[:2] == ["ffmpeg", "-y"]
    assert "-c:v" in cmd and "copy" in cmd
    assert "-c:a" in cmd and "aac" in cmd
    assert "-b:a" in cmd and "256k" in cmd
    assert "+faststart" in cmd


def test_assemble_final_creates_muxed_output_and_sidecars(tmp_path: Path) -> None:
    scene = load_scene_config(PROJECT_ROOT / "scenes" / "001_grandma_porch_summer.yaml")
    video = _make_test_video(tmp_path / "loop.mp4")
    audio = _make_test_audio(tmp_path / "mix.wav", duration_sec=1.2)
    thumbnail = tmp_path / "thumb.jpg"
    thumbnail.write_bytes(b"fake-thumb")

    result = assemble_final(
        video_path=video,
        audio_path=audio,
        scene_config=scene,
        output_path=tmp_path / "final.mp4",
        thumbnail_path=thumbnail,
    )

    assert result["final_video"].exists()
    assert result["metadata_json"].exists()
    assert result["thumbnail_request_json"].exists()
    assert get_duration(result["final_video"]) >= 0.9

    payload = json.loads(result["metadata_json"].read_text(encoding="utf-8"))
    thumb_request = json.loads(result["thumbnail_request_json"].read_text(encoding="utf-8"))

    assert payload["thumbnailPath"].endswith("thumb.jpg")
    assert thumb_request["title"]["ko"] == scene["metadata"]["title"]["ko"]


def test_build_thumbnail_request_includes_scene_identity() -> None:
    scene = load_scene_config(PROJECT_ROOT / "scenes" / "001_grandma_porch_summer.yaml")

    request = build_thumbnail_request(scene, base_image_path=Path("output/video/still.png"))

    assert request["scene"]["id"] == "001"
    assert request["baseImagePath"].endswith("still.png")
