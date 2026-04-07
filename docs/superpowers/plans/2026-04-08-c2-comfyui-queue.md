# C2 ComfyUI Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the ComfyUI queue client and workflow bundle that turns a scene YAML into a generated PNG plus loop MP4.

**Architecture:** Keep stage boundaries explicit. `scripts/comfyui_queue.py` will load a normalized scene config, build two workflow payloads (SDXL still image, then Wan I2V loop), drive ComfyUI over HTTP, and download resulting artifacts. `workflows/ambient_scene.json` will store a generated workflow bundle for the first scene so the repo has a concrete template and reference output.

**Tech Stack:** Python 3.12, requests, pytest, PyYAML, ComfyUI HTTP API

---

### Task 1: Workflow Builders

**Files:**
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\tests\test_comfyui_queue.py`
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\scripts\comfyui_queue.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_build_image_workflow_applies_style_lora():
    workflow = build_image_workflow(scene, seed=123, output_prefix="demo")
    assert workflow["2"]["inputs"]["lora_name"] == "ghibli_style_sdxl.safetensors"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_comfyui_queue.py -v`
Expected: FAIL because `scripts.comfyui_queue` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def build_image_workflow(scene_config: dict, seed: int, output_prefix: str) -> dict[str, dict]:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_comfyui_queue.py::test_build_image_workflow_applies_style_lora -v`
Expected: PASS

---

### Task 2: Queue Client And Artifact Parsing

**Files:**
- Modify: `C:\Users\sinmb\workspace\Library-of-Londing\scripts\comfyui_queue.py`
- Test: `C:\Users\sinmb\workspace\Library-of-Londing\tests\test_comfyui_queue.py`

- [ ] **Step 1: Write the failing integration-style test**

```python
def test_run_scene_generation_uploads_stage1_image_before_video():
    result = run_scene_generation(scene_path, output_dir=tmp_path, client=fake_client)
    assert result["video"].suffix == ".mp4"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_comfyui_queue.py::test_run_scene_generation_uploads_stage1_image_before_video -v`
Expected: FAIL because the queue orchestration is not implemented yet.

- [ ] **Step 3: Write minimal implementation**

```python
def run_scene_generation(scene_path: Path, output_dir: Path, client: ComfyUIClient, ...):
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_comfyui_queue.py::test_run_scene_generation_uploads_stage1_image_before_video -v`
Expected: PASS

---

### Task 3: Workflow Bundle And Verification

**Files:**
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\workflows\ambient_scene.json`
- Modify: `C:\Users\sinmb\workspace\Library-of-Londing\scripts\comfyui_queue.py`
- Test: `C:\Users\sinmb\workspace\Library-of-Londing\tests\test_comfyui_queue.py`

- [ ] **Step 1: Run the focused test suite**

Run: `pytest tests/test_comfyui_queue.py -v`
Expected: PASS

- [ ] **Step 2: Write the concrete workflow bundle**

Run: `python scripts/comfyui_queue.py --scene scenes/001_grandma_porch_summer.yaml --write-template workflows/ambient_scene.json --dry-run`
Expected: `workflows/ambient_scene.json` written with image and video workflows.

- [ ] **Step 3: Verify the generated JSON**

Run: `python -c "import json, pathlib; data=json.loads(pathlib.Path(r'workflows/ambient_scene.json').read_text(encoding='utf-8')); print(sorted(data.keys()))"`
Expected: includes `image_workflow` and `video_workflow`
