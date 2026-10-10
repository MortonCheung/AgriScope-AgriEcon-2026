# -*- coding: utf-8 -*-
"""AgriScope Daily 测试（封版版）。

覆盖：
  单位换算 / QC（空、负价、未知单位、重复、异常跳变、旧页面、缺失作物）/
  特征 past-only 无未来泄漏 / 抓取（正常、空页、网络错误、结构变化 fail-loud）/
  Freshness / volume 单位 UNKNOWN / Final capability 与非静默 fallback /
  market signal（无用户场景不造假推荐）/ 原子写入 / 进程锁 / 时区 /
  Snapshot 契约校验 / 端到端 Case A-J（tmp root，离线）。
"""
from __future__ import annotations

import builtins
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import daily.config as C
import daily.features as FT
import daily.final_adapter as FA
import daily.io_utils as IO
import daily.market_signal as MSIG
import daily.normalize as NZ
import daily.snapshot as SN
import daily.source_shenyang as SRC

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RUN_DAILY = ROOT / "AgriScope" / "pipelines" / "daily" / "run_daily.py"
CROPS = ["土豆", "黄瓜", "西红柿", "青椒"]


# ================================================================ 单位换算
@pytest.mark.parametrize("price,unit,expected", [
    (2.0, "元/500g", 4.0), (2.0, "元/500克", 4.0), (3.0, "元/斤", 6.0),
    (5.0, "元/公斤", 5.0), (5.0, "元/kg", 5.0),
    (5.0, "元/500ml", None), (5.0, "", None),
])
def test_unit_conversion(price, unit, expected):
    assert NZ._per_kg(price, unit) == expected


def test_published_at_uses_beijing_time():
    # 2026-09-21 00:00 (UTC+8) == 1789920000000 ms
    assert NZ._published_at(1789920000000).startswith("2026-09-21")
    assert NZ._published_at("bad") is None


# ================================================================ 时区
def test_timezone_fixed_asia_shanghai():
    assert IO.TZ_NAME == "Asia/Shanghai"
    assert IO.now_tz().utcoffset().total_seconds() == 8 * 3600
    # 业务日期来自北京时间
    assert len(IO.today_str()) == 10


# ================================================================ 原子写入
def test_atomic_write_json(tmp_path):
    p = tmp_path / "a.json"
    IO.atomic_write_json(p, {"k": 1})
    assert json.loads(p.read_text(encoding="utf-8"))["k"] == 1
    IO.atomic_write_json(p, {"k": 2})
    assert json.loads(p.read_text(encoding="utf-8"))["k"] == 2
    # 不残留临时文件
    assert not list(tmp_path.glob(".*tmp*"))


def test_atomic_write_parquet(tmp_path):
    p = tmp_path / "a.parquet"
    IO.atomic_write_parquet(pd.DataFrame({"x": [1, 2]}), p)
    IO.atomic_write_parquet(pd.DataFrame({"x": [3]}), p)
    assert pd.read_parquet(p)["x"].tolist() == [3]
    assert not list(tmp_path.glob(".*tmp*"))


def test_atomic_write_survives_reader_on_old_content(tmp_path):
    """写入过程中不出现"半个文件"：先写临时文件再替换，旧文件始终可读。"""
    p = tmp_path / "big.parquet"
    IO.atomic_write_parquet(pd.DataFrame({"x": range(100)}), p)
    before = len(pd.read_parquet(p))
    IO.atomic_write_parquet(pd.DataFrame({"x": range(500)}), p)
    assert before == 100 and len(pd.read_parquet(p)) == 500


# ================================================================ 进程锁
def test_process_lock_mutual_exclusion(tmp_path):
    lock = tmp_path / "x.lock"
    with IO.ProcessLock(lock):
        assert lock.exists()
        with pytest.raises(RuntimeError):
            with IO.ProcessLock(lock, stale_after=3600):
                pass
    assert not lock.exists()          # 释放后可再次获取
    with IO.ProcessLock(lock):
        pass


def test_process_lock_stale_self_heal(tmp_path):
    lock = tmp_path / "s.lock"
    lock.write_text("stale")
    old = 0
    os.utime(lock, (old, old))         # 极旧 → 应被清理
    with IO.ProcessLock(lock, stale_after=1):
        assert lock.exists()


# ================================================================ QC
def _row(**kw):
    d = kw.get("date", "2026-10-01")
    base = dict(date=d, city="沈阳", market="批发价格", crop_raw="土豆",
                price=1.0, unit_raw="元/500g", unit_standard="元/公斤", price_per_kg=2.0,
                price_level="wholesale", model_comparable=True, volume="9",
                volume_unit=C.VOLUME_UNIT, volume_unit_unverified=True,
                source_id="S", source_name="n", source_url="u", published_at=f"{d} 00:00:00",
                crawl_time="c", raw_file="r", parser_version="p")
    base.update(kw)
    return base


def test_qc_clean_row_ok():
    out = NZ.run_qc(pd.DataFrame([_row()]), CROPS)
    assert out.iloc[0]["quality_status"] == C.QC_OK
    assert out.iloc[0]["crop_standard"] == "土豆"


@pytest.mark.parametrize("field,value,expect", [
    ("price", -1.0, C.QC_REJECTED),
    ("price", float("nan"), C.QC_REJECTED),
    ("price_per_kg", None, C.QC_REJECTED),
    ("crop_raw", "", C.QC_REJECTED),
    ("price_level", "bogus", C.QC_REJECTED),
    ("published_at", "2026-09-01 00:00:00", C.QC_REJECTED),   # 旧页面
    ("crop_raw", "外星菜", C.QC_SUSPECT),
])
def test_qc_bad_rows(field, value, expect):
    out = NZ.run_qc(pd.DataFrame([_row(**{field: value})]), CROPS)
    assert out.iloc[0]["quality_status"] == expect


def test_qc_duplicate_marked():
    out = NZ.run_qc(pd.DataFrame([_row(), _row()]), CROPS)
    assert (out["quality_status"] == C.QC_DUPLICATE).sum() == 1


@pytest.mark.parametrize("p2", [40.0, 0.0, -5.0, 300.0])
def test_qc_abnormal_price_suspect_not_deleted(p2):
    df = pd.DataFrame([_row(date="2026-10-01", price=1.0, price_per_kg=2.0),
                       _row(date="2026-10-02", price=p2, price_per_kg=p2)])
    out = NZ.run_qc(df, CROPS)
    assert len(out) == 2                       # 不删除
    second = out[out["date"] == "2026-10-02"].iloc[0]
    assert second["quality_status"] in (C.QC_SUSPECT, C.QC_REJECTED)


# ================================================================ volume 语义
def test_volume_unit_is_unknown_not_inferred():
    assert C.VOLUME_UNIT == "UNKNOWN"
    assert C.VOLUME_SOURCE_UNIT_UNVERIFIED is True
    # 未经验证的单位不得用于量级推断
    assert "吨" not in C.VOLUME_UNIT


def test_volume_not_used_by_features():
    """features 只使用价格列，volume 不进入任何特征。"""
    cols = set(FT.FEATURE_COLUMNS)
    assert not any("volume" in c.lower() for c in cols)


# ================================================================ 特征 / 无泄漏
def _series(crop, dates, prices):
    return pd.DataFrame({"date": pd.to_datetime(dates), "crop": crop,
                         "price_per_kg": prices, "source": "S"})


def test_asof_change_past_only():
    dates = pd.date_range("2026-01-01", periods=40, freq="D")
    s = _series("土豆", dates, np.arange(1.0, 41.0)).reset_index(drop=True)
    chg7 = FT._asof_change(s, 7)
    assert chg7[20] == pytest.approx(21 / 14 - 1)
    assert np.isnan(chg7[0])


def test_features_no_future_leakage_all_fields():
    dates = pd.date_range("2025-01-01", periods=200, freq="D")
    rng = np.random.default_rng(0)
    prices = 2 + np.cumsum(rng.normal(0, 0.05, 200))
    full = FT.compute_features(_series("黄瓜", dates, prices))
    cut = FT.compute_features(_series("黄瓜", dates[:150], prices[:150]))
    a, b = full.head(150).reset_index(drop=True), cut.reset_index(drop=True)
    for col in ["change_1d", "change_7d", "change_30d", "historical_percentile",
                "rolling_volatility", "recent_runup_14d", "consecutive_rise_days"]:
        assert np.allclose(a[col].to_numpy(float), b[col].to_numpy(float),
                           equal_nan=True), f"{col} 受未来数据影响"


def test_historical_percentile_strictly_expanding():
    """过去某日分位不得使用其后数据：逐点等于 expanding rank。"""
    dates = pd.date_range("2026-01-01", periods=80, freq="D")
    prices = np.linspace(1, 8, 80)
    f = FT.compute_features(_series("土豆", dates, prices))
    s = pd.Series(prices)
    expected = s.expanding(min_periods=30).rank(pct=True)
    assert np.allclose(f["historical_percentile"].to_numpy(float),
                       expected.to_numpy(float), equal_nan=True)


def test_consecutive_rise_days():
    dates = pd.date_range("2026-01-01", periods=6, freq="D")
    f = FT.compute_features(_series("土豆", dates, [1, 2, 3, 3, 4, 5]))
    assert list(f["consecutive_rise_days"]) == [0, 1, 2, 0, 1, 2]


# ================================================================ 抓取 / fail loud
class _FakeResp:
    def __init__(self, payload): self._p = payload
    def read(self): return json.dumps(self._p).encode()
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_fetch_ok(monkeypatch):
    payload = {"code": 0, "count": 10,
               "data": [{"productName": "土豆", "price": "1.0", "unit": "元/500g"}] * 10}
    monkeypatch.setattr(SRC.urllib.request, "urlopen", lambda *a, **k: _FakeResp(payload))
    r = SRC.fetch("2026-10-01", "1")
    assert r.status == SRC.ST_OK and r.count == 10 and r.schema_ok


def test_fetch_empty_page(monkeypatch):
    monkeypatch.setattr(SRC.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResp({"code": 0, "count": 0, "data": []}))
    r = SRC.fetch("2026-10-01", "1")
    assert r.status == SRC.ST_EMPTY and r.schema_ok


def test_fetch_network_error(monkeypatch):
    def boom(*a, **k): raise OSError("connection refused")
    monkeypatch.setattr(SRC.urllib.request, "urlopen", boom)
    monkeypatch.setattr(SRC.time, "sleep", lambda *_: None)
    r = SRC.fetch("2026-10-01", "1", retries=2)
    assert r.status == SRC.ST_FAIL and "connection refused" in r.error


def test_fetch_missing_data_field_is_schema_changed(monkeypatch):
    """API 结构变化（缺 data 字段）→ fail loud，不静默当作成功。"""
    monkeypatch.setattr(SRC.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResp({"code": 0, "rows": []}))
    r = SRC.fetch("2026-10-01", "1")
    assert r.status == SRC.ST_EMPTY and r.schema_ok is False
    assert SRC.SCHEMA_CHANGED in r.schema_note


def test_fetch_wrong_wholesale_count_is_schema_changed(monkeypatch):
    """批发口径期望 10 种作物，突然得到 2 种 → SOURCE_SCHEMA_CHANGED。"""
    payload = {"code": 0, "count": 2,
               "data": [{"productName": "土豆", "price": "1.0", "unit": "元/500g"}] * 2}
    monkeypatch.setattr(SRC.urllib.request, "urlopen", lambda *a, **k: _FakeResp(payload))
    r = SRC.fetch("2026-10-01", "1")
    assert r.schema_ok is False and SRC.SCHEMA_CHANGED in r.schema_note


def test_fetch_missing_required_field_is_schema_changed(monkeypatch):
    payload = {"code": 0, "count": 10, "data": [{"productName": "土豆"}] * 10}
    monkeypatch.setattr(SRC.urllib.request, "urlopen", lambda *a, **k: _FakeResp(payload))
    r = SRC.fetch("2026-10-01", "1")
    assert r.schema_ok is False


def test_evaluate_crawl_all_past_empty_is_schema_changed():
    from daily.run_daily import _evaluate_crawl
    res = [SRC.RawResult(date="2026-10-01", market_type="1",
                         url="u", status=SRC.ST_EMPTY, count=0),
           SRC.RawResult(date="2026-10-03", market_type="1",
                         url="u", status=SRC.ST_EMPTY, count=0)]
    status, schemes = _evaluate_crawl(res, "2026-10-07")
    assert status == "PARTIAL" and any(SRC.SCHEMA_CHANGED in s for s in schemes)


def test_evaluate_crawl_all_failed():
    from daily.run_daily import _evaluate_crawl
    res = [SRC.RawResult(date="2026-10-07", market_type="1", url="u", status=SRC.ST_FAIL)]
    status, _ = _evaluate_crawl(res, "2026-10-07")
    assert status == "FAILED"


# ================================================================ Freshness / 等级
@pytest.mark.parametrize("age,expect", [(0, C.FRESH), (1, C.DELAYED), (2, C.DELAYED),
                                        (3, C.STALE), (7, C.STALE), (8, C.MISSING),
                                        (None, C.MISSING)])
def test_freshness(age, expect):
    assert C.freshness_for_age(age) == expect


@pytest.mark.parametrize("pct,expect", [(95, "VERY_HIGH"), (80, "HIGH"), (60, "WATCH"),
                                        (10, "NORMAL"), (None, "UNKNOWN")])
def test_level_mapping(pct, expect):
    assert FA._pct_level(pct) == expect


def test_worse_level():
    assert FA.worse("WATCH", "VERY_HIGH") == "VERY_HIGH"
    assert FA.worse("UNKNOWN", "NORMAL") == "NORMAL"
    assert FA.worse("UNKNOWN", "UNKNOWN") == "UNKNOWN"


# ================================================================ Final capability / fallback
def test_supported_crops_from_final_capability_or_fallback():
    crops = C.supported_crops("沈阳")
    assert "黄瓜" in crops and len(crops) >= 5


def test_final_readiness_reports_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(C, "FINAL_RUN_META", tmp_path / "nope.json")
    r = FA.final_readiness()
    assert r["ready"] is False and "run_meta" in r["missing"]


def test_model_status_constants_four_kinds():
    assert {FA.MS_FINAL, FA.MS_PARTIAL, FA.MS_UNAVAILABLE, FA.MS_LEGACY} == {
        "FINAL", "PARTIAL", "MODEL_UNAVAILABLE", "LEGACY_FALLBACK"}


def test_compute_assessments_does_not_silently_fallback(monkeypatch):
    """Final 不可用（readiness 失败）→ MODEL_UNAVAILABLE，绝不静默返回 legacy。"""
    monkeypatch.setattr(FA, "final_readiness",
                        lambda: {"ready": False, "missing": ["price_model_selection"],
                                 "has_model_artifacts": False, "note": "x"})
    states, meta = FA.compute_assessments("沈阳", adapter="final")
    assert states == {} and meta["model_status"] == FA.MS_UNAVAILABLE
    assert meta["fallback_used"] is False


def test_legacy_adapter_is_explicitly_labelled():
    _, meta = FA.compute_assessments("沈阳", adapter="legacy")
    assert meta["model_status"] == FA.MS_LEGACY and meta["fallback_used"] is True
    assert "LEGACY_FALLBACK" in meta["warning"]


@pytest.mark.parametrize("n_ok,n_total,art,expect", [
    (10, 10, True, "FINAL"),
    (10, 10, False, "PARTIAL"),     # ML 点预测缺失 → 降级，不假装 FINAL
    (7, 10, True, "PARTIAL"),        # 部分作物不可评估
    (0, 10, True, "PARTIAL"),
])
def test_overall_status_never_overstates(n_ok, n_total, art, expect):
    assert FA._overall_status(n_ok, n_total, art) == expect


def test_readiness_reports_artifact_gap(monkeypatch, tmp_path):
    """选型表等齐备但 .pkl 缺失 → artifacts_ready=False 且给出降级说明。"""
    monkeypatch.setattr(C, "FINAL_MODELS_DIR", tmp_path / "empty_models")
    r = FA.final_readiness()
    assert r["artifacts_ready"] is False
    assert "pkl" in r["note"] or "PARTIAL" in r["note"]


# ================================================================ 无用户场景 → 不造假推荐
def test_market_signal_no_user_scenario():
    feat = pd.DataFrame([{
        "crop": "黄瓜", "date": pd.Timestamp("2026-10-06"), "latest_price": 3.4,
        "change_1d": 0.01, "change_7d": 0.02, "change_30d": -0.03,
        "historical_percentile": 0.4, "rolling_volatility": 0.05,
        "recent_runup_14d": 0.1, "consecutive_rise_days": 1,
        "n_obs_to_date": 10, "source": "S"}])
    sig = MSIG.build_market_signal(feat, {}, "2026-10-06")
    assert sig["basis"] == "market_signal_only"
    assert sig["user_scenario"] is None
    assert "不输出种植推荐" in sig["note"] or "不输出种植推荐或排名" in sig["note"]
    assert "rank" not in sig["crops"][0]


def test_market_signal_change_detects_crossing():
    prev = {"crops": [{"crop": "黄瓜", "daily_signal": "NORMAL", "data_date": "2026-10-05",
                       "price": 3.0, "hri": 40.0, "market_risk": 30.0}]}
    cur = {"crops": [{"crop": "黄瓜", "daily_signal": "HIGH", "data_date": "2026-10-06",
                      "price": 3.6, "hri": 55.0, "market_risk": 62.0}]}
    ch = MSIG.build_change(prev, cur)
    assert ch[0]["signal_crossed_up"] is True
    assert ch[0]["hri_change"] == 15.0
    assert ch[0]["changed"] is True


# ================================================================ Snapshot 契约
def test_validate_snapshot_detects_missing_fields():
    errs = SN.validate_snapshot({"date": "2026-10-01"})
    assert errs and any("schema_version" in e for e in errs)


def test_validate_snapshot_ok_minimal():
    snap = {"schema_version": "1", "daily_pipeline_version": "1", "data_version": "d",
            "model_version": "final_v1", "generated_at": "t", "date": "2026-10-06",
            "city": "沈阳", "status": "partial", "latest_data_date": "2026-10-06",
            "data_freshness": "FRESH", "crawl_status": "OK", "sources": [],
            "crops": [{"crop": "黄瓜", "latest_price": 3.4, "change_1d": 0.0,
                       "change_7d": 0.0, "change_30d": 0.0, "historical_percentile": 0.4,
                       "hri": 40.0, "market_risk": 30.0, "daily_signal": "NORMAL",
                       "confidence": 70.0, "warnings": [], "data_freshness": "FRESH",
                       "source": "S"}]}
    assert SN.validate_snapshot(snap) == []


def test_validate_snapshot_bad_status_and_signal():
    snap = {"schema_version": "1", "daily_pipeline_version": "1", "data_version": "d",
            "model_version": "m", "generated_at": "t", "date": "d", "city": "沈阳",
            "status": "weird", "latest_data_date": None, "data_freshness": "NOPE",
            "crawl_status": "OK", "sources": [],
            "crops": [{"crop": "c", "latest_price": 1, "change_1d": 0, "change_7d": 0,
                       "change_30d": 0, "historical_percentile": 0, "hri": 1,
                       "market_risk": 1, "daily_signal": "PURPLE", "confidence": 1,
                       "warnings": [], "data_freshness": "FRESH", "source": "s"}]}
    errs = SN.validate_snapshot(snap)
    assert any("status" in e for e in errs)
    assert any("data_freshness" in e for e in errs)
    assert any("daily_signal" in e for e in errs)


# ================================================================ 静态依赖扫描
FORBIDDEN_TOKENS = ["decision_dataset_v1", "snapshots/v1", "hri_v1.parquet",
                    "market_risk_v1", "archive/", "evaluation/metrics/model_selection.csv"]


def _code_text(path: Path) -> str:
    """只取"代码文本"：剔除 docstring 与注释，避免把说明性文字当作真实依赖。"""
    import ast
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docs.add(id(body[0].value))
    parts = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docs:
            parts.append(node.value)
        elif isinstance(node, ast.Name):
            parts.append(node.id)
        elif isinstance(node, ast.Attribute):
            parts.append(node.attr)
    return "\n".join(parts)


def _production_modules():
    """生产模块（排除 tests/ 与验收脚本自身——后者按定义含被检查词表）。"""
    mod_dir = ROOT / "AgriScope" / "pipelines" / "daily"
    return [p for p in mod_dir.rglob("*.py")
            if "tests" not in p.parts and p.name != "acceptance.py"]


def test_static_no_old_v1_dependency():
    hits = []
    for p in _production_modules():
        text = _code_text(p)
        for tok in FORBIDDEN_TOKENS:
            if tok in text:
                hits.append(f"{p.name}:{tok}")
    assert hits == [], f"Daily 生产代码仍引用旧 v1 产物: {hits}"


def test_static_no_mac_absolute_paths():
    hits = []
    for p in _production_modules():
        text = _code_text(p)
        for tok in ("/Users/", "morton_cheung", "/Desktop/"):
            if tok in text:
                hits.append(f"{p.name}:{tok}")
    assert hits == [], f"Daily 生产代码含 Mac 绝对路径: {hits}"


# ================================================================ 端到端（tmp root，离线）
def _seed_raw(root: Path, dates, crops=("土豆", "黄瓜"), count=None):
    n = len(crops)
    for d in dates:
        day = root / "data" / "raw" / "prices" / "shenyang_clz"
        day.mkdir(parents=True, exist_ok=True)
        data = [{"productName": c, "price": "1.00", "unit": "元/500g", "grade": "新鲜一级",
                 "volume": "10", "dates": int(pd.Timestamp(d).timestamp() * 1000)} for c in crops]
        (day / f"{d}_mt1.json").write_text(
            json.dumps({"code": 0, "count": n, "data": data}), encoding="utf-8")


def _run(root: Path, *args, env_extra=None):
    env = dict(os.environ, PROJECT_ROOT=str(root))
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, str(RUN_DAILY), *args], cwd=str(ROOT / "AgriScope"),
                          env=env, capture_output=True, text=True)


def _snap(root: Path, d: str):
    return json.loads((root / "data" / "processed" / "daily" / "snapshots"
                       / "daily" / f"{d}.json").read_text(encoding="utf-8"))


def _latest(root: Path):
    return json.loads((root / "data" / "processed" / "daily" / "snapshots"
                       / "latest.json").read_text(encoding="utf-8"))


def test_case_A_fresh_data_complete(tmp_path):
    """Case A：官方有当天数据 → FRESH。"""
    dates = [str(d.date()) for d in pd.date_range("2026-01-01", periods=40, freq="D")]
    _seed_raw(tmp_path, dates)
    t = dates[-1]
    assert _run(tmp_path, "--date", t, "--no-collect").returncode == 0
    s = _snap(tmp_path, t)
    assert s["latest_data_date"] == t and s["data_freshness"] == C.FRESH
    assert s["crops"][0]["data_freshness"] == C.FRESH


def test_case_B_only_yesterday_data(tmp_path):
    """Case B：只有昨天数据 → DELAYED，且不写成今天。"""
    dates = [str(d.date()) for d in pd.date_range("2026-01-01", periods=30, freq="D")]
    _seed_raw(tmp_path, dates)
    last = dates[-1]
    t = (pd.Timestamp(last) + pd.Timedelta(days=1)).date().isoformat()
    assert _run(tmp_path, "--date", t, "--no-collect").returncode == 0
    s = _snap(tmp_path, t)
    assert s["latest_data_date"] == last
    assert s["data_freshness"] == C.DELAYED and s["status"] == "partial"
    assert any("不得标为当日价格" in n for n in s["notes"])


def test_case_C_api_down_no_placeholder(tmp_path):
    """Case C：API 挂了 → 不得用昨日价格填今天；latest.json 不被破坏。"""
    dates = [str(d.date()) for d in pd.date_range("2026-01-01", periods=30, freq="D")]
    _seed_raw(tmp_path, dates)
    good = dates[-2]
    assert _run(tmp_path, "--date", good, "--no-collect").returncode in (0, 2)
    before = _latest(tmp_path)
    bad = dates[-1]
    r = _run(tmp_path, "--date", bad, "--force", "--markets", "1",
             env_extra={"AGRISCOPE_SY_API": "http://127.0.0.1:9/x",
                        "AGRISCOPE_HTTP_RETRIES": "1", "AGRISCOPE_HTTP_TIMEOUT": "2"})
    assert r.returncode == 2
    s = _snap(tmp_path, bad)
    assert s["crawl_status"] == "FAILED" and s["status"] == "failed"
    assert _latest(tmp_path)["date"] == before["date"]     # latest 未被污染
    mon = json.loads((tmp_path / "data" / "processed" / "daily" / "monitor"
                      / "status.json").read_text(encoding="utf-8"))
    assert mon["consecutive_failures"] >= 1 and mon["last_failure_reason"]


def test_case_E_missing_crop_still_renders(tmp_path):
    """Case E：某作物缺失 → 仍生成快照，不崩。"""
    dates = [str(d.date()) for d in pd.date_range("2026-01-01", periods=30, freq="D")]
    _seed_raw(tmp_path, dates, crops=("土豆",))
    t = dates[-1]
    assert _run(tmp_path, "--date", t, "--no-collect").returncode == 0
    s = _snap(tmp_path, t)
    assert [c["crop"] for c in s["crops"]] == ["土豆"]


def test_case_F_abnormal_price_excluded_from_signal(tmp_path):
    """Case F：异常价格标 SUSPECT 并排除出信号，但原始证据保留。"""
    dates = [str(d.date()) for d in pd.date_range("2026-01-01", periods=30, freq="D")]
    _seed_raw(tmp_path, dates, crops=("土豆",))
    # 最后一天注入 100x 跳变
    last = dates[-1]
    day = tmp_path / "data" / "raw" / "prices" / "shenyang_clz"
    (day / f"{last}_mt1.json").write_text(json.dumps(
        {"code": 0, "count": 1, "data": [{"productName": "土豆", "price": "100.00",
                                          "unit": "元/500g", "volume": "1",
                                          "dates": int(pd.Timestamp(last).timestamp() * 1000)}]}),
        encoding="utf-8")
    assert _run(tmp_path, "--date", last, "--no-collect").returncode == 0
    qc = pd.read_csv(tmp_path / "data" / "processed" / "daily" / "qc_daily.csv")
    assert (qc["quality_status"] == "SUSPECT").any()
    feat = pd.read_parquet(tmp_path / "data" / "processed" / "daily" / "features_daily.parquet")
    assert feat["latest_price"].max() < 10      # SUSPECT 未进入特征


def test_case_G_final_unavailable_partial(tmp_path):
    """Case G：Final 不可用 → PARTIAL/MODEL_UNAVAILABLE，价格仍真实，不静默 fallback。"""
    dates = [str(d.date()) for d in pd.date_range("2026-01-01", periods=30, freq="D")]
    _seed_raw(tmp_path, dates)
    t = dates[-1]
    assert _run(tmp_path, "--date", t, "--no-collect").returncode in (0, 2)
    s = _snap(tmp_path, t)
    assert s["model"]["model_status"] in ("MODEL_UNAVAILABLE", "PARTIAL")
    assert s["model"]["fallback_used"] is False
    assert s["status"] != "complete"
    assert all(c["latest_price"] is not None for c in s["crops"])   # 价格仍真实
    assert s["recommendation"] is None


def test_case_H_idempotent(tmp_path):
    """Case H：重复执行 → 业务结果一致。"""
    dates = [str(d.date()) for d in pd.date_range("2026-01-01", periods=40, freq="D")]
    _seed_raw(tmp_path, dates)
    t = dates[-1]
    assert _run(tmp_path, "--date", t, "--no-collect").returncode in (0, 2)
    s1 = _snap(tmp_path, t)
    assert _run(tmp_path, "--date", t, "--no-collect").returncode in (0, 2)
    s2 = _snap(tmp_path, t)
    if s1["snapshot_hash"] != s2["snapshot_hash"]:
        a = {k: v for k, v in s1.items()
             if k not in ("generated_at", "updated_at", "monitor", "snapshot_hash")}
        b = {k: v for k, v in s2.items()
             if k not in ("generated_at", "updated_at", "monitor", "snapshot_hash")}
        diff = [k for k in set(a) | set(b) if a.get(k) != b.get(k)]
        raise AssertionError(f"幂等失败，差异字段: {diff} :: "
                             + " | ".join(f"{k}: {a.get(k)!r} != {b.get(k)!r}"
                                          for k in sorted(diff)[:5]))
    assert s2["data_version"] == s1["data_version"]


# ================================================================ 契约校验守卫
def test_invalid_contract_does_not_replace_latest(tmp_path, monkeypatch):
    """非法 Snapshot → 抛 SnapshotContractError，且不替换 latest.json（§50）。"""
    root = tmp_path
    (root / "data" / "processed" / "daily" / "snapshots").mkdir(parents=True)
    latest = root / "data" / "processed" / "daily" / "snapshots" / "latest.json"
    latest.write_text(json.dumps({"date": "2026-01-01", "sentinel": True}), encoding="utf-8")
    before = latest.read_text(encoding="utf-8")

    import daily.snapshot as S
    monkeypatch.setattr(S, "SNAPSHOT_DAILY_DIR", root / "data" / "processed" / "daily" / "snapshots" / "daily")
    monkeypatch.setattr(S, "LATEST_JSON", latest)
    monkeypatch.setattr(S, "C", C)
    monkeypatch.setattr(C, "SNAPSHOT_DIR", root / "data" / "processed" / "daily" / "snapshots")
    monkeypatch.setattr(C, "PROCESSED_DAILY_DIR", root / "data" / "processed" / "daily")
    monkeypatch.setattr(C, "MONITOR_JSON", root / "data" / "processed" / "daily" / "monitor" / "status.json")
    monkeypatch.setattr(S, "validate_snapshot", lambda snap: ["forced contract error"])
    import daily.features as F
    monkeypatch.setattr(F, "build", lambda write=True: pd.DataFrame())
    with pytest.raises(S.SnapshotContractError):
        S.build(target_date="2026-01-02", crawl_status="OK", write=True)
    assert latest.read_text(encoding="utf-8") == before


def test_no_junk_versioned_snapshot_files(tmp_path):
    """历史快照按日期命名，不生成 -v2 / final2 等垃圾版本（§22）。"""
    dates = [str(d.date()) for d in pd.date_range("2026-01-01", periods=30, freq="D")]
    _seed_raw(tmp_path, dates)
    t = dates[-1]
    assert _run(tmp_path, "--date", t, "--no-collect").returncode in (0, 2)
    assert _run(tmp_path, "--date", t, "--no-collect").returncode in (0, 2)
    files = sorted(p.name for p in (tmp_path / "data" / "processed" / "daily"
                                    / "snapshots" / "daily").glob("*.json"))
    assert files == [f"{t}.json"], files


def test_raw_attempts_preserved_on_recrawl(tmp_path):
    """同日重复抓取：旧响应保留在 attempts/，当前 mt*.json 为本次使用（§23）。"""
    import daily.source_shenyang as SRCm
    monkeypatch_dirs = None
    day = tmp_path / "data" / "raw" / "daily" / "shenyang_clz" / "2026-01-01"
    day.mkdir(parents=True)
    r1 = SRCm.RawResult(date="2026-01-01", market_type="1", url="u", status=SRCm.ST_OK,
                        count=1, records=[{"productName": "土豆", "price": "1.0",
                                           "unit": "元/500g"}], crawl_time="2026-01-01 20:30:00")
    old_root = SRCm.C.RAW_DAILY_DIR
    old_root2 = SRCm.C.ROOT
    SRCm.C.RAW_DAILY_DIR = tmp_path / "data" / "raw" / "daily"
    SRCm.C.ROOT = tmp_path
    try:
        SRCm._archive(r1)
        r2 = SRCm.RawResult(date="2026-01-01", market_type="1", url="u", status=SRCm.ST_OK,
                            count=1, records=[{"productName": "土豆", "price": "9.9",
                                               "unit": "元/500g"}],
                            crawl_time="2026-01-01 23:30:00")
        SRCm._archive(r2)
    finally:
        SRCm.C.RAW_DAILY_DIR = old_root
        SRCm.C.ROOT = old_root2
    attempts = list((day / "attempts").glob("*.json"))
    assert len(attempts) == 1                      # 旧响应被保留
    cur = json.loads((day / "mt1.json").read_text(encoding="utf-8"))
    assert cur["data"][0]["price"] == "9.9"        # 当前 = 本次使用
    assert json.loads(attempts[0].read_text(encoding="utf-8"))["data"][0]["price"] == "1.0"


def test_case_I_backfill_no_rollback(tmp_path):
    """Case I：backfill 旧日期不回退 latest.json，历史快照保留。"""
    dates = [str(d.date()) for d in pd.date_range("2026-01-01", periods=40, freq="D")]
    _seed_raw(tmp_path, dates)
    newer, older = dates[-1], dates[-5]
    assert _run(tmp_path, "--date", newer, "--no-collect").returncode in (0, 2)
    assert _run(tmp_path, "--date", older, "--no-collect").returncode in (0, 2)
    assert _latest(tmp_path)["date"] == newer
    assert (tmp_path / "data" / "processed" / "daily" / "snapshots"
            / "daily" / f"{older}.json").exists()


def test_case_J_concurrent_execution_locked(tmp_path):
    """Case J：并发执行 → 第二个进程被锁拒绝（退出码 4）。"""
    dates = [str(d.date()) for d in pd.date_range("2026-01-01", periods=30, freq="D")]
    _seed_raw(tmp_path, dates)
    t = dates[-1]
    lockfile = tmp_path / "data" / "processed" / "daily" / ".run.lock"
    lockfile.parent.mkdir(parents=True, exist_ok=True)
    lockfile.write_text('{"pid": 1}')          # 模拟另一个任务持有锁
    r = _run(tmp_path, "--date", t, "--no-collect")
    assert r.returncode == 4
    assert "另一个 Daily 任务正在运行" in (r.stdout + r.stderr)


def test_case_D_schema_changed_fails_loud(tmp_path):
    """Case D：API 结构变化 → SOURCE_SCHEMA_CHANGED，不静默成功。"""
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"code": 0, "rows": [{"x": 1}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        dates = [str(d.date()) for d in pd.date_range("2026-01-01", periods=3, freq="D")]
        _seed_raw(tmp_path, dates)
        t = dates[-1]
        r = _run(tmp_path, "--date", t, "--force", "--markets", "1",
                 env_extra={"AGRISCOPE_SY_API": f"http://127.0.0.1:{port}/api/showList",
                            "AGRISCOPE_HTTP_RETRIES": "1"})
        assert r.returncode in (0, 2)
        assert "SOURCE_SCHEMA_CHANGED" in (r.stdout + r.stderr)
    finally:
        srv.shutdown()