from backend.app.services.vlm_detector import parse_items

KNOWN = {"potato", "brinjal"}


def test_aliases_junk_and_plurals():
    raw = '{"items":[{"name":"Potatoes","count":3},{"name":"eggplant","count":2},{"name":"leaf","count":1}]}'
    assert parse_items(raw, KNOWN) == [{"name": "potato", "count": 3}, {"name": "brinjal", "count": 2}]


def test_truncated_json_is_salvaged():
    raw = '```json\n{"items":[{"name":"potato","count":3},{"name":"bell pepper","count":4},{"name":"tom'
    assert parse_items(raw, KNOWN) == [{"name": "potato", "count": 3}, {"name": "capsicum", "count": 4}]


def test_garbage_returns_empty():
    assert parse_items("sorry, I cannot help", KNOWN) == []
