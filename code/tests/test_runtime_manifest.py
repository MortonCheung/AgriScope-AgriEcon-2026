import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_assets import verify


def test_ok_assets_pass(tmp_path):
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime" / "a.pkl").write_bytes(b"x")
    man = {"assets": [{"source": "s", "destination": "runtime/a.pkl",
                       "description": "d", "status": "OK"}]}
    result = verify(man, tmp_path)
    assert result["problems"] == []
    assert result["ok"] == 1 and result["total"] == 1


def test_missing_destination_reported(tmp_path):
    man = {"assets": [{"source": "s", "destination": "runtime/missing.pkl",
                       "description": "d", "status": "OK"}]}
    result = verify(man, tmp_path)
    assert len(result["problems"]) == 1
    assert "missing/empty destination" in result["problems"][0]


def test_empty_destination_reported(tmp_path):
    (tmp_path / "runtime" / "empty").mkdir(parents=True)
    man = {"assets": [{"source": "s", "destination": "runtime/empty",
                       "description": "d", "status": "OK"}]}
    result = verify(man, tmp_path)
    assert result["problems"] == ["missing/empty destination: runtime/empty"]


def test_unavailable_source_reported(tmp_path):
    man = {"assets": [{"source": "s", "destination": "runtime/a",
                       "description": "d", "status": "SKIP(missing-src)"}]}
    result = verify(man, tmp_path)
    assert len(result["problems"]) == 1
    assert "source unavailable" in result["problems"][0]


def test_destination_escape_reported(tmp_path):
    man = {"assets": [{"source": "s", "destination": "../outside.pkl",
                       "description": "d", "status": "OK"}]}
    result = verify(man, tmp_path)
    assert len(result["problems"]) == 1
    assert "escapes AgriScope" in result["problems"][0]
