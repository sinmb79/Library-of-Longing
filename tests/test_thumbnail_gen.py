from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from scripts.scene_config import load_scene_config
from scripts.thumbnail_gen import (
    THUMBNAIL_HEIGHT,
    THUMBNAIL_WIDTH,
    build_thumbnail_workflow,
    render_thumbnail,
    write_thumbnail_workflow,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _make_base_image(path: Path, size: tuple[int, int] = (1920, 1080)) -> Path:
    Image.new("RGB", size, (180, 150, 120)).save(path)
    return path


def test_build_thumbnail_workflow_references_input_image() -> None:
    scene = load_scene_config(PROJECT_ROOT / "scenes" / "001_grandma_porch_summer.yaml")

    workflow = build_thumbnail_workflow(
        scene_config=scene,
        uploaded_image_name="still.png",
        output_prefix="grandma_thumb",
    )

    assert workflow["1"]["inputs"]["image"] == "still.png"
    assert workflow["3"]["inputs"]["lora_name"] == "ghibli_style_sdxl.safetensors"
    assert workflow["9"]["inputs"]["filename_prefix"] == "grandma_thumb_variant"


def test_render_thumbnail_writes_1280x720_jpg(tmp_path: Path) -> None:
    scene = load_scene_config(PROJECT_ROOT / "scenes" / "001_grandma_porch_summer.yaml")
    base_image = _make_base_image(tmp_path / "base.png")

    out = render_thumbnail(
        scene_config=scene,
        base_image_path=base_image,
        output_path=tmp_path / "thumb.jpg",
    )

    assert out.suffix == ".jpg"
    with Image.open(out) as image:
        assert image.size == (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT)


def test_write_thumbnail_workflow_serializes_json(tmp_path: Path) -> None:
    scene = load_scene_config(PROJECT_ROOT / "scenes" / "001_grandma_porch_summer.yaml")
    path = write_thumbnail_workflow(
        scene_config=scene,
        uploaded_image_name="still.png",
        output_prefix="grandma_thumb",
        output_path=tmp_path / "thumbnail.json",
    )

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["workflow"]["1"]["inputs"]["image"] == "still.png"
