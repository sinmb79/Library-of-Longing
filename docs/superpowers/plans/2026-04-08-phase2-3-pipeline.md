# Phase 2-3 Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the remaining production pipeline by adding final assembly, thumbnail generation, YouTube upload automation, and an n8n orchestration workflow on top of the existing Phase 1 foundation.

**Architecture:** Keep every new unit scene-config driven and independently runnable from the command line. `assemble_final.py` will merge video and audio while writing YouTube-ready metadata; `thumbnail_gen.py` will handle scene variation requests plus final overlay rendering; `youtube_upload.py` will provide a safe dry-run-first uploader around OAuth and resumable uploads; `n8n/library_of_longing_pipeline.json` will orchestrate the full flow by invoking the scripts with clear handoff paths. Where live services are unavailable, verification will rely on deterministic dry-runs and focused unit/smoke tests.

**Tech Stack:** Python 3.12, argparse, subprocess, Pillow, requests, google-api-python-client/google-auth-oauthlib, FFmpeg 8.1, pytest, n8n JSON workflow definitions

---

## File Structure

- Create: `C:\Users\sinmb\workspace\Library-of-Londing\scripts\assemble_final.py`
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\scripts\thumbnail_gen.py`
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\scripts\youtube_upload.py`
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\n8n\library_of_longing_pipeline.json`
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\tests\test_assemble_final.py`
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\tests\test_thumbnail_gen.py`
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\tests\test_youtube_upload.py`
- Modify: `C:\Users\sinmb\workspace\Library-of-Londing\scenes\schema.yaml`
- Modify: `C:\Users\sinmb\workspace\Library-of-Londing\scenes\001_grandma_porch_summer.yaml`
- Modify: `C:\Users\sinmb\workspace\Library-of-Londing\README.md`

### Task 1: C4 Final Assembly

**Files:**
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\tests\test_assemble_final.py`
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\scripts\assemble_final.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_build_youtube_metadata_from_scene() -> None:
    scene = load_scene_config(PROJECT_ROOT / "scenes" / "001_grandma_porch_summer.yaml")
    metadata = build_youtube_metadata(scene, thumbnail_path=Path("thumb.jpg"))
    assert metadata["title"] == scene["metadata"]["title"]["ko"]
    assert "Grandmother's Porch" in metadata["description"]

def test_assemble_final_creates_muxed_output(tmp_path: Path) -> None:
    out = assemble_final(video_path=video, audio_path=audio, scene_config=scene, output_path=tmp_path / "final.mp4")
    assert out.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_assemble_final.py -v`
Expected: FAIL because `assemble_final.py` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def build_youtube_metadata(...):
    return {...}

def assemble_final(...):
    subprocess.run([...])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_assemble_final.py -v`
Expected: PASS

### Task 2: C5 Thumbnail Generator

**Files:**
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\tests\test_thumbnail_gen.py`
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\scripts\thumbnail_gen.py`
- Create/Modify: `C:\Users\sinmb\workspace\Library-of-Londing\workflows\thumbnail.json`

- [ ] **Step 1: Write the failing tests**

```python
def test_build_thumbnail_workflow_references_input_image() -> None:
    workflow = build_thumbnail_workflow(...)
    assert workflow["1"]["inputs"]["image"] == "still.png"

def test_render_thumbnail_writes_1280x720_jpg(tmp_path: Path) -> None:
    out = render_thumbnail(...)
    assert out.suffix == ".jpg"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_thumbnail_gen.py -v`
Expected: FAIL because `thumbnail_gen.py` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def build_thumbnail_workflow(...):
    return {...}

def render_thumbnail(...):
    image.save(...)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_thumbnail_gen.py -v`
Expected: PASS

### Task 3: C6 YouTube Upload

**Files:**
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\tests\test_youtube_upload.py`
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\scripts\youtube_upload.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_build_upload_request_uses_metadata_defaults() -> None:
    request = build_upload_request(...)
    assert request["snippet"]["defaultLanguage"] == "ko"

def test_dry_run_returns_predicted_payload(tmp_path: Path) -> None:
    result = dry_run_upload(...)
    assert result["status"] == "dry_run"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_youtube_upload.py -v`
Expected: FAIL because `youtube_upload.py` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def build_upload_request(...):
    return {...}

def upload_video(..., dry_run=True):
    return {...}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_youtube_upload.py -v`
Expected: PASS

### Task 4: Scene Schema Extension + C7 n8n Workflow

**Files:**
- Modify: `C:\Users\sinmb\workspace\Library-of-Londing\scenes\schema.yaml`
- Modify: `C:\Users\sinmb\workspace\Library-of-Londing\scenes\001_grandma_porch_summer.yaml`
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\n8n\library_of_longing_pipeline.json`

- [ ] **Step 1: Write the failing tests**

```python
def test_scene_config_accepts_optional_timelapse_segments() -> None:
    config = load_scene_config(scene_path)
    assert config["video"]["time_lapse_segments"][0]["label"] == "dawn"

def test_n8n_workflow_contains_phase_order() -> None:
    workflow = json.loads(Path(...).read_text())
    assert "Call C2" in ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scene_config.py tests/test_thumbnail_gen.py -v`
Expected: FAIL because the schema and workflow additions do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```yaml
video:
  time_lapse_segments:
    - source: ...
      label: ...
```

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_scene_config.py tests/test_thumbnail_gen.py tests/test_assemble_final.py tests/test_youtube_upload.py -v`
Expected: PASS

### Task 5: Full Verification + Docs

**Files:**
- Modify: `C:\Users\sinmb\workspace\Library-of-Londing\README.md`

- [ ] **Step 1: Run the full suite**

Run: `pytest tests -v`
Expected: PASS

- [ ] **Step 2: Run smoke commands**

Run:

```powershell
python scripts/assemble_final.py --help
python scripts/thumbnail_gen.py --help
python scripts/youtube_upload.py --help
```

Expected: Each CLI prints help and exits cleanly.

- [ ] **Step 3: Update README**

Add Phase 2/3 coverage and note any live-service verification gaps.

- [ ] **Step 4: Commit and push**

```bash
git add .
git commit -m "feat: complete production pipeline"
git push origin main
```
