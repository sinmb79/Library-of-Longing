from __future__ import annotations

import json
from pathlib import Path

from scripts.youtube_upload import build_upload_request, dry_run_upload, load_metadata


def test_build_upload_request_uses_metadata_defaults() -> None:
    metadata = {
        "title": "할머니 집 마루, 여름",
        "description": "ambient description",
        "tags": ["ambience", "nostalgia"],
        "categoryId": "10",
        "defaultLanguage": "ko",
        "defaultAudioLanguage": "ko",
        "privacyStatus": "private",
        "madeForKids": False,
    }

    request = build_upload_request(metadata)

    assert request["snippet"]["defaultLanguage"] == "ko"
    assert request["snippet"]["defaultAudioLanguage"] == "ko"
    assert request["status"]["privacyStatus"] == "private"
    assert request["status"]["selfDeclaredMadeForKids"] is False


def test_dry_run_returns_predicted_payload(tmp_path: Path) -> None:
    metadata = {
        "title": "Grandmother's Porch",
        "description": "ambient description",
        "tags": ["ambience"],
        "categoryId": "10",
        "defaultLanguage": "ko",
        "defaultAudioLanguage": "ko",
        "privacyStatus": "private",
        "madeForKids": False,
    }
    video = tmp_path / "final.mp4"
    thumb = tmp_path / "thumb.jpg"
    video.write_bytes(b"video")
    thumb.write_bytes(b"thumb")

    result = dry_run_upload(video_path=video, metadata=metadata, thumbnail_path=thumb)

    assert result["status"] == "dry_run"
    assert result["videoPath"].endswith("final.mp4")
    assert result["thumbnailPath"].endswith("thumb.jpg")
    assert result["request"]["snippet"]["title"] == "Grandmother's Porch"


def test_load_metadata_reads_json_file(tmp_path: Path) -> None:
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps({"title": "hello"}, ensure_ascii=False), encoding="utf-8")

    metadata = load_metadata(path)

    assert metadata["title"] == "hello"
