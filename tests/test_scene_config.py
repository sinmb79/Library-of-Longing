from pathlib import Path

from scripts.scene_config import load_scene_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_load_project_scene_config_normalizes_known_fields() -> None:
    config = load_scene_config(PROJECT_ROOT / "scenes" / "001_grandma_porch_summer.yaml")

    assert config["scene"]["id"] == "001"
    assert config["scene"]["slug"] == "grandma-porch-summer"
    assert config["visual"]["style"] == "ghibli"
    assert config["visual"]["resolution"] == [3840, 2160]
    assert config["video"]["target_duration_hours"] == 10
    assert config["metadata"]["title"]["ko"].startswith("할머니 집 마루")
    assert config["audio"]["layers"]["room_tone"]["source_path"] == (
        PROJECT_ROOT / "audio_sources" / "grandma_porch" / "room_tone.wav"
    ).as_posix()


def test_scene_config_accepts_optional_timelapse_segments() -> None:
    config = load_scene_config(PROJECT_ROOT / "scenes" / "001_grandma_porch_summer.yaml")

    assert config["video"]["time_lapse_segments"][0]["label"] == "dawn"
    assert config["video"]["time_lapse_segments"][0]["source_path"].endswith("grandma_dawn.png")
