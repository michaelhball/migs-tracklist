from migshazam.recognize import Recognizer


def test_parse_valid_response():
    out = {
        "matches": [{"frequencyskew": 0.01, "timeskew": 0.0}],
        "track": {
            "key": "357027",
            "title": "Never Gonna Give You Up",
            "subtitle": "Rick Astley",
            "url": "https://www.shazam.com/track/357027",
        },
    }
    d = Recognizer.parse(out, time_s=30.0, speed=1.06)
    assert d is not None
    assert d.track_key == "357027"
    assert d.title == "Never Gonna Give You Up"
    assert d.artist == "Rick Astley"
    assert d.time_s == 30.0
    assert d.speed_factor == 1.06
    assert d.frequency_skew == 0.01
    assert d.url.endswith("357027")


def test_parse_no_match_returns_none():
    assert Recognizer.parse({"matches": []}, 0.0, 1.0) is None
    assert Recognizer.parse(None, 0.0, 1.0) is None


def test_parse_track_without_key_returns_none():
    assert Recognizer.parse({"track": {"title": "x"}}, 0.0, 1.0) is None


def test_parse_captures_offset_and_preview_url():
    out = {
        "matches": [{"offset": 123.4, "frequencyskew": 0.0, "timeskew": 0.0}],
        "track": {
            "key": "1", "title": "T", "subtitle": "A",
            "hub": {
                "actions": [
                    {"name": "apple", "type": "applemusicplay", "id": "99"},
                    {"name": "apple", "type": "uri",
                     "uri": "https://audio-ssl.itunes.apple.com/x/preview.m4a"},
                ],
            },
        },
    }
    d = Recognizer.parse(out, 0.0, 1.0)
    assert d.offset_s == 123.4
    assert d.preview_url == "https://audio-ssl.itunes.apple.com/x/preview.m4a"


def test_parse_without_hub_or_offset_leaves_fields_none():
    out = {"matches": [{}], "track": {"key": "1", "title": "T", "subtitle": "A"}}
    d = Recognizer.parse(out, 0.0, 1.0)
    assert d.offset_s is None and d.preview_url is None
