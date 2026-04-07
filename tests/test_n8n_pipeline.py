from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_n8n_workflow_contains_phase_order() -> None:
    path = PROJECT_ROOT / "n8n" / "library_of_longing_pipeline.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    node_names = [node["name"] for node in payload["nodes"]]

    assert "Manual Trigger" in node_names
    assert "Schedule Weekly" in node_names
    assert "Read Scene Config" in node_names
    assert "Generate Visual Loop" in node_names
    assert "Compose Video" in node_names
    assert "Mix Audio" in node_names
    assert "Assemble Final" in node_names
    assert "Generate Thumbnail" in node_names
    assert "Upload to YouTube" in node_names
    assert "Notify Completion" in node_names
