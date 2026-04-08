from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

from scripts.audio_sourcing.stable_audio_gen import batch_generate, generate_sfx


class FakeTensor:
    def __init__(self, array: np.ndarray) -> None:
        self.array = array

    @property
    def T(self) -> "FakeTensor":
        return FakeTensor(self.array.T)

    def float(self) -> "FakeTensor":
        return self

    def cpu(self) -> "FakeTensor":
        return self

    def numpy(self) -> np.ndarray:
        return self.array


class FakeResult:
    def __init__(self, array: np.ndarray) -> None:
        self.audios = [FakeTensor(array)]


class FakeVAE:
    sampling_rate = 44_100


class FakePipeline:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.vae = FakeVAE()

    def to(self, device: str) -> "FakePipeline":
        self.device = device
        return self

    def __call__(self, prompt: str, **kwargs) -> FakeResult:
        self.calls.append({"prompt": prompt, **kwargs})
        waveform = np.tile(np.linspace(-0.1, 0.1, 4410, dtype=np.float32), (2, 1))
        return FakeResult(waveform)


def test_generate_sfx_writes_wav_using_injected_pipeline(tmp_path: Path) -> None:
    fake_pipeline = FakePipeline()

    output_path = generate_sfx(
        prompt="kitchen cup clink",
        duration=5.0,
        seed=7,
        output_path=tmp_path / "clink.wav",
        pipeline=fake_pipeline,
        device="cpu",
    )

    assert output_path.exists()
    data, sample_rate = sf.read(output_path)
    assert sample_rate == 44_100
    assert data.ndim == 2
    assert data.shape[1] == 2
    assert fake_pipeline.calls[0]["prompt"] == "kitchen cup clink"
    assert fake_pipeline.calls[0]["audio_end_in_s"] == 5.0


def test_batch_generate_reads_yaml_and_returns_paths(tmp_path: Path) -> None:
    prompts_path = tmp_path / "prompts.yaml"
    prompts_path.write_text(
        yaml.safe_dump(
            {
                "prompts": [
                    {"name": "glass", "prompt": "ice glass clink", "duration": 4},
                    {"name": "kitchen", "prompt": "distant kitchen clink", "duration": 6},
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    fake_pipeline = FakePipeline()

    paths = batch_generate(prompts_path, tmp_path / "generated", pipeline=fake_pipeline, device="cpu")

    assert [path.name for path in paths] == ["glass.wav", "kitchen.wav"]
    assert all(path.exists() for path in paths)
    assert len(fake_pipeline.calls) == 2
