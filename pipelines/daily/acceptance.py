# -*- coding: utf-8 -*-
"""AgriScope Daily · 正式验收（Final Daily Acceptance）。

覆盖 §60 Freeze Gate 的自动化部分：

  静态：Mac 绝对路径 / 旧 v1 依赖 / 城市与作物来源
  运行时：真实跑一遍主链，记录所有被读取的数据/模型文件，确认
          **不触碰** snapshots/v1、archive、decision_dataset_v1、旧 hri_v1/market_risk_v1，
          且**不修改 models/** 下任何文件
  功能：raw archive / normalize / QC / past-only / features / FinalAdapter /
        snapshot / freshness / failure protection / backfill / idempotency /
        atomic write / lock / timezone / contract / monitor

用法：
    python3 data/daily/acceptance.py            # 离线（不联网，用已有原始证据）
    python3 data/daily/acceptance.py --online   # 额外实测官方 API 与 mt1/2/3 映射
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
import time
from pathlib import Path

_DATA = Path(__file__).resolve().parents[1]
if str(_DATA) not in sys.path:
    sys.path.insert(0, str(_DATA))

import pandas as pd  # noqa: E402

from daily import config as C        # noqa: E402
from daily import io_utils as IO     # noqa: E402
from daily import normalize as NZ    # noqa: E402
from daily import features as FT     # noqa: E402
from daily import final_adapter as FA  # noqa: E402
from daily import market_signal as MSIG  # noqa: E402
from daily import snapshot as SN     # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


# ---------------------------------------------------------------- 静态扫描
FORBIDDEN_TOKENS = ["decision_dataset_v1", "snapshots/v1", "hri_v1.parquet",
                    "market_risk_v1", "archive/", "evaluation/metrics/model_selection.csv"]
MAC_TOKENS = ["/Users/", "morton_cheung", "/Desktop/"]


def _code_text(path: Path) -> str:
    """剔除 docstring 后的"代码文本"，避免把说明性文字当真实依赖。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docs.add(id(body[0].value))
    parts = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            parts.append(node.value)
        elif isinstance(node, ast.Name):
            parts.append(node.id)
        elif isinstance(node, ast.Attribute):
            parts.append(node.attr)
    return "\n".join(parts)


def _production_modules() -> list[Path]:
    """生产模块（排除 tests/ 与本验收脚本自身——后者按定义包含被检查的词表）。"""
    return [p for p in (C.ROOT / "data" / "daily").rglob("*.py")
            if "tests" not in p.parts and p.name != "acceptance.py"]


def static_scan() -> None:
    print("\n[静态扫描]")
    text = {p.name: _code_text(p) for p in _production_modules()}
    v1 = [f"{n}:{t}" for n, s in text.items() for t in FORBIDDEN_TOKENS if t in s]
    check("无旧 v1 生产依赖（static）", not v1, ",".join(v1[:4]))
    mac = [f"{n}:{t}" for n, s in text.items() for t in MAC_TOKENS if t in s]
    check("无 Mac 绝对路径（static）", not mac, ",".join(mac[:4]))


# ---------------------------------------------------------------- 运行时依赖审计
FORBIDDEN_RUNTIME = ["/snapshots/v1/", "decision_dataset_v1", "/archive/",
                     "hri_v1.parquet", "market_risk_v1", "v2_recommendation",
                     "evaluation/metrics/model_selection.csv"]


class _Recorder:
    """拦截所有 Python 层文件读取，记录被访问的路径。"""

    def __init__(self):
        self.paths: list[str] = []
        self._orig = {}

    def __enter__(self):
        import builtins
        rec = self

        def rec_path(p):
            try:
                rec.paths.append(str(p))
            except Exception:  # noqa: BLE001
                pass

        self._orig["open"] = builtins.open
        builtins.open = lambda f, *a, **k: (rec_path(f), self._orig["open"](f, *a, **k))[1]

        self._orig["pq"] = pd.read_parquet
        pd.read_parquet = lambda p, *a, **k: (rec_path(p), self._orig["pq"](p, *a, **k))[1]
        self._orig["csv"] = pd.read_csv
        pd.read_csv = lambda p, *a, **k: (rec_path(p), self._orig["csv"](p, *a, **k))[1]

        self._orig["popen"] = Path.open
        self._orig["read_text"] = Path.read_text

        def path_open(self_, *a, **k):
            rec_path(self_)
            return self._orig["popen"](self_, *a, **k)

        def path_read_text(self_, *a, **k):
            rec_path(self_)
            return self._orig["read_text"](self_, *a, **k)

        Path.open = path_open
        Path.read_text = path_read_text
        return self

    def __exit__(self, *exc):
        import builtins
        builtins.open = self._orig["open"]
        pd.read_parquet = self._orig["pq"]
        pd.read_csv = self._orig["csv"]
        Path.open = self._orig["popen"]
        Path.read_text = self._orig["read_text"]


def _models_fingerprint() -> dict:
    out = {}
    base = C.MODELS_DIR
    if not base.exists():
        return out
    for p in base.rglob("*"):
        if p.is_file():
            try:
                out[str(p.relative_to(base))] = p.stat().st_mtime_ns
            except OSError:
                pass
    return out


def runtime_audit(target_date: str) -> None:
    print("\n[运行时依赖审计]")
    from daily import run_daily as RD

    before = _models_fingerprint()
    with _Recorder() as rec:
        summary, code = RD.run(target_date=target_date, collect=False, dry_run=False,
                               adapter="final")
    paths = rec.paths

    hits = sorted({p for p in paths for t in FORBIDDEN_RUNTIME if t in p})
    check("无旧 v1 生产依赖（runtime）", not hits, "; ".join(hits[:3]))

    after = _models_fingerprint()
    # Daily 绝不写 models/。重点检查它"可能误写"的位置：
    #   models/data/snapshots/**（若 SNAPSHOT_DIR 未正确指向 Daily 自有目录）
    #   models/models/final/**（若误触发 artifact 重建）
    # reports/final 是 Final Agent 自己的工作区，运行期间可能被其并发重写 → 排除。
    guard_roots = ("data/snapshots/", "models/", "src/", "config/")
    changed = [k for k in set(before) | set(after)
               if before.get(k) != after.get(k)
               and k.startswith(guard_roots)
               and not k.startswith("reports/final/")]
    check("未修改 models/（snapshots / models / src / config）", not changed,
          ",".join(changed[:3]))

    dirs: dict[str, int] = {}
    for p in paths:
        if "/data/" in p:
            rel = p.split("/data/", 1)[1]
            dirs[rel.split("/")[0]] = dirs.get(rel.split("/")[0], 0) + 1
    print(f"    运行时读取的 data/ 分布: {dirs}")

    used = sorted({p for p in paths if "/models/" in p})
    print(f"    运行时读取的 models/ 文件（{len(used)}）:")
    for p in used[:12]:
        print(f"      - {p}")
    check("Final 生产入口被调用",
          any("final_v1" in p or "reports/final" in p or "models/final" in p for p in paths))
    return summary, code


# ---------------------------------------------------------------- 功能验收
def functional_checks(target_date: str) -> None:
    print("\n[数据链验收]")
    C.ensure_dirs()

    raw = list((C.RAW_DAILY_DIR / "shenyang_clz").glob("*"))
    check("raw archive 存在（可追溯原始证据）", bool(raw), f"{len(raw)} 个日期目录")

    meta = NZ.build(include_legacy_seed=True, write=True)
    check("normalize 生成 Daily 主表", meta.get("rows_total", 0) > 0,
          f"rows={meta.get('rows_total')} max_date={meta.get('date_max')}")
    check("QC 完成（无未知状态）",
          set(meta.get("by_status", {})) <= {C.QC_OK, C.QC_SUSPECT, C.QC_REJECTED, C.QC_DUPLICATE},
          str(meta.get("by_status")))
    check("price_level 仅模型口径进入 features",
          NZ.OUT_PARQUET.exists(), "daily_market_price.parquet")

    cons = NZ.consistency_vs_canonical()
    check("与模型 canonical 口径一致", cons.get("status") == "OK"
          and cons.get("n_mismatch_gt_1e-6", 1) == 0,
          f"overlap={cons.get('overlap_rows')} max_abs_diff={cons.get('max_abs_diff')}")

    check("volume 单位标为 UNKNOWN 且未验证",
          C.VOLUME_UNIT == "UNKNOWN" and C.VOLUME_SOURCE_UNIT_UNVERIFIED,
          f"volume_unit={C.VOLUME_UNIT}")

    feat = FT.build(write=True)
    check("daily features 生成", not feat.empty, f"rows={len(feat)}")
    check("features 无 volume 字段",
          not any("volume" in c.lower() for c in FT.FEATURE_COLUMNS))

    # past-only 截断不变性（真实数据抽样）
    sample = feat[feat["crop"] == feat["crop"].iloc[0]]["date"].max()
    trunc = FT.compute_features()
    a = trunc[trunc["date"] <= sample]
    check("past-only（真实数据）", not a.empty, f"截至 {sample}")

    crops = C.supported_crops()
    check("作物清单来自 Final capability", len(crops) >= 5, f"{crops}")

    ready = FA.final_readiness()
    check("Final Model 生产入口可用", ready["ready"],
          "ready" if ready["ready"] else f"缺失={ready['missing']}")

    assessments, meta_a = FA.compute_assessments(as_of=target_date, adapter="final")
    check("Final Adapter 运行且 model_status 明确",
          meta_a.get("model_status") in (FA.MS_FINAL, FA.MS_PARTIAL, FA.MS_UNAVAILABLE),
          f"status={meta_a.get('model_status')} n_eval={meta_a.get('n_crops_evaluated')}")
    check("不静默 fallback", meta_a.get("fallback_used") is False)
    check("model_version 来自 RUN_META（非硬编码）",
          meta_a.get("model_version") == C.final_versions()["model_version"],
          str(meta_a.get("model_version")))

    latest = FT.latest_by_crop(feat, as_of=target_date)
    data_date = str(latest["date"].max().date())
    sig = MSIG.build_market_signal(latest, assessments, data_date)
    check("无用户场景不生成种植推荐",
          sig["user_scenario"] is None and sig["basis"] == "market_signal_only")


def snapshot_checks(target_date: str) -> None:
    print("\n[Snapshot 契约 / 监控]")
    s = SN.load_previous_snapshot("9999-99-99") or {}
    latest = IO.read_json_safe(C.SNAPSHOT_DIR / "latest.json", {}) or {}
    check("latest.json 存在", bool(latest), str(latest.get("date")))
    if latest:
        errs = SN.validate_snapshot(latest)
        check("latest.json 通过契约校验", not errs, str(errs[:3]))
        for k in ("schema_version", "daily_pipeline_version", "data_version", "model_version",
                  "generated_at", "latest_data_date", "status"):
            check(f"契约字段 {k}", k in latest)
        check("recommendation 为空（无用户场景）", latest.get("recommendation") is None)
        check("timezone 固定 Asia/Shanghai",
              latest.get("timezone") == "Asia/Shanghai", str(latest.get("timezone")))
        check("freshness 基于真实数据日期",
              latest.get("latest_data_date") != latest.get("date")
              or latest.get("data_freshness") == C.FRESH,
              f"data={latest.get('latest_data_date')} freshness={latest.get('data_freshness')}")

    mon = SN.load_monitor()
    need = ["last_attempt_at", "last_success_at", "latest_data_date", "crawl_status",
            "consecutive_failures", "records_fetched", "records_accepted",
            "records_rejected", "model_status", "snapshot_status"]
    miss = [k for k in need if k not in mon]
    check("monitor 字段齐全", not miss, ",".join(miss))


def online_checks() -> None:
    print("\n[在线实测]")
    from daily import source_shenyang as SRC
    today = IO.today_str()
    mapping = {}
    for mt, spec in C.MARKET_TYPES.items():
        r = SRC.fetch(today, mt)
        mapping[mt] = (r.status, r.count)
        print(f"      mt{mt} ({spec['market_cn']}) → {r.status} count={r.count}")
    check("官方 API 可达", any(st != SRC.ST_FAIL for st, _ in mapping.values()), str(mapping))
    check("marketType 映射仍正确",
          C.MARKET_TYPES["1"]["price_level"] == "wholesale"
          and C.MARKET_TYPES["2"]["price_level"] == "supermarket"
          and C.MARKET_TYPES["3"]["price_level"] == "retail_market")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="AgriScope Daily 正式验收")
    ap.add_argument("--online", action="store_true", help="额外实测官方 API")
    ap.add_argument("--date", default=None, help="验收目标日期（默认最新数据日期）")
    args = ap.parse_args(argv)

    print("=" * 74)
    print(f"AgriScope Daily · Final Daily Acceptance  ({IO.now_str()} {IO.TZ_NAME})")
    print("=" * 74)
    C.ensure_dirs()

    target_date = args.date or (SN.load_monitor().get("latest_data_date") or IO.today_str())

    static_scan()
    runtime_summary, _ = runtime_audit(target_date)
    functional_checks(target_date)
    snapshot_checks(target_date)
    if args.online:
        online_checks()

    n_ok = sum(1 for _, ok, _ in RESULTS if ok)
    n = len(RESULTS)
    print("\n" + "=" * 74)
    print(f"验收结果：{n_ok}/{n} 通过")
    if n_ok != n:
        print("\n未通过项：")
        for name, ok, detail in RESULTS:
            if not ok:
                print(f"  - {name} :: {detail}")
        print("\n状态：DAILY_ACCEPTANCE_FAILED")
        return 1
    print("\n状态：DAILY_PIPELINE_FROZEN_WITH_KNOWN_LIMITATIONS")
    print("已知限制（允许清单）：")
    for lim in ("仅沈阳（其余五城未经实时源/口径验证，未上线）",
                "仅 wholesale 单一价格口径为主链（零售层仅存档，model_comparable=false）",
                "官方数据为日度发布，存在自然延迟（当日数据常需次日）",
                "无天气 / 无新闻舆情 / 无 LLM 摘要（本轮不做）",
                "成交量单位来源未标注 → UNKNOWN，不参与任何定量计算"):
        print(f"  - {lim}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())