# C3 Video Compositor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `scripts/video_compositor.py` so a short ambient loop clip can be expanded into a 10-hour delivery video with FFmpeg-based post-processing, plus an optional time-lapse composition path.

**Architecture:** Keep the script scene-config driven for the default path: read `scenes/*.yaml`, derive output defaults from `video.*`, and generate deterministic FFmpeg commands. Implement two composition modes behind clear helpers: a basic loop compositor for one MP4 loop clip, and a time-lapse compositor that crossfades multiple visual sources. Verify behavior with test-first command assertions and one short FFmpeg smoke test.

**Tech Stack:** Python 3.12, argparse, subprocess, FFmpeg/ffprobe 8.1, pytest, existing `scripts.scene_config`

---

## File Structure

- Create: `C:\Users\sinmb\workspace\Library-of-Londing\scripts\video_compositor.py`
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\tests\test_video_compositor.py`
- Reuse: `C:\Users\sinmb\workspace\Library-of-Londing\scripts\scene_config.py`
- Reference only: `C:\Users\sinmb\workspace\scp-videos\produce_shorts_v2.py`
- Reference only: `C:\Users\sinmb\workspace\scp-videos\generate_long_videos.py`

### Task 1: Basic Loop Composition Command

**Files:**
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\tests\test_video_compositor.py`
- Create: `C:\Users\sinmb\workspace\Library-of-Londing\scripts\video_compositor.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_basic_command_uses_scene_defaults() -> None:
    scene = load_scene_config(PROJECT_ROOT / "scenes" / "001_grandma_porch_summer.yaml")
    cmd = build_basic_loop_command(
        loop_clip=Path("loop.mp4"),
        output_path=Path("output.mp4"),
        scene_config=scene,
    )
    assert "-stream_loop" in cmd
    assert "noise=alls=15:allf=t" in " ".join(cmd)
    assert "vignette" in " ".join(cmd)
    assert "libx264" in cmd
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_video_compositor.py::test_build_basic_command_uses_scene_defaults -v`
Expected: FAIL because `video_compositor.py` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def build_basic_loop_command(...):
    return [...]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_video_compositor.py::test_build_basic_command_uses_scene_defaults -v`
Expected: PASS

- [ ] **Step 5: Record progress**

Workspace note: no git root is present, so capture progress through the test result instead of a commit.

### Task 2: Time-Lapse Command Builder

**Files:**
- Modify: `C:\Users\sinmb\workspace\Library-of-Londing\tests\test_video_compositor.py`
- Modify: `C:\Users\sinmb\workspace\Library-of-Londing\scripts\video_compositor.py`

- [ ] **Step 1: Write the failing test**

```python
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
    assert "xfade" in joined
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_video_compositor.py::test_build_timelapse_command_creates_xfade_graph -v`
Expected: FAIL because `build_timelapse_command` is missing.

- [ ] **Step 3: Write minimal implementation**

```python
def build_timelapse_command(...):
    return [...]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_video_compositor.py::test_build_timelapse_command_creates_xfade_graph -v`
Expected: PASS

- [ ] **Step 5: Record progress**

Workspace note: no git root is present, so capture progress through the test result instead of a commit.

### Task 3: CLI and FFmpeg Smoke Path

**Files:**
- Modify: `C:\Users\sinmb\workspace\Library-of-Londing\tests\test_video_compositor.py`
- Modify: `C:\Users\sinmb\workspace\Library-of-Londing\scripts\video_compositor.py`

- [ ] **Step 1: Write the failing test**

```python
def test_compose_basic_video_writes_short_output(tmp_path: Path) -> None:
    clip = make_test_clip(tmp_path / "loop.mp4")
    scene = load_scene_config(PROJECT_ROOT / "scenes" / "001_grandma_porch_summer.yaml")
    out = compose_basic_video(
        loop_clip=clip,
        output_path=tmp_path / "composed.mp4",
        scene_config=scene,
        target_duration_sec=2,
    )
    assert out.exists()
    assert get_duration(out) >= 1.8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_video_compositor.py::test_compose_basic_video_writes_short_output -v`
Expected: FAIL because `compose_basic_video` is missing.

- [ ] **Step 3: Write minimal implementation**

```python
def compose_basic_video(...):
    subprocess.run(...)
    return output_path
```

- [ ] **Step 4: Run targeted tests to verify they pass**

Run: `pytest tests/test_video_compositor.py -v`
Expected: PASS

- [ ] **Step 5: Run broader verification**

Run: `pytest tests/test_scene_config.py tests/test_audio_mixer.py tests/test_comfyui_queue.py tests/test_video_compositor.py -v`
Expected: PASS

- [ ] **Step 6: Dry-run CLI verification**

Run: `python scripts/video_compositor.py --scene scenes/001_grandma_porch_summer.yaml --loop-clip output/video/demo_loop.mp4 --output output/video/demo_10h.mp4 --dry-run`
Expected: command preview prints without executing FFmpeg.
