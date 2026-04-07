from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.scene_config import load_scene_config
from scripts.video_compositor import (
    build_basic_loop_command,
    build_timelapse_command,
    compose_basic_video,
    get_duration,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _make_test_clip(path: Path, *, duration_sec: float = 0.5, resolution: tuple[int, int] = (320, 180)) -> Path:
    width, height = resolution
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size={width}x{height}:rate=12:duration={duration_sec}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return path


def test_build_basic_command_uses_scene_defaults() -> None:
    scene = load_scene_config(PROJECT_ROOT / "scenes" / "001_grandma_porch_summer.yaml")

    cmd = build_basic_loop_command(
        loop_clip=Path("loop.mp4"),
        output_path=Path("output.mp4"),
        scene_config=scene,
    )

    joined = " ".join(cmd)

    assert cmd[:2] == ["ffmpeg", "-y"]
    assert "-stream_loop" in cmd
    assert "-1" in cmd
    assert "noise=alls=15:allf=t" in joined
    assert "vignette" in joined
    assert "colorbalance=" in joined
    assert "scale=3840:2160:flags=lanczos" in joined
    assert "fps=24" in joined
    assert "libx264" in cmd
    assert "slow" in cmd
    assert "18" in cmd
    assert "36000" in cmd


def test_build_basic_command_respects_neutral_and_no_vignette() -> None:
    scene = load_scene_config(PROJECT_ROOT / "scenes" / "001_grandma_porch_summer.yaml")

    cmd = build_basic_loop_command(
        loop_clip=Path("loop.mp4"),
        output_path=Path("output.mp4"),
        scene_config=scene,
        vignette=False,
        color_temperature="neutral",
        film_grain=0,
    )

    joined = " ".join(cmd)

    assert "vignette" not in joined
    assert "colorbalance=" not in joined
    assert "noise=alls=" not in joined


def test_build_timelapse_command_creates_xfade_graph() -> None:
    cmd = build_timelapse_command(
        segment_sources=[Path("dawn.png"), Path("noon.png"), Path("night.png")],
        output_path=Path("timelapse.mp4"),
        output_resolution=(3840, 2160),
        segment_duration_sec=2,
        transition_duration_sec=1,
    )

    joined = " ".join(cmd)

    assert "-filter_complex" in cmd
    assert "xfade=transition=fade:duration=1:offset=1" in joined
    assert "xfade=transition=fade:duration=1:offset=2" in joined
    assert "scale=3840:2160:flags=lanczos" in joined
    assert "colorbalance=" in joined


def test_compose_basic_video_writes_short_output(tmp_path: Path) -> None:
    clip = _make_test_clip(tmp_path / "loop.mp4")
    scene = load_scene_config(PROJECT_ROOT / "scenes" / "001_grandma_porch_summer.yaml")

    out = compose_basic_video(
        loop_clip=clip,
        output_path=tmp_path / "composed.mp4",
        scene_config=scene,
        target_duration_sec=2,
        output_resolution=(640, 360),
        film_grain=4,
        vignette=False,
        color_temperature="neutral",
    )

    assert out.exists()
    assert get_duration(out) >= 1.8
