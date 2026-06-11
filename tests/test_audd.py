import pytest

from migshazam.audd import AuddError, _parse_response, load_token


def test_parse_success_returns_detection():
    resp = {"status": "success",
            "result": {"artist": "Floyd Lee", "title": "One of These Days", "song_link": "https://lis.tn/x"}}
    d = _parse_response(resp, 390.0)
    assert d is not None
    assert d.artist == "Floyd Lee" and d.title == "One of These Days"
    assert d.source == "audd" and d.track_key == "audd:floyd lee|one of these days"
    assert d.time_s == 390.0


def test_parse_no_match_returns_none():
    assert _parse_response({"status": "success", "result": None}, 0.0) is None


def test_parse_error_raises_auderror():
    # e.g. expired token / out of credits — must not look like 'no match'
    resp = {"status": "error",
            "error": {"error_code": 900, "error_message": "the provided api_token is incorrect"}}
    with pytest.raises(AuddError, match="api_token is incorrect"):
        _parse_response(resp, 0.0)


def test_load_token_explicit_wins():
    assert load_token("abc123") == "abc123"


def test_load_token_from_env(monkeypatch):
    monkeypatch.setenv("AUDD_API_TOKEN", "env-token")
    assert load_token() == "env-token"


def test_load_token_from_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("AUDD_API_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text('AUDD_API_TOKEN="file-token"\n')
    assert load_token() == "file-token"


def test_load_token_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("AUDD_API_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert load_token() is None


def test_parse_captures_timecode_and_apple_preview():
    resp = {"status": "success",
            "result": {"artist": "A", "title": "T", "song_link": "https://lis.tn/x",
                       "timecode": "01:23",
                       "apple_music": {"previews": [{"url": "https://p/a.m4a"}]},
                       "deezer": {"preview": "https://p/d.mp3"}}}
    d = _parse_response(resp, 0.0)
    assert d.offset_s == 83.0
    assert d.preview_url == "https://p/a.m4a"  # apple preferred over deezer


def test_parse_preview_falls_back_to_deezer():
    resp = {"status": "success",
            "result": {"artist": "A", "title": "T",
                       "deezer": {"preview": "https://p/d.mp3"}}}
    assert _parse_response(resp, 0.0).preview_url == "https://p/d.mp3"


def test_parse_timecode_junk_is_ignored():
    resp = {"status": "success",
            "result": {"artist": "A", "title": "T", "timecode": "n/a"}}
    d = _parse_response(resp, 0.0)
    assert d.offset_s is None and d.preview_url is None
