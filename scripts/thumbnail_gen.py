from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

try:
    from scripts.comfyui_queue import STYLE_PRESETS
    from scripts.scene_config import load_scene_config
except ImportError:
    from comfyui_queue import STYLE_PRESETS
    from scene_config import load_scene_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE_PATH = PROJECT_ROOT / "workflows" / "thumbnail.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "thumbnails"
THUMBNAIL_WIDTH = 1280
THUMBNAIL_HEIGHT = 720


def build_thumbnail_workflow(
    *,
    scene_config: dict[str, Any],
    uploaded_image_name: str,
    output_prefix: str,
) -> dict[str, dict[str, Any]]:
    preset = STYLE_PRESETS[scene_config["visual"]["style"]]
    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": uploaded_image_name},
        },
        "2": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
        },
        "3": {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["2", 0],
                "clip": ["2", 1],
                "lora_name": preset["lora_name"],
                "strength_model": 0.55,
                "strength_clip": 0.55,
            },
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["3", 1],
                "text": f"thumbnail variant, {scene_config['visual']['prompt'].strip()}",
            },
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["3", 1],
                "text": "text, watermark, logo, bad composition, oversaturated colors",
            },
        },
        "6": {
            "class_type": "VAEEncode",
            "inputs": {
                "pixels": ["1", 0],
                "vae": ["2", 2],
            },
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["3", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["6", 0],
                "seed": 777,
                "steps": 18,
                "cfg": 6.0,
                "sampler_name": "dpmpp_2m_sde",
                "scheduler": "karras",
                "denoise": 0.28,
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["7", 0],
                "vae": ["2", 2],
            },
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["8", 0],
                "filename_prefix": f"{output_prefix}_variant",
            },
        },
    }


def write_thumbnail_workflow(
    *,
    scene_config: dict[str, Any],
    uploaded_image_name: str,
    output_prefix: str,
    output_path: Path = DEFAULT_TEMPLATE_PATH,
) -> Path:
    payload = {
        "scene": scene_config["scene"]["slug"],
        "workflow": build_thumbnail_workflow(
            scene_config=scene_config,
            uploaded_image_name=uploaded_image_name,
            output_prefix=output_prefix,
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _find_font(candidates: list[Path], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _english_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return _find_font([PROJECT_ROOT / "fonts" / "BebasNeue-Regular.ttf"], size=size)


def _korean_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path(r"C:\Windows\Fonts\malgunbd.ttf"),
        Path(r"C:\Windows\Fonts\malgun.ttf"),
        Path(r"C:\Windows\Fonts\NanumGothicBold.ttf"),
        Path(r"C:\Windows\Fonts\NanumGothic.ttf"),
    ]
    return _find_font(candidates, size=size)


def _fit_cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    src_w, src_h = image.size
    scale = max(target_w / src_w, target_h / src_h)
    resized = image.resize((int(src_w * scale), int(src_h * scale)), Image.Resampling.LANCZOS)
    left = max(0, (resized.width - target_w) // 2)
    top = max(0, (resized.height - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))


def _draw_gradient_bar(canvas: Image.Image, height: int = 220) -> None:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    start_y = canvas.height - height
    for index in range(height):
        alpha = int(190 * ((index + 1) / height))
        y = start_y + index
        draw.line((0, y, canvas.width, y), fill=(16, 12, 10, alpha))
    canvas.alpha_composite(overlay)


def _draw_text_block(draw: ImageDraw.ImageDraw, text: str, position: tuple[int, int], font, fill: tuple[int, int, int]) -> None:
    x, y = position
    draw.text((x + 3, y + 3), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=fill)


def render_thumbnail(
    *,
    scene_config: dict[str, Any],
    base_image_path: Path,
    output_path: Path,
    duration_label_ko: str = "10시간",
    duration_label_en: str = "10 Hours",
) -> Path:
    image = Image.open(base_image_path).convert("RGB")
    image = _fit_cover(image, (THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT))
    image = ImageEnhance.Color(image).enhance(1.08)
    image = ImageEnhance.Contrast(image).enhance(1.05)
    image = image.filter(ImageFilter.GaussianBlur(radius=0.4))
    canvas = image.convert("RGBA")
    _draw_gradient_bar(canvas)

    draw = ImageDraw.Draw(canvas)
    metadata = scene_config["metadata"]
    ko_font = _korean_font(50)
    en_font = _english_font(44)
    duration_font = _english_font(40)

    left_x = 54
    ko_y = THUMBNAIL_HEIGHT - 172
    en_y = THUMBNAIL_HEIGHT - 108
    _draw_text_block(draw, metadata["title"]["ko"], (left_x, ko_y), ko_font, (255, 245, 232))
    _draw_text_block(draw, metadata["title"]["en"], (left_x, en_y), en_font, (255, 220, 170))

    duration_text = f"{duration_label_ko} | {duration_label_en}"
    duration_box = draw.textbbox((0, 0), duration_text, font=duration_font)
    duration_x = THUMBNAIL_WIDTH - (duration_box[2] - duration_box[0]) - 54
    duration_y = THUMBNAIL_HEIGHT - 92
    _draw_text_block(draw, duration_text, (duration_x, duration_y), duration_font, (255, 245, 232))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, quality=95)
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a YouTube thumbnail and/or write a ComfyUI variation workflow.")
    parser.add_argument("--scene", type=Path, required=True, help="Path to the scene YAML file.")
    parser.add_argument("--base-image", type=Path, required=True, help="Base image used for local thumbnail rendering.")
    parser.add_argument("--output", type=Path, default=None, help="Output JPG path.")
    parser.add_argument("--write-template", type=Path, default=None, help="Write the thumbnail workflow JSON to this path.")
    parser.add_argument(
        "--uploaded-image-name",
        type=str,
        default=None,
        help="Image filename as it exists inside ComfyUI input/output for workflow templating.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    scene_config = load_scene_config(args.scene)
    output_path = args.output or (DEFAULT_OUTPUT_DIR / f"{scene_config['scene']['slug']}.jpg")
    result = {"thumbnail": render_thumbnail(scene_config=scene_config, base_image_path=args.base_image, output_path=output_path).as_posix()}

    if args.write_template is not None:
        uploaded_image_name = args.uploaded_image_name or args.base_image.name
        template_path = write_thumbnail_workflow(
            scene_config=scene_config,
            uploaded_image_name=uploaded_image_name,
            output_prefix=scene_config["scene"]["slug"],
            output_path=args.write_template,
        )
        result["workflow"] = template_path.as_posix()

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
