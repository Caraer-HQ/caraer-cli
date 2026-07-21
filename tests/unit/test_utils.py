from caraer_cli.utils import deep_merge


def test_deep_merge_nested_objects() -> None:
    base = {"details": {"title": "Old", "category": "A"}, "privateApp": False}
    patch = {"details": {"title": "New"}}
    merged = deep_merge(base, patch)
    assert merged["details"]["title"] == "New"
    assert merged["details"]["category"] == "A"
    assert merged["privateApp"] is False
