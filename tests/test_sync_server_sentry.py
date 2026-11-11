"""The sync server must never ship ciphertext, the bearer token or note paths to Sentry."""
from sync_server.server import _scrub_event


def test_scrub_removes_body_token_and_note_path():
    event = {
        "request": {
            "url": "https://sync.example.com/notes/projects/Secret%20Plan.md",
            "query_string": "since=1",
            "data": {"ciphertext": "AAAA", "content_hash": "h"},
            "cookies": {"a": "b"},
            "headers": {"Authorization": "Bearer s3cret", "Content-Type": "application/json"},
        }
    }
    out = _scrub_event(event, {})["request"]
    assert "data" not in out and "cookies" not in out and "query_string" not in out
    assert out["headers"] == {"Content-Type": "application/json"}
    assert out["url"] == "https://sync.example.com/notes/<redacted>"


def test_scrub_leaves_non_note_urls_and_events_without_request():
    event = {"request": {"url": "https://sync.example.com/manifest"}}
    assert _scrub_event(event, {})["request"]["url"] == "https://sync.example.com/manifest"
    assert _scrub_event({"message": "x"}, {}) == {"message": "x"}
