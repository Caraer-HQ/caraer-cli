from __future__ import annotations

from caraer_cli.formatters.timestamps import epoch_ms_to_iso, normalize_payload


def test_epoch_ms_to_iso() -> None:
    assert epoch_ms_to_iso(1_700_000_000_000) == "2023-11-14T22:13:20Z"
    assert epoch_ms_to_iso("1700000000000") == "2023-11-14T22:13:20Z"


def test_normalize_payload_converts_and_sorts() -> None:
    data = [
        {"uuid": "old", "createdAt": 1_700_000_000_000, "name": "a"},
        {"uuid": "new", "createdAt": 1_710_000_000_000, "name": "b"},
    ]
    normalized = normalize_payload(data)
    assert normalized[0]["uuid"] == "new"
    assert normalized[0]["createdAt"] == "2024-03-09T16:00:00Z"
    assert normalized[1]["createdAt"] == "2023-11-14T22:13:20Z"


def test_normalize_nested_dict() -> None:
    payload = normalize_payload({"createdAt": 1_700_000_000_000, "nested": {"updatedAt": 1_700_000_000_000}})
    assert payload["createdAt"] == "2023-11-14T22:13:20Z"
    assert payload["nested"]["updatedAt"] == "2023-11-14T22:13:20Z"
