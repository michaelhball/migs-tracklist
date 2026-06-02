from migshazam.audd import load_token


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
