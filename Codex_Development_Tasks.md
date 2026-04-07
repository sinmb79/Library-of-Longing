# Codex Development Task Specification
## Library of Longing — Production Pipeline

**Date:** 2026-04-08
**Context:** Masterplan (Library_of_Longing_Masterplan.md) 기반, 기존 환경 조사 완료 후 작성

---

## A. Existing Assets — No Development Needed (Copy/Reuse)

These components already exist on this machine and can be used as-is or with minimal config.

### A1. Infrastructure (Ready)

| Component | Location | Status |
|-----------|----------|--------|
| ComfyUI 0.18.1 | `C:\Users\sinmb\ComfyUI\` | Installed, GPU detected |
| Wan2.2 T2V model | `ComfyUI\models\diffusion_models\LowNoise\Wan2.2-T2V-A14B-LowNoise-Q4_K_M.gguf` (9GB) | Ready |
| SkyReels v3 (a2v/r2v/v2v) | `ComfyUI\models\diffusion_models\` (31GB) | Ready |
| UMT5-XXL text encoder | `ComfyUI\models\text_encoders\` (FP16 + FP8) | Ready |
| Wan 2.1 VAE | `ComfyUI\models\vae\wan_2.1_vae.safetensors` | Ready |
| VibeVoice TTS | `ComfyUI\models\vibevoice\` (1.5B + 0.5B Realtime) | Ready |
| FFmpeg 8.1 | System PATH | Ready |
| n8n 2.14.2 | npm global | Ready (no workflows yet) |
| Node.js 24.14 | System | Ready |
| Python 3.12.10 | System + ComfyUI .venv | Ready |
| Docker CLI 29.3.1 | System | Ready |

### A2. ComfyUI Custom Nodes (Ready)

| Node | Purpose | Ambient Use |
|------|---------|-------------|
| ComfyUI-WanVideoWrapper | Wan2.2 T2V/I2V | Loop animation generation |
| ComfyUI-WaveSpeed | Inference optimization (First Block Cache) | Faster generation |
| ComfyUI-VideoHelperSuite | Video I/O, frame batching | Video processing |
| ComfyUI-KJNodes | Utility nodes | General workflow support |
| ComfyUI-VibeVoice | Expressive audio generation | Ambient narration/voice |

### A3. Reusable Python Code from scp-videos

**Source:** `C:\Users\sinmb\workspace\scp-videos\`

| File | Reusable Functions | Copy/Adapt |
|------|-------------------|------------|
| `produce_shorts_v2.py` | `get_duration()` — FFprobe wrapper | Copy as-is |
| | Video looping via `stream_loop` + trim | Copy pattern |
| | FFmpeg `filter_complex` multi-stream mixing | Copy pattern |
| | Lanczos upscaling pipeline | Copy pattern |
| | Audio concat with silence gaps | Adapt for ambient |
| `queue_optimized_v2.py` | ComfyUI API client (`POST /prompt`, `/queue`) | Copy & adapt |
| | SageAttention + TeaCache optimization config | Copy as-is |
| | Workflow JSON builder pattern | Adapt for ambient |
| | Output polling via glob patterns | Copy as-is |
| `generate_long_videos.py` | Title card generation (FFmpeg + custom font) | Adapt for ambient |
| | Clip normalization (resolution/fps/codec) | Copy as-is |
| | FFmpeg concat demuxer pattern | Copy as-is |
| `auto_produce.py` | Directory polling + auto-trigger | Copy & adapt |

### A4. Reusable TypeScript from shorts-engine

**Source:** `C:\Users\sinmb\workspace\media\`

| Component | Path | Reusable For |
|-----------|------|-------------|
| YouTube Upload Adapter | `src/adapters/upload/youtube-upload-adapter.ts` | YouTube API upload scaffold |
| Platform Specs | `src/platform/` | YouTube metadata format |
| Prompt Generation | `src/prompt/` | AI prompt template pattern |
| Cost Routing | `src/domain/` | Backend selection logic |
| .env.example | Root | API key template |

### A5. Existing Audio Toolchain (Python packages)

| Package | Version | Use |
|---------|---------|-----|
| librosa | 0.11.0 | Audio analysis/processing |
| soundfile | 0.13.1 | WAV/FLAC I/O |
| torchaudio | 2.11.0 | PyTorch audio |
| edge-tts | 7.2.8 | Microsoft TTS |
| f5-tts | 1.1.18 | F5-TTS |
| MelBandRoformer | model | Audio separation |

### A6. Existing Font Asset

| Asset | Location |
|-------|----------|
| BebasNeue-Regular.ttf | `C:\Users\sinmb\workspace\scp-videos\fonts\` |

---

## B. Manual Setup — COMPLETED (2026-04-08)

All models, custom nodes, dependencies, and project structure have been installed.
**Codex does NOT need to install or verify any of these — they are confirmed present.**

See `CLAUDE.md` for the authoritative list of available models, nodes, and packages.

### B1. Models Installed ✅

| Model | File | Path |
|-------|------|------|
| SDXL 1.0 | `sd_xl_base_1.0.safetensors` (5.4GB) | `ComfyUI/models/checkpoints/` |
| Ghibli LoRA | `ghibli_style_sdxl.safetensors` (8.4MB) | `ComfyUI/models/loras/` |
| Watercolor LoRA | `watercolor_sdxl.safetensors` (12MB) | `ComfyUI/models/loras/` |
| Oil Painting LoRA | `oil_painting_sdxl.safetensors` (8.4MB) | `ComfyUI/models/loras/` |
| RIFE v4.7 | `rife47.pth` (21MB) | `ComfyUI/custom_nodes/ComfyUI-Frame-Interpolation/ckpts/rife/` |
| 4x-UltraSharp | `4x-UltraSharp.pth` (64MB) | `ComfyUI/models/upscale_models/` |

### B2. Custom Nodes Installed ✅

| Node | Status |
|------|--------|
| ComfyUI-AnimateDiff-Evolved | Installed + dependencies |
| ComfyUI-Frame-Interpolation | Installed + opencv-contrib-python, einops, kornia |

### B3. Python Packages Installed ✅

| Package | Status |
|---------|--------|
| pyyaml, pyloudnorm, pillow | Installed (system Python) |
| opencv-contrib-python, einops, kornia | Installed (ComfyUI .venv) |

### B4. Project Structure Created ✅

Font `BebasNeue-Regular.ttf` copied to `fonts/`. All output directories created.

---

## C. Codex Development Tasks

Priority: P0 (blocking) → P1 (core pipeline) → P2 (automation) → P3 (optimization)

---

### TASK C1: Ambient Audio Mixer (P0 — Blocking)
**Priority:** P0 — All videos need audio
**Type:** New Python script
**Output:** `scripts/audio_mixer.py`

**Description:**
Masterplan B3의 4-Layer Sound Design을 구현하는 오디오 믹싱 엔진.

**Spec:**
```
Input:
  - Layer config YAML/JSON:
    {
      "room_tone": { "file": "room.wav", "volume": 0.3 },
      "continuous": { "file": "fan.wav", "volume": 0.6 },
      "periodic": {
        "files": ["crackle1.wav", "crackle2.wav"],
        "interval_range": [30, 120],  // seconds
        "volume": 0.4
      },
      "rare_events": {
        "files": ["thunder.wav", "bird.wav", "door.wav"],
        "interval_range": [300, 900],  // 5~15 min
        "volume": 0.35
      }
    }
  - Target duration (seconds)
  - Output format: 48kHz/24bit WAV

Output:
  - Single mixed WAV file with randomized event placement
  - Crossfade at loop boundaries (5~10s)

Requirements:
  - Use numpy + soundfile (already installed)
  - Binaural stereo panning for spatial feel
  - Master to -14 LUFS (YouTube standard)
  - Ensure no clipping (peak limiter)
  - Seed-based randomization for reproducibility
```

**Reuse from:** `scp-videos/produce_shorts_v2.py` — BGM synthesis pattern (numpy sine waves), audio concat logic

---

### TASK C2: ComfyUI Ambient Workflow Builder (P0 — Blocking)
**Priority:** P0 — Image/video generation is the core
**Type:** Python script + ComfyUI workflow JSON
**Output:** `scripts/comfyui_queue.py` + `workflows/ambient_scene.json`

**Description:**
Masterplan C1 Stage 1~2를 자동화. ComfyUI API를 통해 장면 이미지 생성 → 루프 애니메이션 생성을 큐잉.

**Spec:**
```
Step 1: Image Generation (SDXL + Style LoRA)
  - Input: scene description (prompt), style (ghibli/watercolor/oil), negative prompt
  - Generate 4K (3840x2160) static scene image
  - Apply LoRA for art style
  - Output: PNG image

Step 2: Loop Animation (Wan2.2)
  - Input: Step 1 output image (as first frame AND last frame)
  - Motion prompt: gentle movement description
  - Output: 5~10 second seamless loop MP4
  - Use existing optimization: SageAttention + TeaCache (from scp-videos)

API Integration:
  - POST workflow to ComfyUI /prompt endpoint
  - Poll for completion
  - Download output
```

**Reuse from:** `scp-videos/queue_optimized_v2.py` — ComfyUI API client, SageAttention/TeaCache config, polling logic. Adapt workflow JSON from Wan2.2 pattern to include SDXL image generation step.

---

### TASK C3: Video Compositor (P1 — Core Pipeline)
**Priority:** P1
**Type:** Python script (FFmpeg wrapper)
**Output:** `scripts/video_compositor.py`

**Description:**
Masterplan C1 Stage 3 — 루프 클립 → 10시간 영상 합성.

**Spec:**
```
Input:
  - Loop clip (5~10s MP4)
  - Target duration (default: 36000s = 10h)
  - Post-processing options:
    - Film grain intensity (0~100, default: 15)
    - Vignette (on/off, default: on)
    - Color temperature shift (warm/neutral)

Output:
  - 4K H.264 MP4, CRF 18, preset slow
  - 24fps

Advanced Mode (time-lapse):
  Input:
    - Multiple scene images (dawn/morning/afternoon/evening/night)
    - Transition duration per segment
  Output:
    - Crossfade between time segments over 10h duration

FFmpeg command template:
  Basic: stream_loop → noise filter → vignette → encode
  Time-lapse: concat with xfade filter
```

**Reuse from:** `scp-videos/produce_shorts_v2.py` — video looping (`stream_loop`), FFmpeg encoding settings (CRF 17~18, libx264, preset slow). `generate_long_videos.py` — concat demuxer, normalization.

---

### TASK C4: Final Assembly Script (P1 — Core Pipeline)
**Priority:** P1
**Type:** Python script (FFmpeg wrapper)
**Output:** `scripts/assemble_final.py`

**Description:**
Masterplan C1 Stage 5 — 영상 + 오디오 머지 + 메타데이터.

**Spec:**
```
Input:
  - Video file (from C3)
  - Audio file (from C1)
  - Metadata YAML:
    {
      "title_ko": "할머니 집 마루, 여름 — 매미와 선풍기 | 10시간",
      "title_en": "Grandmother's Porch, Summer — Cicadas & Old Fan | 10 Hours",
      "description": "...",
      "tags": ["ambience", "nostalgia", ...],
      "storyline": "여름이면 할머니 집에 갔다..."
    }

Output:
  - Final MP4 (video + AAC 256kbps audio)
  - YouTube metadata JSON (title, description, tags, category, language)
  - Thumbnail request (trigger ComfyUI for variant image)

FFmpeg merge:
  ffmpeg -i video.mp4 -i audio.wav -c:v copy -c:a aac -b:a 256k final.mp4
```

**Reuse from:** `scp-videos/produce_shorts_v2.py` — `assemble_final()` function pattern. `media/shorts-engine` — YouTube metadata format from platform specs.

---

### TASK C5: Thumbnail Generator (P1 — Core Pipeline)
**Priority:** P1
**Type:** Python script + ComfyUI workflow
**Output:** `scripts/thumbnail_gen.py` + `workflows/thumbnail.json`

**Description:**
장면 이미지의 변형 + 텍스트 오버레이로 썸네일 자동 생성.

**Spec:**
```
Input:
  - Base scene image (from C2 Step 1)
  - Title text (bilingual: KO + EN)
  - Duration text ("10 Hours" / "10시간")

Processing:
  1. ComfyUI: scene image variation (slight color/composition change)
  2. Python (Pillow): text overlay
     - Font: BebasNeue (from scp-videos/fonts/) + Korean font
     - Layout: title bottom-left, duration bottom-right
     - Semi-transparent dark gradient bar at bottom

Output:
  - 1280x720 JPG (YouTube thumbnail spec)
```

**Reuse from:** `scp-videos/generate_long_videos.py` — `make_title_card()` FFmpeg text overlay pattern. `scp-videos/fonts/BebasNeue-Regular.ttf` — copy to project.

---

### TASK C6: YouTube Auto-Upload (P2 — Automation)
**Priority:** P2
**Type:** Python script
**Output:** `scripts/youtube_upload.py`

**Description:**
YouTube Data API v3를 이용한 자동 업로드.

**Spec:**
```
Input:
  - Final MP4 file
  - Thumbnail JPG
  - Metadata JSON (from C4)

Features:
  - OAuth2 authentication (token refresh)
  - Resumable upload (10h videos = large files)
  - Set: title, description, tags, category (22=People & Blogs or 10=Music)
  - Set: default language, thumbnail
  - Set: visibility (private → scheduled publish)
  - Premiere scheduling option

Output:
  - Video ID
  - Upload status log
```

**Reuse from:** `media/src/adapters/upload/youtube-upload-adapter.ts` — OAuth2 flow scaffold (rewrite in Python). Google API Python client library (`google-api-python-client`).

---

### TASK C7: n8n Pipeline Orchestration (P2 — Automation)
**Priority:** P2
**Type:** n8n workflow JSON
**Output:** `n8n/library_of_longing_pipeline.json`

**Description:**
Masterplan C1 전체 파이프라인을 n8n으로 오케스트레이션.

**Spec:**
```
Trigger: Manual or Scheduled (weekly)

Flow:
  1. Read scene config (from scenes/ directory)
  2. Call C2: ComfyUI image + loop generation
  3. Wait for ComfyUI completion (polling)
  4. Call C3: Video composition (10h)
  5. Call C1: Audio mixing
  6. Call C4: Final assembly
  7. Call C5: Thumbnail generation
  8. Call C6: YouTube upload
  9. Notify completion (Telegram/Slack/Email)

Error handling:
  - Retry on ComfyUI timeout
  - Skip to next scene on failure
  - Log all steps

n8n nodes to use:
  - Execute Command (Python scripts)
  - HTTP Request (ComfyUI API)
  - Wait/Delay
  - IF/Switch (error handling)
  - Telegram/Email (notification)
```

**Reuse from:** Existing n8n installation. `scp-videos/auto_produce.py` — polling/orchestration pattern (translate to n8n flow).

---

### TASK C8: Scene Config System (P1 — Core Pipeline)
**Priority:** P1
**Type:** YAML schema + templates
**Output:** `scenes/schema.yaml` + `scenes/001_grandma_porch_summer.yaml` (template)

**Description:**
각 영상의 모든 설정을 하나의 YAML 파일로 정의. 모든 스크립트(C1~C6)가 이 config를 입력으로 사용.

**Spec:**
```yaml
# Scene Configuration Schema
scene:
  id: "001"
  slug: "grandma-porch-summer"

visual:
  prompt: "korean traditional hanok maru wooden floor, old electric fan spinning..."
  negative_prompt: "realistic photo, modern, dark, gloomy"
  style: "ghibli"  # ghibli | watercolor | oil
  resolution: [3840, 2160]
  loop_duration_sec: 8
  motion_prompt: "gentle fan spinning, light breeze moving curtain..."

audio:
  layers:
    room_tone: { source: "freesound:12345", volume: 0.3 }
    continuous: { source: "freesound:67890", volume: 0.6 }
    periodic:
      sources: ["freesound:11111", "freesound:22222"]
      interval: [30, 120]
      volume: 0.4
    rare_events:
      sources: ["freesound:33333", "freesound:44444"]
      interval: [300, 900]
      volume: 0.35

video:
  target_duration_hours: 10
  film_grain: 15
  vignette: true
  time_lapse: false  # true for advanced time-flow mode

metadata:
  title:
    ko: "할머니 집 마루, 여름 — 매미와 선풍기 | 10시간"
    en: "Grandmother's Porch, Summer — Cicadas & Old Fan | 10 Hours"
  description:
    ko: "여름이면 할머니 집에 갔다..."
    en: "Every summer, I went to grandmother's house..."
  tags: ["ambience", "nostalgia", "korean", "summer", "cicadas"]
  storyline:
    ko: "여름이면 할머니 집에 갔다. 마루에 누우면..."
    en: "Every summer, I went to grandmother's house..."
  culture: "KR"
  season: "summer"
```

---

## D. Development Priority Summary

```
Phase 1 (Week 1): Foundation — Can produce 1 video manually
  1. [P0] C8: Scene Config System    ← START HERE (all scripts depend on this)
  2. [P0] C1: Audio Mixer
  3. [P0] C2: ComfyUI Workflow Builder
  4. [P1] C3: Video Compositor

Phase 2 (Week 2): Complete Pipeline — End-to-end production
  5. [P1] C4: Final Assembly
  6. [P1] C5: Thumbnail Generator

Phase 3 (Week 3): Automation — Hands-free production
  7. [P2] C6: YouTube Auto-Upload
  8. [P2] C7: n8n Pipeline Orchestration
```

---

## E. Project Structure

```
C:\Users\sinmb\workspace\Library-of-Londing\
├── Library_of_Longing_Masterplan.md       # Strategy doc (existing)
├── Codex_Development_Tasks.md             # This file
├── scripts/                               # Python production scripts
│   ├── audio_mixer.py                     # C1
│   ├── comfyui_queue.py                   # C2
│   ├── video_compositor.py                # C3
│   ├── assemble_final.py                  # C4
│   ├── thumbnail_gen.py                   # C5
│   └── youtube_upload.py                  # C6
├── workflows/                             # ComfyUI workflow JSONs
│   ├── ambient_scene.json                 # C2: SDXL → Wan2.2 loop
│   └── thumbnail.json                     # C5: Thumbnail variation
├── scenes/                                # Per-video config files
│   ├── schema.yaml                        # C8: Config schema
│   └── 001_grandma_porch_summer.yaml      # First scene template
├── n8n/                                   # n8n workflow files
│   └── library_of_longing_pipeline.json   # C7
├── fonts/                                 # Copy from scp-videos/fonts/
├── audio_sources/                         # Downloaded sound files
└── output/                                # Final production output
    ├── video/
    ├── audio/
    ├── thumbnails/
    └── final/
```

---

## F. Dependencies — ALREADY INSTALLED ✅

All required packages are installed. No action needed.

```
# System Python: pyyaml, pyloudnorm, pillow, numpy, soundfile, librosa, requests
# ComfyUI .venv: opencv-contrib-python, einops, kornia, torch, torchvision, torchaudio
# Phase 3 only (install when starting C6): google-api-python-client, google-auth-oauthlib
```

---

## G. Reference Code (READ-ONLY — do not modify)

These existing scripts contain reusable patterns. Read them for reference:

```
C:\Users\sinmb\workspace\scp-videos\produce_shorts_v2.py   — FFmpeg wrappers, video looping, audio mixing
C:\Users\sinmb\workspace\scp-videos\queue_optimized_v2.py   — ComfyUI API client, SageAttention/TeaCache
C:\Users\sinmb\workspace\scp-videos\generate_long_videos.py — Title cards, concat, normalization
C:\Users\sinmb\workspace\scp-videos\auto_produce.py         — Directory polling automation
```

Font asset already copied to `fonts/BebasNeue-Regular.ttf`.

---

*Generated: 2026-04-08*
*For: Codex development agent*
*Review: User (planning/review)*
