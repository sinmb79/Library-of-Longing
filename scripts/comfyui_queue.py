from __future__ import annotations

import argparse
import json
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

try:
    from scripts.scene_config import load_scene_config
except ImportError:
    from scene_config import load_scene_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMFYUI_URL = "http://localhost:8188"
DEFAULT_CLIENT_ID = "library_of_longing"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output" / "video"
DEFAULT_TEMPLATE_PATH = PROJECT_ROOT / "workflows" / "ambient_scene.json"
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_TIMEOUT_SEC = 1800
DEFAULT_LOOP_GENERATION_RESOLUTION = (1280, 720)
DEFAULT_UPSCALE_MODEL = "4x-UltraSharp"
VRAM_PIXEL_BUDGET = 300_000_000
FALLBACK_LOOP_RESOLUTION = (912, 512)

STYLE_PRESETS = {
    "ghibli": {
        "lora_name": "ghibli_style_sdxl.safetensors",
        "trigger": "Studio Ghibli style",
        "strength_model": 0.85,
        "strength_clip": 0.85,
    },
    "watercolor": {
        "lora_name": "watercolor_sdxl.safetensors",
        "trigger": "",
        "strength_model": 0.8,
        "strength_clip": 0.8,
    },
    "oil": {
        "lora_name": "oil_painting_sdxl.safetensors",
        "trigger": "oil painting",
        "strength_model": 0.8,
        "strength_clip": 0.8,
    },
}
logger = logging.getLogger(__name__)


@dataclass(eq=True, frozen=True)
class GeneratedArtifact:
    filename: str
    subfolder: str
    folder_type: str
    kind: str


class ComfyUIClient:
    def __init__(self, base_url: str = DEFAULT_COMFYUI_URL, session: requests.Session | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()

    def queue_prompt(self, workflow: dict[str, Any], client_id: str = DEFAULT_CLIENT_ID) -> str:
        try:
            response = self.session.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow, "client_id": client_id},
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            return payload["prompt_id"]
        except requests.RequestException as exc:
            raise RuntimeError(f"Could not reach ComfyUI at {self.base_url}. Start ComfyUI before queueing prompts.") from exc

    def wait_for_history(
        self,
        prompt_id: str,
        *,
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> dict[str, Any]:
        started = time.time()
        while time.time() - started < timeout_sec:
            try:
                response = self.session.get(f"{self.base_url}/history/{prompt_id}", timeout=30)
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException as exc:
                raise RuntimeError(f"Could not query ComfyUI history for prompt {prompt_id}.") from exc
            if payload and prompt_id in payload and payload[prompt_id].get("outputs"):
                return payload
            time.sleep(poll_interval)
        raise TimeoutError(f"Timed out waiting for ComfyUI prompt {prompt_id}.")

    def upload_image(self, image_path: Path, overwrite: bool = True) -> str:
        try:
            with image_path.open("rb") as handle:
                response = self.session.post(
                    f"{self.base_url}/upload/image",
                    files={"image": (image_path.name, handle, "image/png")},
                    data={"type": "input", "overwrite": str(overwrite).lower()},
                    timeout=120,
                )
            response.raise_for_status()
            payload = response.json()
            return payload.get("name") or payload.get("filename") or image_path.name
        except requests.RequestException as exc:
            raise RuntimeError(f"Could not upload {image_path.name} to ComfyUI input.") from exc

    def download_output(self, artifact: GeneratedArtifact, destination: Path) -> Path:
        try:
            response = self.session.get(
                f"{self.base_url}/view",
                params={
                    "filename": artifact.filename,
                    "subfolder": artifact.subfolder,
                    "type": artifact.folder_type,
                },
                timeout=120,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Could not download {artifact.filename} from ComfyUI output.") from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
        return destination


def _compose_still_prompt(scene_config: dict[str, Any]) -> str:
    preset = STYLE_PRESETS[scene_config["visual"]["style"]]
    trigger = preset["trigger"].strip()
    prompt = scene_config["visual"]["prompt"].strip()
    if trigger and trigger.lower() not in prompt.lower():
        return f"{trigger}, {prompt}"
    return prompt


def _compose_motion_prompt(scene_config: dict[str, Any]) -> str:
    still = scene_config["visual"]["prompt"].strip()
    motion = scene_config["visual"]["motion_prompt"].strip()
    return f"{still}. Motion guidance: {motion}"


def _video_negative_prompt(scene_config: dict[str, Any]) -> str:
    return (
        f"{scene_config['visual']['negative_prompt'].strip()}, static frame, flicker, jitter, "
        "warped anatomy, broken motion, text, watermark"
    )


def _snap_down(value: float, multiple: int = 16) -> int:
    snapped = int(value) // multiple * multiple
    return max(64, snapped)


def _fit_resolution(resolution: list[int], *, max_width: int, max_height: int) -> tuple[int, int]:
    width, height = int(resolution[0]), int(resolution[1])
    aspect = width / height
    candidates: list[tuple[int, int]] = []

    width_candidate = (_snap_down(min(max_width, width)), _snap_down(min(max_width, width) / aspect))
    if width_candidate[0] <= max_width and width_candidate[1] <= max_height:
        candidates.append(width_candidate)

    height_candidate = (_snap_down(min(max_height, height) * aspect), _snap_down(min(max_height, height)))
    if height_candidate[0] <= max_width and height_candidate[1] <= max_height:
        candidates.append(height_candidate)

    if not candidates:
        return max(64, _snap_down(max_width)), max(64, _snap_down(max_height))
    return max(candidates, key=lambda item: item[0] * item[1])


def derive_video_resolution(
    resolution: list[int],
    max_width: int = DEFAULT_LOOP_GENERATION_RESOLUTION[0],
    max_height: int = DEFAULT_LOOP_GENERATION_RESOLUTION[1],
    *,
    num_frames: int | None = None,
    vram_pixel_budget: int = VRAM_PIXEL_BUDGET,
    fallback_width: int = FALLBACK_LOOP_RESOLUTION[0],
    fallback_height: int = FALLBACK_LOOP_RESOLUTION[1],
) -> tuple[int, int]:
    target_width, target_height = _fit_resolution(resolution, max_width=max_width, max_height=max_height)
    if num_frames is not None and target_width * target_height * num_frames > vram_pixel_budget:
        fallback = _fit_resolution(resolution, max_width=fallback_width, max_height=fallback_height)
        logger.warning(
            "Wan loop resolution %sx%s exceeds VRAM budget for %s frames; falling back to %sx%s.",
            target_width,
            target_height,
            num_frames,
            fallback[0],
            fallback[1],
        )
        return fallback
    return target_width, target_height


def _blocks_to_swap_for_resolution(height: int) -> int:
    if height >= 960:
        return 30
    if height >= 720:
        return 28
    if height >= 640:
        return 25
    return 20


def _loop_generation_target(scene_config: dict[str, Any]) -> tuple[int, int]:
    target = scene_config["visual"].get("loop_generation_resolution")
    if target:
        return int(target[0]), int(target[1])
    return DEFAULT_LOOP_GENERATION_RESOLUTION


def _upscale_model_filename(scene_config: dict[str, Any]) -> str | None:
    name = str(scene_config["visual"].get("upscale_model") or DEFAULT_UPSCALE_MODEL).strip()
    if not name or name == "none":
        return None
    if name.lower().endswith(".pth"):
        return name
    return f"{name}.pth"


def _loop_frame_count(loop_duration_sec: int, frame_rate: int = 16) -> int:
    return max(1, int(math.ceil((loop_duration_sec * frame_rate + 1) / 4.0) * 4))


def build_image_workflow(scene_config: dict[str, Any], *, seed: int, output_prefix: str) -> dict[str, dict[str, Any]]:
    preset = STYLE_PRESETS[scene_config["visual"]["style"]]
    width, height = scene_config["visual"]["resolution"]
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {
                "ckpt_name": "sd_xl_base_1.0.safetensors",
            },
        },
        "2": {
            "class_type": "LoraLoader",
            "inputs": {
                "model": ["1", 0],
                "clip": ["1", 1],
                "lora_name": preset["lora_name"],
                "strength_model": preset["strength_model"],
                "strength_clip": preset["strength_clip"],
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["2", 1],
                "text": _compose_still_prompt(scene_config),
            },
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["2", 1],
                "text": scene_config["visual"]["negative_prompt"].strip(),
            },
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": width,
                "height": height,
                "batch_size": 1,
            },
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["2", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["5", 0],
                "seed": seed,
                "steps": 30,
                "cfg": 7.0,
                "sampler_name": "dpmpp_2m_sde",
                "scheduler": "karras",
                "denoise": 1.0,
            },
        },
        "7": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["6", 0],
                "vae": ["1", 2],
            },
        },
        "8": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["7", 0],
                "filename_prefix": f"{output_prefix}_still",
            },
        },
    }


def build_video_workflow(
    scene_config: dict[str, Any],
    *,
    uploaded_image_name: str,
    seed: int,
    output_prefix: str,
) -> dict[str, dict[str, Any]]:
    num_frames = _loop_frame_count(scene_config["visual"]["loop_duration_sec"])
    max_width, max_height = _loop_generation_target(scene_config)
    width, height = derive_video_resolution(
        scene_config["visual"]["resolution"],
        max_width=max_width,
        max_height=max_height,
        num_frames=num_frames,
    )
    blocks_to_swap = _blocks_to_swap_for_resolution(height)
    upscale_model_name = _upscale_model_filename(scene_config)
    video_input_node = ["12", 0]
    workflow: dict[str, dict[str, Any]] = {
        "1": {
            "class_type": "LoadImage",
            "inputs": {
                "image": uploaded_image_name,
            },
        },
        "2": {
            "class_type": "WanVideoModelLoader",
            "inputs": {
                "model": r"a2v\SkyReels-v3-a2v-Q4_K_M.gguf",
                "base_precision": "fp16",
                "quantization": "disabled",
                "load_device": "offload_device",
                "attention_mode": "sdpa",
                "block_swap_args": ["6", 0],
            },
        },
        "3": {
            "class_type": "LoadWanVideoT5TextEncoder",
            "inputs": {
                "model_name": r"split_files\text_encoders\umt5_xxl_fp16.safetensors",
                "precision": "bf16",
                "load_device": "offload_device",
            },
        },
        "4": {
            "class_type": "WanVideoVAELoader",
            "inputs": {
                "model_name": r"split_files\vae\wan_2.1_vae.safetensors",
                "precision": "bf16",
            },
        },
        "5": {
            "class_type": "WanVideoTextEncode",
            "inputs": {
                "t5": ["3", 0],
                "positive_prompt": _compose_motion_prompt(scene_config),
                "negative_prompt": _video_negative_prompt(scene_config),
                "force_offload": True,
                "device": "gpu",
            },
        },
        "6": {
            "class_type": "WanVideoBlockSwap",
            "inputs": {
                "blocks_to_swap": blocks_to_swap,
                "offload_txt_emb": False,
                "offload_img_emb": False,
            },
        },
        "7": {
            "class_type": "WanVideoSetAttentionModeOverride",
            "inputs": {
                "model": ["2", 0],
                "attention_mode": "sageattn",
                "start_step": 0,
                "end_step": 10000,
                "verbose": False,
            },
        },
        "8": {
            "class_type": "WanVideoImageToVideoEncode",
            "inputs": {
                "width": width,
                "height": height,
                "num_frames": num_frames,
                "noise_aug_strength": 0.02,
                "start_latent_strength": 1.0,
                "end_latent_strength": 1.0,
                "force_offload": True,
                "vae": ["4", 0],
                "start_image": ["1", 0],
                "end_image": ["1", 0],
                "fun_or_fl2v_model": True,
                "tiled_vae": False,
            },
        },
        "9": {
            "class_type": "WanVideoTeaCache",
            "inputs": {
                "rel_l1_thresh": 0.25,
                "start_step": 1,
                "end_step": -1,
                "cache_device": "offload_device",
                "use_coefficients": True,
            },
        },
        "10": {
            "class_type": "WanVideoSampler",
            "inputs": {
                "model": ["7", 0],
                "text_embeds": ["5", 0],
                "image_embeds": ["8", 0],
                "cache_args": ["9", 0],
                "steps": 20,
                "cfg": 6.0,
                "shift": 5,
                "seed": seed,
                "force_offload": True,
                "scheduler": "dpm++_sde",
                "riflex_freq_index": 0,
                "denoise_strength": 1.0,
                "batched_cfg": False,
            },
        },
        "11": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": video_input_node,
                "frame_rate": 16,
                "loop_count": 0,
                "filename_prefix": f"{output_prefix}_loop",
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": 18,
                "save_metadata": True,
                "trim_to_audio": False,
                "pingpong": False,
                "save_output": True,
            },
        },
        "12": {
            "class_type": "WanVideoDecode",
            "inputs": {
                "vae": ["4", 0],
                "samples": ["10", 0],
                "enable_vae_tiling": False,
                "tile_x": 272,
                "tile_y": 272,
                "tile_stride_x": 144,
                "tile_stride_y": 128,
            },
        },
    }
    if upscale_model_name:
        workflow["13"] = {
            "class_type": "UpscaleModelLoader",
            "inputs": {
                "model_name": upscale_model_name,
            },
        }
        workflow["14"] = {
            "class_type": "ImageUpscaleWithModel",
            "inputs": {
                "upscale_model": ["13", 0],
                "image": ["12", 0],
            },
        }
        workflow["11"]["inputs"]["images"] = ["14", 0]
    return workflow


def extract_output_files(history: dict[str, Any], prompt_id: str) -> list[GeneratedArtifact]:
    payload = history.get(prompt_id, {})
    outputs = payload.get("outputs", {})
    artifacts: list[GeneratedArtifact] = []
    for node_id in sorted(outputs.keys(), key=lambda value: int(value) if str(value).isdigit() else str(value)):
        node_output = outputs[node_id]
        for key, kind in (("images", "image"), ("gifs", "video"), ("videos", "video")):
            for item in node_output.get(key, []):
                filename = item["filename"]
                resolved_kind = kind
                if filename.lower().endswith((".gif", ".webp")):
                    resolved_kind = "image"
                artifacts.append(
                    GeneratedArtifact(
                        filename=filename,
                        subfolder=item.get("subfolder", ""),
                        folder_type=item.get("type", "output"),
                        kind=resolved_kind,
                    )
                )
    return artifacts


def _select_first_artifact(artifacts: list[GeneratedArtifact], *, kind: str) -> GeneratedArtifact:
    for artifact in artifacts:
        if artifact.kind == kind:
            return artifact
    raise FileNotFoundError(f"No {kind} artifact found in ComfyUI history.")


def render_workflow_bundle(scene_path: Path, *, image_seed: int, video_seed: int) -> dict[str, Any]:
    scene = load_scene_config(scene_path)
    base_prefix = f"{scene['scene']['id']}_{scene['scene']['slug']}"
    return {
        "scene_path": scene_path.resolve().as_posix(),
        "scene_id": scene["scene"]["id"],
        "scene_slug": scene["scene"]["slug"],
        "image_seed": image_seed,
        "video_seed": video_seed,
        "image_workflow": build_image_workflow(scene, seed=image_seed, output_prefix=base_prefix),
        "video_workflow": build_video_workflow(
            scene,
            uploaded_image_name="__UPLOADED_IMAGE__",
            seed=video_seed,
            output_prefix=base_prefix,
        ),
    }


def write_workflow_bundle(scene_path: Path, destination: Path, *, image_seed: int, video_seed: int) -> Path:
    bundle = render_workflow_bundle(scene_path, image_seed=image_seed, video_seed=video_seed)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


def run_scene_generation(
    scene_path: Path,
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    client: ComfyUIClient | Any | None = None,
    client_id: str = DEFAULT_CLIENT_ID,
    image_seed: int = 101,
    video_seed: int = 202,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
) -> dict[str, Path]:
    scene = load_scene_config(scene_path)
    base_prefix = f"{scene['scene']['id']}_{scene['scene']['slug']}"
    active_client = client or ComfyUIClient()

    image_workflow = build_image_workflow(scene, seed=image_seed, output_prefix=base_prefix)
    image_prompt_id = active_client.queue_prompt(image_workflow, client_id=client_id)
    image_history = active_client.wait_for_history(image_prompt_id, timeout_sec=timeout_sec, poll_interval=poll_interval)
    image_artifact = _select_first_artifact(extract_output_files(image_history, image_prompt_id), kind="image")
    image_destination = output_dir / "image" / image_artifact.filename
    local_image = active_client.download_output(image_artifact, image_destination)

    uploaded_name = active_client.upload_image(local_image)

    video_workflow = build_video_workflow(
        scene,
        uploaded_image_name=uploaded_name,
        seed=video_seed,
        output_prefix=base_prefix,
    )
    video_prompt_id = active_client.queue_prompt(video_workflow, client_id=client_id)
    video_history = active_client.wait_for_history(video_prompt_id, timeout_sec=timeout_sec, poll_interval=poll_interval)
    video_artifact = _select_first_artifact(extract_output_files(video_history, video_prompt_id), kind="video")
    video_destination = output_dir / "loop" / video_artifact.filename
    local_video = active_client.download_output(video_artifact, video_destination)

    return {
        "image": local_image,
        "video": local_video,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Queue Library of Longing scene generation jobs to ComfyUI.")
    parser.add_argument("--scene", type=Path, required=True, help="Path to the scene YAML file.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Download directory for generated assets.")
    parser.add_argument("--write-template", type=Path, default=None, help="Write a workflow bundle JSON to this path.")
    parser.add_argument("--image-seed", type=int, default=101, help="Seed for the SDXL still image.")
    parser.add_argument("--video-seed", type=int, default=202, help="Seed for the Wan loop generation.")
    parser.add_argument("--client-id", type=str, default=DEFAULT_CLIENT_ID, help="ComfyUI client id.")
    parser.add_argument("--timeout-sec", type=int, default=DEFAULT_TIMEOUT_SEC, help="Maximum wait time per ComfyUI stage.")
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL, help="Polling interval for ComfyUI history.")
    parser.add_argument("--dry-run", action="store_true", help="Only render and optionally save the workflow bundle.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    template_path = args.write_template
    if template_path is not None:
        write_workflow_bundle(args.scene, template_path, image_seed=args.image_seed, video_seed=args.video_seed)
        print(template_path)
    if args.dry_run:
        return
    result = run_scene_generation(
        args.scene,
        output_dir=args.output_dir,
        client_id=args.client_id,
        image_seed=args.image_seed,
        video_seed=args.video_seed,
        timeout_sec=args.timeout_sec,
        poll_interval=args.poll_interval,
    )
    print(json.dumps({key: value.as_posix() for key, value in result.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
