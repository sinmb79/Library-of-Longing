from __future__ import annotations

from pathlib import Path

import json

from scripts.comfyui_queue import (
    GeneratedArtifact,
    build_image_workflow,
    build_video_workflow,
    extract_output_files,
    run_scene_generation,
)
from scripts.scene_config import load_scene_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_build_image_workflow_applies_style_lora() -> None:
    scene = load_scene_config(PROJECT_ROOT / "scenes" / "001_grandma_porch_summer.yaml")

    workflow = build_image_workflow(scene, seed=123, output_prefix="demo_scene")

    assert workflow["2"]["class_type"] == "LoraLoader"
    assert workflow["2"]["inputs"]["lora_name"] == "ghibli_style_sdxl.safetensors"
    assert "Studio Ghibli style" in workflow["3"]["inputs"]["text"]
    assert workflow["5"]["inputs"]["width"] == 3840
    assert workflow["8"]["inputs"]["filename_prefix"] == "demo_scene_still"


def test_build_video_workflow_uses_uploaded_image_and_wan_nodes() -> None:
    scene = load_scene_config(PROJECT_ROOT / "scenes" / "001_grandma_porch_summer.yaml")

    workflow = build_video_workflow(scene, uploaded_image_name="uploaded_scene.png", seed=321, output_prefix="demo_scene")

    assert workflow["1"]["class_type"] == "LoadImage"
    assert workflow["1"]["inputs"]["image"] == "uploaded_scene.png"
    assert workflow["2"]["inputs"]["model"] == r"a2v\SkyReels-v3-a2v-Q4_K_M.gguf"
    assert workflow["8"]["class_type"] == "WanVideoImageToVideoEncode"
    assert workflow["8"]["inputs"]["start_image"] == ["1", 0]
    assert workflow["8"]["inputs"]["end_image"] == ["1", 0]
    assert workflow["8"]["inputs"]["width"] == 848
    assert workflow["8"]["inputs"]["height"] == 480
    assert workflow["11"]["class_type"] == "VHS_VideoCombine"
    assert workflow["11"]["inputs"]["filename_prefix"] == "demo_scene_loop"


def test_extract_output_files_reads_images_and_videos() -> None:
    prompt_id = "prompt-123"
    history = {
        prompt_id: {
            "outputs": {
                "8": {
                    "images": [
                        {"filename": "still.png", "subfolder": "", "type": "output"},
                    ]
                },
                "11": {
                    "gifs": [
                        {"filename": "loop.mp4", "subfolder": "", "type": "output", "format": "video/h264-mp4"},
                    ]
                },
            }
        }
    }

    files = extract_output_files(history, prompt_id)

    assert files == [
        GeneratedArtifact(filename="still.png", subfolder="", folder_type="output", kind="image"),
        GeneratedArtifact(filename="loop.mp4", subfolder="", folder_type="output", kind="video"),
    ]


def test_run_scene_generation_uploads_stage1_image_before_video(tmp_path: Path) -> None:
    scene_path = PROJECT_ROOT / "scenes" / "001_grandma_porch_summer.yaml"
    stage1_history = {
        "prompt-image": {
            "outputs": {
                "8": {"images": [{"filename": "still.png", "subfolder": "", "type": "output"}]}
            }
        }
    }
    stage2_history = {
        "prompt-video": {
            "outputs": {
                "11": {"gifs": [{"filename": "loop.mp4", "subfolder": "", "type": "output", "format": "video/h264-mp4"}]}
            }
        }
    }

    class FakeClient:
        def __init__(self) -> None:
            self.queued: list[dict] = []
            self.uploaded: list[Path] = []
            self.downloaded: list[tuple[str, Path]] = []

        def queue_prompt(self, workflow: dict, client_id: str) -> str:
            self.queued.append(workflow)
            return "prompt-image" if len(self.queued) == 1 else "prompt-video"

        def wait_for_history(self, prompt_id: str, timeout_sec: int, poll_interval: float) -> dict:
            return stage1_history if prompt_id == "prompt-image" else stage2_history

        def download_output(self, artifact: GeneratedArtifact, destination: Path) -> Path:
            self.downloaded.append((artifact.filename, destination))
            destination.parent.mkdir(parents=True, exist_ok=True)
            if artifact.kind == "image":
                destination.write_bytes(b"png-data")
            else:
                destination.write_bytes(b"mp4-data")
            return destination

        def upload_image(self, image_path: Path, overwrite: bool = True) -> str:
            self.uploaded.append(image_path)
            return "uploaded_scene.png"

    fake_client = FakeClient()
    result = run_scene_generation(scene_path, output_dir=tmp_path, client=fake_client, timeout_sec=5)

    assert result["image"].suffix == ".png"
    assert result["video"].suffix == ".mp4"
    assert fake_client.uploaded == [result["image"]]
    assert fake_client.queued[0]["8"]["inputs"]["filename_prefix"].endswith("_still")
    assert fake_client.queued[1]["1"]["inputs"]["image"] == "uploaded_scene.png"


def test_rendered_template_bundle_is_json_serializable() -> None:
    scene = load_scene_config(PROJECT_ROOT / "scenes" / "001_grandma_porch_summer.yaml")
    bundle = {
        "image_workflow": build_image_workflow(scene, seed=111, output_prefix="bundle_scene"),
        "video_workflow": build_video_workflow(scene, uploaded_image_name="bundle.png", seed=222, output_prefix="bundle_scene"),
    }

    encoded = json.dumps(bundle, ensure_ascii=False)

    assert "image_workflow" in encoded
    assert "video_workflow" in encoded
