from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import soundfile as sf
import yaml


DEFAULT_NEGATIVE_PROMPT = "low quality, average quality, noise, distortion"
DEFAULT_OUTPUT_DIR = Path("audio_sources") / "stable_audio"
DEFAULT_MODEL_ID = "stabilityai/stable-audio-open-1.0"


def _load_pipeline(model_id: str = DEFAULT_MODEL_ID, device: str = "cuda"):
    import torch
    from diffusers.pipelines.stable_audio.pipeline_stable_audio import StableAudioPipeline

    pipe = StableAudioPipeline.from_pretrained(model_id, torch_dtype=torch.float16)
    return pipe.to(device)


def _audio_to_numpy(audio_like: Any):
    current = audio_like
    if hasattr(current, "T"):
        current = current.T
    for method in ("float", "cpu", "numpy"):
        if hasattr(current, method):
            current = getattr(current, method)()
    return current


def generate_sfx(
    prompt: str,
    duration: float,
    seed: int,
    output_path: str | Path,
    *,
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
    num_inference_steps: int = 50,
    pipeline: Any | None = None,
    device: str = "cuda",
    model_id: str = DEFAULT_MODEL_ID,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pipe = pipeline or _load_pipeline(model_id=model_id, device=device)

    call_kwargs = {
        "negative_prompt": negative_prompt,
        "num_inference_steps": num_inference_steps,
        "audio_end_in_s": duration,
        "num_waveforms_per_prompt": 1,
    }
    try:
        import torch

        if device and device != "cpu":
            call_kwargs["generator"] = torch.Generator(device).manual_seed(seed)
        else:
            call_kwargs["generator"] = torch.Generator("cpu").manual_seed(seed)
    except Exception:
        pass

    result = pipe(prompt, **call_kwargs)
    audio = _audio_to_numpy(result.audios[0])
    sample_rate = int(getattr(getattr(pipe, "vae", None), "sampling_rate", 44_100))
    sf.write(output_path, audio, sample_rate)

    sidecar = {
        "provider": "stable_audio",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "duration": duration,
        "seed": seed,
        "num_inference_steps": num_inference_steps,
        "model_id": model_id,
        "sample_rate": sample_rate,
    }
    output_path.with_suffix(".json").write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def batch_generate(
    prompts_yaml: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
    num_inference_steps: int = 50,
    pipeline: Any | None = None,
    device: str = "cuda",
    model_id: str = DEFAULT_MODEL_ID,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    config = yaml.safe_load(prompts_yaml.read_text(encoding="utf-8"))
    prompts = config.get("prompts", [])
    paths: list[Path] = []
    for index, prompt_config in enumerate(prompts):
        name = prompt_config["name"]
        prompt = prompt_config["prompt"]
        duration = float(prompt_config.get("duration", 10.0))
        seed = int(prompt_config.get("seed", index))
        path = generate_sfx(
            prompt=prompt,
            duration=duration,
            seed=seed,
            output_path=output_dir / f"{name}.wav",
            negative_prompt=negative_prompt,
            num_inference_steps=num_inference_steps,
            pipeline=pipeline,
            device=device,
            model_id=model_id,
        )
        paths.append(path)
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate fallback audio with Stable Audio Open.")
    parser.add_argument("--prompt", type=str, default=None, help="Single prompt to generate.")
    parser.add_argument("--duration", type=float, default=10.0, help="Output duration in seconds.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--output", type=Path, default=None, help="Output path for single prompt generation.")
    parser.add_argument("--prompts-yaml", type=Path, default=None, help="Batch prompt YAML file.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Batch output directory.")
    parser.add_argument("--steps", type=int, default=50, help="Inference steps.")
    parser.add_argument("--device", type=str, default="cuda", help="Execution device.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.prompts_yaml:
        paths = batch_generate(
            args.prompts_yaml,
            output_dir=args.output_dir,
            num_inference_steps=args.steps,
            device=args.device,
        )
        print(json.dumps([path.as_posix() for path in paths], ensure_ascii=False, indent=2))
        return

    if not args.prompt:
        raise SystemExit("--prompt or --prompts-yaml is required.")

    output_path = args.output or (DEFAULT_OUTPUT_DIR / "generated.wav")
    print(
        generate_sfx(
            prompt=args.prompt,
            duration=args.duration,
            seed=args.seed,
            output_path=output_path,
            num_inference_steps=args.steps,
            device=args.device,
        )
    )


if __name__ == "__main__":
    main()
