# Library of Longing — Project Instructions

## Project Overview
AI-generated ambient YouTube channel "그리움의 라이브러리 (Library of Longing)".
Produces 10-hour nostalgic ambience videos with 4-layer sound design.

## Key Documents
- `Library_of_Longing_Masterplan.md` — Full strategy, concept, pipeline design
- `Codex_Development_Tasks.md` — Development task specification with priorities

## Development Rules

### Language
- All code, comments, variable names, docstrings: **English**
- Config files (scene YAML metadata fields): bilingual KO/EN as specified in schema

### Code Style
- Python scripts go in `scripts/`
- ComfyUI workflow JSONs go in `workflows/`
- Scene configs go in `scenes/`
- n8n workflows go in `n8n/`
- Use type hints in Python
- Use argparse for CLI interfaces
- Each script must be runnable standalone AND importable as module

### Environment
- Python 3.12.10 (system)
- ComfyUI: `C:\Users\sinmb\ComfyUI\` (has own .venv)
- FFmpeg 8.1 in PATH
- n8n 2.14.2 (npm global)
- GPU: RTX 4080 Super 16GB VRAM

### Existing Code to Reference (DO NOT modify these, read-only)
- `C:\Users\sinmb\workspace\scp-videos\produce_shorts_v2.py` — FFmpeg wrappers, video looping, audio mixing
- `C:\Users\sinmb\workspace\scp-videos\queue_optimized_v2.py` — ComfyUI API client, SageAttention/TeaCache config
- `C:\Users\sinmb\workspace\scp-videos\generate_long_videos.py` — Title cards, concat, normalization
- `C:\Users\sinmb\workspace\scp-videos\auto_produce.py` — Directory polling automation

### Models Available
- Checkpoint: `sd_xl_base_1.0.safetensors` in ComfyUI/models/checkpoints/
- LoRAs: `ghibli_style_sdxl.safetensors`, `watercolor_sdxl.safetensors`, `oil_painting_sdxl.safetensors` in ComfyUI/models/loras/
  - Ghibli trigger: `Studio Ghibli style`
  - Oil painting trigger: `oil painting`
  - Watercolor: no trigger word needed
- Video: Wan2.2-T2V (GGUF), SkyReels v3 (a2v/r2v/v2v) in ComfyUI/models/diffusion_models/
- Text encoder: UMT5-XXL (FP16 + FP8) in ComfyUI/models/text_encoders/
- VAE: wan_2.1_vae.safetensors in ComfyUI/models/vae/
- Upscaler: 4x-UltraSharp.pth in ComfyUI/models/upscale_models/
- RIFE: rife47.pth in ComfyUI/custom_nodes/ComfyUI-Frame-Interpolation/ckpts/rife/

### ComfyUI Custom Nodes
- ComfyUI-WanVideoWrapper (Wan2.2 T2V/I2V)
- ComfyUI-WaveSpeed (inference optimization)
- ComfyUI-VideoHelperSuite (video I/O)
- ComfyUI-KJNodes (utilities)
- ComfyUI-VibeVoice (audio generation)
- ComfyUI-AnimateDiff-Evolved (closed-loop animation)
- ComfyUI-Frame-Interpolation (RIFE frame interpolation)

### Python Packages Available
numpy, soundfile, librosa, torchaudio, torch, torchvision, pillow, pyyaml, pyloudnorm, jsonschema, requests, edge-tts, f5-tts

### Development Priority (Phase 1 first, C8 is prerequisite for all)
1. **Phase 1 (P0/P1):** C8 Scene Config → C1 Audio Mixer → C2 ComfyUI Workflow → C3 Video Compositor
2. **Phase 2 (P1):** C4 Final Assembly → C5 Thumbnail Generator
3. **Phase 3 (P2):** C6 YouTube Upload → C7 n8n Pipeline

### Output Directory Structure
```
output/
├── video/       # 10h composed videos
├── audio/       # Mixed ambient audio
├── thumbnails/  # Generated thumbnails
└── final/       # Merged final videos ready for upload
```

### Testing
- Each script should include a `if __name__ == "__main__":` block with a small test/demo
- Use the first scene config (001_grandma_porch_summer.yaml) as test input
