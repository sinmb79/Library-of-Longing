from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    from scripts.scene_config import load_scene_config
except ImportError:
    from scene_config import load_scene_config


if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "video"
DEFAULT_FRAME_RATE = 24
DEFAULT_CRF = 18
DEFAULT_PRESET = "slow"
DEFAULT_COLOR_TEMPERATURE = "warm"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


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


def _resolve_target_duration(scene_config: dict[str, Any], target_duration_sec: int | None) -> int:
    if target_duration_sec is not None:
        return int(target_duration_sec)
    return int(scene_config["video"]["target_duration_hours"] * 3600)


def _resolve_resolution(
    scene_config: dict[str, Any], output_resolution: tuple[int, int] | None
) -> tuple[int, int]:
    if output_resolution is not None:
        return int(output_resolution[0]), int(output_resolution[1])
    resolution = scene_config["visual"]["resolution"]
    return int(resolution[0]), int(resolution[1])


def _validate_color_temperature(color_temperature: str) -> str:
    normalized = color_temperature.strip().lower()
    if normalized not in {"warm", "neutral"}:
        raise ValueError("color_temperature must be 'warm' or 'neutral'.")
    return normalized


def _basic_filter_chain(
    *,
    output_resolution: tuple[int, int],
    frame_rate: int,
    film_grain: int,
    vignette: bool,
    color_temperature: str,
) -> str:
    width, height = output_resolution
    filters = [
        f"scale={width}:{height}:flags=lanczos",
        "setsar=1",
        f"fps={frame_rate}",
    ]
    if film_grain > 0:
        filters.append(f"noise=alls={int(film_grain)}:allf=t")
    if vignette:
        filters.append("vignette")
    if _validate_color_temperature(color_temperature) == "warm":
        filters.append("colorbalance=rs=0.04:gs=0.02:bs=-0.03")
    filters.append("format=yuv420p")
    return ",".join(filters)


def build_basic_loop_command(
    *,
    loop_clip: Path,
    output_path: Path,
    scene_config: dict[str, Any],
    target_duration_sec: int | None = None,
    output_resolution: tuple[int, int] | None = None,
    film_grain: int | None = None,
    vignette: bool | None = None,
    color_temperature: str = DEFAULT_COLOR_TEMPERATURE,
    frame_rate: int = DEFAULT_FRAME_RATE,
    crf: int = DEFAULT_CRF,
    preset: str = DEFAULT_PRESET,
) -> list[str]:
    target_duration = _resolve_target_duration(scene_config, target_duration_sec)
    resolved_grain = int(scene_config["video"]["film_grain"] if film_grain is None else film_grain)
    resolved_vignette = bool(scene_config["video"]["vignette"] if vignette is None else vignette)
    resolved_resolution = _resolve_resolution(scene_config, output_resolution)
    filter_chain = _basic_filter_chain(
        output_resolution=resolved_resolution,
        frame_rate=frame_rate,
        film_grain=resolved_grain,
        vignette=resolved_vignette,
        color_temperature=color_temperature,
    )
    return [
        "ffmpeg",
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        str(loop_clip),
        "-t",
        str(target_duration),
        "-vf",
        filter_chain,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(frame_rate),
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def _timelapse_input_args(source: Path, segment_duration_sec: int) -> list[str]:
    if source.suffix.lower() in IMAGE_EXTENSIONS:
        return ["-loop", "1", "-t", str(segment_duration_sec), "-i", str(source)]
    return ["-stream_loop", "-1", "-t", str(segment_duration_sec), "-i", str(source)]


def _timelapse_filter_complex(
    *,
    input_count: int,
    output_resolution: tuple[int, int],
    segment_duration_sec: int,
    transition_duration_sec: int,
    film_grain: int,
    vignette: bool,
    color_temperature: str,
    frame_rate: int,
) -> str:
    width, height = output_resolution
    graph: list[str] = []
    for index in range(input_count):
        graph.append(
            f"[{index}:v]scale={width}:{height}:flags=lanczos,setsar=1,fps={frame_rate},format=yuv420p[s{index}]"
        )

    previous = "s0"
    overlap = max(1, segment_duration_sec - transition_duration_sec)
    for index in range(1, input_count):
        offset = overlap * index
        output_label = f"xf{index}"
        graph.append(
            f"[{previous}][s{index}]xfade=transition=fade:duration={transition_duration_sec}:offset={offset}[{output_label}]"
        )
        previous = output_label

    post_filters: list[str] = []
    if film_grain > 0:
        post_filters.append(f"noise=alls={int(film_grain)}:allf=t")
    if vignette:
        post_filters.append("vignette")
    if _validate_color_temperature(color_temperature) == "warm":
        post_filters.append("colorbalance=rs=0.04:gs=0.02:bs=-0.03")
    post_filters.append("format=yuv420p")
    graph.append(f"[{previous}]{','.join(post_filters)}[outv]")
    return ";".join(graph)


def build_timelapse_command(
    *,
    segment_sources: Iterable[Path],
    output_path: Path,
    output_resolution: tuple[int, int],
    segment_duration_sec: int,
    transition_duration_sec: int,
    film_grain: int = 15,
    vignette: bool = True,
    color_temperature: str = DEFAULT_COLOR_TEMPERATURE,
    frame_rate: int = DEFAULT_FRAME_RATE,
    crf: int = DEFAULT_CRF,
    preset: str = DEFAULT_PRESET,
) -> list[str]:
    sources = [Path(item) for item in segment_sources]
    if len(sources) < 2:
        raise ValueError("Time-lapse mode requires at least two segment sources.")

    cmd = ["ffmpeg", "-y"]
    for source in sources:
        cmd.extend(_timelapse_input_args(source, segment_duration_sec))
    cmd.extend(
        [
            "-filter_complex",
            _timelapse_filter_complex(
                input_count=len(sources),
                output_resolution=output_resolution,
                segment_duration_sec=segment_duration_sec,
                transition_duration_sec=transition_duration_sec,
                film_grain=film_grain,
                vignette=vignette,
                color_temperature=color_temperature,
                frame_rate=frame_rate,
            ),
            "-map",
            "[outv]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(frame_rate),
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return cmd


def _run_ffmpeg(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-1000:])


def compose_basic_video(
    *,
    loop_clip: Path,
    output_path: Path,
    scene_config: dict[str, Any],
    target_duration_sec: int | None = None,
    output_resolution: tuple[int, int] | None = None,
    film_grain: int | None = None,
    vignette: bool | None = None,
    color_temperature: str = DEFAULT_COLOR_TEMPERATURE,
    frame_rate: int = DEFAULT_FRAME_RATE,
    crf: int = DEFAULT_CRF,
    preset: str = DEFAULT_PRESET,
) -> Path:
    if not loop_clip.exists():
        raise FileNotFoundError(f"Loop clip not found: {loop_clip}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_basic_loop_command(
        loop_clip=loop_clip,
        output_path=output_path,
        scene_config=scene_config,
        target_duration_sec=target_duration_sec,
        output_resolution=output_resolution,
        film_grain=film_grain,
        vignette=vignette,
        color_temperature=color_temperature,
        frame_rate=frame_rate,
        crf=crf,
        preset=preset,
    )
    _run_ffmpeg(cmd)
    return output_path


def compose_timelapse_video(
    *,
    segment_sources: Iterable[Path],
    output_path: Path,
    scene_config: dict[str, Any],
    segment_duration_sec: int,
    transition_duration_sec: int,
    output_resolution: tuple[int, int] | None = None,
    film_grain: int | None = None,
    vignette: bool | None = None,
    color_temperature: str = DEFAULT_COLOR_TEMPERATURE,
    frame_rate: int = DEFAULT_FRAME_RATE,
    crf: int = DEFAULT_CRF,
    preset: str = DEFAULT_PRESET,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_resolution = _resolve_resolution(scene_config, output_resolution)
    resolved_grain = int(scene_config["video"]["film_grain"] if film_grain is None else film_grain)
    resolved_vignette = bool(scene_config["video"]["vignette"] if vignette is None else vignette)
    cmd = build_timelapse_command(
        segment_sources=segment_sources,
        output_path=output_path,
        output_resolution=resolved_resolution,
        segment_duration_sec=segment_duration_sec,
        transition_duration_sec=transition_duration_sec,
        film_grain=resolved_grain,
        vignette=resolved_vignette,
        color_temperature=color_temperature,
        frame_rate=frame_rate,
        crf=crf,
        preset=preset,
    )
    _run_ffmpeg(cmd)
    return output_path


def _default_output_path(scene_path: Path, scene_config: dict[str, Any], mode: str) -> Path:
    slug = scene_config["scene"]["slug"]
    suffix = "timelapse" if mode == "timelapse" else f"{scene_config['video']['target_duration_hours']}h"
    return DEFAULT_OUTPUT_DIR / f"{slug}_{suffix}.mp4"


def _render_command_preview(cmd: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compose long-form ambient video loops with FFmpeg.")
    parser.add_argument("--scene", type=Path, required=True, help="Path to the scene YAML file.")
    parser.add_argument("--mode", choices=["basic", "timelapse"], default=None, help="Composition mode.")
    parser.add_argument("--loop-clip", type=Path, help="Input loop clip for basic mode.")
    parser.add_argument(
        "--timelapse-source",
        type=Path,
        action="append",
        default=[],
        help="Image or video source for a time-lapse segment. Repeat for multiple segments.",
    )
    parser.add_argument("--segment-duration-sec", type=int, default=6, help="Per-segment hold length in time-lapse mode.")
    parser.add_argument("--transition-duration-sec", type=int, default=2, help="Crossfade length in time-lapse mode.")
    parser.add_argument("--output", type=Path, default=None, help="Output MP4 path.")
    parser.add_argument("--target-duration-sec", type=int, default=None, help="Override target duration for basic mode.")
    parser.add_argument("--film-grain", type=int, default=None, help="Override grain intensity (0-100).")
    parser.add_argument("--vignette", choices=["on", "off"], default=None, help="Override vignette toggle.")
    parser.add_argument(
        "--color-temperature",
        choices=["warm", "neutral"],
        default=DEFAULT_COLOR_TEMPERATURE,
        help="Post-processing color temperature.",
    )
    parser.add_argument("--width", type=int, default=None, help="Override output width.")
    parser.add_argument("--height", type=int, default=None, help="Override output height.")
    parser.add_argument("--dry-run", action="store_true", help="Print the FFmpeg command without running it.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    scene_config = load_scene_config(args.scene)
    mode = args.mode or ("timelapse" if scene_config["video"]["time_lapse"] else "basic")
    output_resolution = None
    if args.width is not None or args.height is not None:
        if args.width is None or args.height is None:
            raise SystemExit("--width and --height must be provided together.")
        output_resolution = (args.width, args.height)

    output_path = args.output or _default_output_path(args.scene, scene_config, mode)
    vignette = None if args.vignette is None else args.vignette == "on"

    if mode == "basic":
        if args.loop_clip is None:
            raise SystemExit("--loop-clip is required in basic mode.")
        cmd = build_basic_loop_command(
            loop_clip=args.loop_clip,
            output_path=output_path,
            scene_config=scene_config,
            target_duration_sec=args.target_duration_sec,
            output_resolution=output_resolution,
            film_grain=args.film_grain,
            vignette=vignette,
            color_temperature=args.color_temperature,
        )
    else:
        if len(args.timelapse_source) < 2:
            raise SystemExit("At least two --timelapse-source values are required in timelapse mode.")
        cmd = build_timelapse_command(
            segment_sources=args.timelapse_source,
            output_path=output_path,
            output_resolution=_resolve_resolution(scene_config, output_resolution),
            segment_duration_sec=args.segment_duration_sec,
            transition_duration_sec=args.transition_duration_sec,
            film_grain=int(scene_config["video"]["film_grain"] if args.film_grain is None else args.film_grain),
            vignette=bool(scene_config["video"]["vignette"] if vignette is None else vignette),
            color_temperature=args.color_temperature,
        )

    if args.dry_run:
        print(_render_command_preview(cmd))
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(cmd)
    print(output_path)


if __name__ == "__main__":
    main()
