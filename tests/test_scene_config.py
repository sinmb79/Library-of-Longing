from pathlib import Path

import yaml

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


def test_scene_config_accepts_optional_audio_sourcing_and_gen_alias(tmp_path: Path) -> None:
    scene_path = tmp_path / "scene_with_sourcing.yaml"
    scene_path.write_text(
        yaml.safe_dump(
            {
                "scene": {"id": "999", "slug": "sourcing-test"},
                "visual": {
                    "prompt": "demo prompt",
                    "negative_prompt": "demo negative",
                    "style": "ghibli",
                    "resolution": [3840, 2160],
                    "loop_duration_sec": 8,
                    "motion_prompt": "gentle dust",
                },
                "audio": {
                    "layers": {
                        "room_tone": {
                            "source": "./audio_sources/demo/room_tone.wav",
                            "volume": 0.25,
                            "sourcing": {
                                "tier": "procedural",
                                "type": "room_tone",
                                "params": {"base_freq": 55, "bandwidth": 180},
                            },
                        },
                        "continuous": {
                            "source": "./audio_sources/demo/fan_loop.wav",
                            "volume": 0.4,
                            "gen": {
                                "tier": "procedural",
                                "type": "fan",
                                "params": {"base_freq": 120},
                            },
                        },
                        "periodic": {
                            "sources": ["./audio_sources/demo/cicada_a.wav"],
                            "interval": [20, 30],
                            "volume": 0.5,
                            "sourcing": {
                                "tier": "freesound_cc0",
                                "queries": ["summer cicada chorus"],
                                "min_duration": 12,
                                "max_duration": 45,
                            },
                        },
                        "rare_events": {
                            "sources": ["./audio_sources/demo/kitchen_clink.wav"],
                            "interval": [120, 300],
                            "volume": 0.35,
                            "sourcing": {
                                "tier": "stable_audio",
                                "queries": ["kitchen ceramic cup clink"],
                                "prompt": "isolated ceramic cup clink in a quiet kitchen",
                            },
                        },
                    }
                },
                "video": {
                    "target_duration_hours": 1,
                    "film_grain": 10,
                    "vignette": True,
                    "time_lapse": False,
                },
                "metadata": {
                    "title": {"ko": "테스트", "en": "Test"},
                    "description": {"ko": "설명", "en": "Description"},
                    "tags": ["test"],
                    "storyline": {"ko": "이야기", "en": "Story"},
                    "culture": "KR",
                    "season": "summer",
                },
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    config = load_scene_config(scene_path)

    assert config["audio"]["layers"]["room_tone"]["sourcing"]["tier"] == "procedural"
    assert config["audio"]["layers"]["room_tone"]["sourcing"]["params"]["base_freq"] == 55
    assert config["audio"]["layers"]["continuous"]["sourcing"]["type"] == "fan"
    assert "gen" not in config["audio"]["layers"]["continuous"]
    assert config["audio"]["layers"]["periodic"]["sourcing"]["queries"] == ["summer cicada chorus"]
    assert config["audio"]["layers"]["rare_events"]["sourcing"]["prompt"].startswith("isolated ceramic")


def test_scene_config_accepts_loop_generation_resolution_and_upscale_model(tmp_path: Path) -> None:
    scene_path = tmp_path / "scene_with_loop_resolution.yaml"
    scene_path.write_text(
        yaml.safe_dump(
            {
                "scene": {"id": "998", "slug": "loop-resolution-test"},
                "visual": {
                    "prompt": "demo prompt",
                    "negative_prompt": "demo negative",
                    "style": "ghibli",
                    "resolution": [3840, 2160],
                    "loop_duration_sec": 8,
                    "motion_prompt": "gentle dust",
                    "loop_generation_resolution": [1920, 1080],
                    "upscale_model": "4x-UltraSharp",
                },
                "audio": {
                    "layers": {
                        "room_tone": {"source": "./audio_sources/demo/room_tone.wav", "volume": 0.25},
                        "continuous": {"source": "./audio_sources/demo/fan_loop.wav", "volume": 0.4},
                        "periodic": {
                            "sources": ["./audio_sources/demo/cicada_a.wav"],
                            "interval": [20, 30],
                            "volume": 0.5,
                        },
                        "rare_events": {
                            "sources": ["./audio_sources/demo/kitchen_clink.wav"],
                            "interval": [120, 300],
                            "volume": 0.35,
                        },
                    }
                },
                "video": {
                    "target_duration_hours": 1,
                    "film_grain": 10,
                    "vignette": True,
                    "time_lapse": False,
                },
                "metadata": {
                    "title": {"ko": "테스트", "en": "Test"},
                    "description": {"ko": "설명", "en": "Description"},
                    "tags": ["test"],
                    "storyline": {"ko": "이야기", "en": "Story"},
                    "culture": "KR",
                    "season": "summer",
                },
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    config = load_scene_config(scene_path)

    assert config["visual"]["loop_generation_resolution"] == [1920, 1080]
    assert config["visual"]["upscale_model"] == "4x-UltraSharp"


def test_scene_config_accepts_optional_external_still_image(tmp_path: Path) -> None:
    scene_path = tmp_path / "scene_with_external_still.yaml"
    scene_path.write_text(
        yaml.safe_dump(
            {
                "scene": {"id": "997", "slug": "external-still-test"},
                "visual": {
                    "prompt": "demo prompt",
                    "negative_prompt": "demo negative",
                    "style": "ghibli",
                    "resolution": [3840, 2160],
                    "loop_duration_sec": 8,
                    "motion_prompt": "gentle dust",
                    "still_image": "./external_stills/grandma_portrait.png",
                },
                "audio": {
                    "layers": {
                        "room_tone": {"source": "./audio_sources/demo/room_tone.wav", "volume": 0.25},
                        "continuous": {"source": "./audio_sources/demo/fan_loop.wav", "volume": 0.4},
                        "periodic": {
                            "sources": ["./audio_sources/demo/cicada_a.wav"],
                            "interval": [20, 30],
                            "volume": 0.5,
                        },
                        "rare_events": {
                            "sources": ["./audio_sources/demo/kitchen_clink.wav"],
                            "interval": [120, 300],
                            "volume": 0.35,
                        },
                    }
                },
                "video": {
                    "target_duration_hours": 1,
                    "film_grain": 10,
                    "vignette": True,
                    "time_lapse": False,
                },
                "metadata": {
                    "title": {"ko": "테스트", "en": "Test"},
                    "description": {"ko": "설명", "en": "Description"},
                    "tags": ["test"],
                    "storyline": {"ko": "이야기", "en": "Story"},
                    "culture": "KR",
                    "season": "summer",
                },
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    config = load_scene_config(scene_path)

    assert config["visual"]["still_image_path"] == (tmp_path / "external_stills" / "grandma_portrait.png").as_posix()
