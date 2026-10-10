"""真实故障边界：新数据确实进上下文，发布不会并发或回退，Daily 不受污染。"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipelines.long_horizon import run_long_horizon_job as job
from scripts.run_daily_chain import eligible


def test_append_respects_scope_qc_and_frozen_history(tmp_path, monkeypatch):
    frozen = tmp_path / "frozen.parquet"
    daily = tmp_path / "daily.parquet"
    pd.DataFrame({"date": ["2026-09-14"], "crop": ["土豆"], "price_per_kg": [2.0]}).to_parquet(frozen)
    rows = []
    for day, city, level, comparable, qc, price in [
        ("2026-09-14", "沈阳", "wholesale", True, "OK", 99),
        ("2026-09-15", "沈阳", "wholesale", True, "OK", 3),
        ("2026-09-16", "沈阳", "retail", False, "OK", 100),
        ("2026-09-17", "大连", "wholesale", True, "OK", 101),
        ("2026-09-18", "沈阳", "wholesale", True, "SUSPECT", 102),
    ]:
        rows.append(dict(date=day, city=city, crop_standard="土豆", price_per_kg=price,
                         price_level=level, model_comparable=comparable, quality_status=qc))
    pd.DataFrame(rows).to_parquet(daily)
    monkeypatch.setattr(job, "FROZEN_DATA", frozen)
    monkeypatch.setattr(job, "DAILY_DATA", daily)
    latest = tmp_path / "latest.json"
    latest.write_text(json.dumps(dict(status="partial", contract_valid=True, crawl_status="OK", latest_data_date="2026-09-15")))
    monkeypatch.setattr(job, "DAILY_LATEST", latest)
    history, meta = job.load_runtime_history()
    assert history.price_per_kg.tolist() == [2, 3]
    assert meta["latest_data_date"] == "2026-09-15"
    assert meta["appended_rows"] == 1
    hist2, meta2 = job.load_runtime_history("2026-09-14")
    assert hist2.price_per_kg.tolist() == [2]
    assert meta2["runtime_data_version"] != meta["runtime_data_version"]
    latest.write_text(json.dumps(dict(status="failed", contract_valid=False, latest_data_date="2026-09-18")))
    failed_history, _ = job.load_runtime_history()
    assert failed_history.price_per_kg.tolist() == [2]


def test_lock_rejects_concurrent_writer(tmp_path, monkeypatch):
    monkeypatch.setattr(job, "LOCK_PATH", tmp_path / "lock")
    with job.job_lock():
        with pytest.raises(RuntimeError, match="already running"):
            with job.job_lock():
                pass
    with job.job_lock():
        pass


def test_atomic_idempotent_and_no_rollback(tmp_path, monkeypatch):
    monkeypatch.setattr(job, "SNAPSHOT_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(job, "LOCK_PATH", tmp_path / "lock")
    current = {"as_of": "2026-10-06", "snapshot_hash": "new", "n_entries": 120}
    assert job.write_snapshot(current)["latest_written"]
    raw = (job.SNAPSHOT_DIR / "latest.json").read_bytes()
    assert job.write_snapshot(current)["idempotent"]
    assert (job.SNAPSHOT_DIR / "latest.json").read_bytes() == raw
    old = dict(current, as_of="2026-09-14", snapshot_hash="old")
    assert not job.write_snapshot(old)["latest_written"]
    assert json.loads((job.SNAPSHOT_DIR / "latest.json").read_text())["as_of"] == "2026-10-06"
    assert not list(job.SNAPSHOT_DIR.glob("*.tmp"))


@pytest.mark.parametrize("updates,code,expected", [
    ({}, 0, True), ({"crawl_status": "FAILED"}, 0, False),
    ({"snapshot_status": "failed"}, 0, False), ({"dry_run": True}, 0, False),
    ({"snapshot_hash": None}, 0, False), ({}, 2, False),
])
def test_daily_failure_skips_long_horizon(updates, code, expected):
    summary = dict(snapshot_status="partial", crawl_status="OK", snapshot_hash="valid", dry_run=False)
    summary.update(updates)
    assert eligible(summary, code) is expected
