import json

from app.slack import action_blocks


def test_action_blocks_contains_json_values():
    blocks = action_blocks("https://example.com", "Example", 0.99)
    assert isinstance(blocks, list) and len(blocks) >= 2
    actions = blocks[1]
    assert actions["type"] == "actions"
    elements = actions["elements"]
    assert len(elements) >= 2
    approve = elements[0]
    payload = json.loads(approve["value"])  # value must be JSON string
    assert payload["action"] == "approve"
    assert payload["url"] == "https://example.com"

