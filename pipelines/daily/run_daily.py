# -*- coding: utf-8 -*-
"""AgriScope Daily · 统一入口（纯命令行，适合服务器 / cron 运行）。

用法：
    python3 data/daily/run_daily.py                        # 采集今天 + 生成 Snapshot
    python3 data/daily/run_daily.py --date 2026-10-06      # backfill 指定日期
    python3 data/daily/run_daily.py --dry-run              # 只抓取/解析/QC，不写 Daily 数据
    python3 data/daily/run_daily.py --no-collect           # 只用已有原始证据重建
    python3 data/daily/run_daily.py --adapter legacy       # 显式使用旧信号（LEGACY_FALLBACK）

流水线：
    Scheduler → Collector → Raw Archive → Normalizer → QC
        → Daily Feature Builder → Final Model Adapter → Daily Snapshot

退出码（供 cron / systemd 判失败）：
    0  成功（status = complete / partial）
    2  抓取失败或无可用数据（status = failed）
    3  Snapshot 契约校验失败（不推进 latest.json）
    4  另一个 Daily 任务正在运行（进程锁）
    1  未预期异常
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

_DATA = Path(__file__).resolve().parents[1]
if str(_DATA) not in sys.path:
    sys.path.insert(0, str(_DATA))

from daily import config as C                      # noqa: E402
from daily import io_utils as IO                   # noqa: E402
from daily import source_shenyang as SRC           # noqa: E402
from daily import normalize as NZ                  # noqa: E402
from daily import features as FT                   # noqa: E402
from daily import final_adapter as FA              # noqa: E402
from daily import market_signal as MS              # noqa: E402
from daily import snapshot as SN                   # noqa: E402

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_FAILED = 2
EXIT_CONTRACT = 3
EXIT_LOCKED = 4


class Logger:
    """按日日志：同一业务日多次运行追加，不无限增长单文件。"""

    def __init__(self, path: Path | None, run_tag: str = ""):
        self.path = path
        self.run_tag = run_tag
        self.lines: list[str] = []

    def __call__(self, msg: str) -> None:
        line = f"[{IO.now_str()}] {msg}"
        print(line)
        self.lines.append(line)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


def _log_path(target_date: str) -> Path:
    return C.LOG_DIR / f"run_{target_date}.log"


def _last_data_date() -> str | None:
    import pandas as pd
    p = C.PROCESSED_DAILY_DIR / "daily_market_price.parquet"
    if not p.exists():
        return None
    try:
        col = pd.read_parquet(p, columns=["date"])["date"]
        return str(pd.to_datetime(col).max().date()) if len(col) else None
    except Exception:  # noqa: BLE001
        return None


def _dates_to_collect(target_date: str, max_gap_days: int = 60) -> list[str]:
    """需要采集的日期 = 已有数据缺口 + 目标日期本身。

    - 目标日期总是采集（来源可能延迟发布当日数据）；
    - 缺口日期补齐，覆盖服务器停机。
    """
    last = _last_data_date()
    start = date.fromisoformat(last) + timedelta(days=1) \
        if last else date.fromisoformat(target_date)
    end = date.fromisoformat(target_date)
    if start > end:
        return [target_date]
    dates = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    if len(dates) > max_gap_days:
        dates = dates[-max_gap_days:]
    if target_date not in dates:
        dates.append(target_date)
    return sorted(set(dates))


def _evaluate_crawl(results: list, target_date: str) -> tuple[str, list[str]]:
    """判定 crawl_status 与结构漂移。fail-loud：结构变化不得静默成功。"""
    fetched = [r for r in results if r.status != SRC.ST_SKIPPED]
    schemes: list[str] = []
    if fetched and all(r.status == SRC.ST_FAIL for r in fetched):
        return "FAILED", schemes
    if any(r.status == SRC.ST_FAIL for r in fetched):
        base = "PARTIAL"
    else:
        base = "OK"
    # 字段级漂移
    for r in fetched:
        if r.schema_note and r.schema_note.startswith(SRC.SCHEMA_CHANGED):
            schemes.append(f"{r.date}/mt{r.market_type}: {r.schema_note}")
    # 目标日之前的批发口径全部无数据（源可达但结构/路径变化）
    past_wholesale = [r for r in fetched
                      if r.market_type == "1" and r.date < target_date
                      and r.status in (SRC.ST_OK, SRC.ST_EMPTY)]
    if past_wholesale and all(r.count == 0 for r in past_wholesale):
        schemes.append(f"{SRC.SCHEMA_CHANGED}: 目标日之前的批发口径全部返回 0 条")
    if schemes:
        return ("PARTIAL" if base == "OK" else base), schemes
    return base, schemes


def run(target_date: str, city: str = C.PRIMARY_CITY, dry_run: bool = False,
        collect: bool = True, adapter: str = "final",
        market_types: list[str] | None = None, skip_existing: bool = True,
        no_snapshot: bool = False) -> tuple[dict, int]:
    log = Logger(_log_path(target_date))
    C.ensure_dirs()
    log("=" * 70)
    log(f"job_start date={target_date} city={city} dry_run={dry_run} adapter={adapter} "
        f"tz={IO.TZ_NAME} pipeline_version={C.DAILY_PIPELINE_VERSION}")
    summary: dict = {"date": target_date, "city": city, "dry_run": dry_run,
                     "adapter": adapter, "timezone": IO.TZ_NAME,
                     "daily_pipeline_version": C.DAILY_PIPELINE_VERSION}

    # ---------------- 1. 采集（含缺口补齐） ----------------
    crawl_status, crawl_detail, results, schemes = "SKIPPED", [], [], []
    if collect:
        dates = _dates_to_collect(target_date)
        log(f"[collect] source={C.SOURCE_ID} dates={dates[0]}..{dates[-1]} ({len(dates)} 天) "
            f"markets={market_types or list(C.MARKET_TYPES)}")
        for d in dates:
            results += SRC.collect_day(
                d, market_types=market_types, dry_run=dry_run,
                skip_existing=skip_existing and d != target_date)
        for r in results:
            log(f"[crawl] date={r.date} mt{r.market_type} status={r.status} count={r.count} "
                f"attempts={r.http_attempts} schema_ok={r.schema_ok} err={r.error}")
            crawl_detail.append({"date": r.date, "market_type": r.market_type,
                                 "status": r.status, "count": r.count, "error": r.error,
                                 "url": r.url, "raw_path": r.raw_path,
                                 "schema_ok": r.schema_ok, "schema_note": r.schema_note})
        crawl_status, schemes = _evaluate_crawl(results, target_date)
        log(f"[crawl] result={crawl_status} records_fetched={sum(r.count for r in results)}")
        if schemes:
            log(f"[crawl] {SRC.SCHEMA_CHANGED} → {schemes[:3]}")
        summary.update({"collect_dates": dates, "records_fetched": sum(r.count for r in results),
                        "schema_changed": bool(schemes)})
    summary["crawl_status"] = crawl_status

    # ---------------- 2+3. 标准化 + QC ----------------
    if dry_run:
        import pandas as pd
        crops = C.supported_crops(city)
        raw = pd.concat([NZ.load_raw_records(), NZ.seed_legacy_raw()], ignore_index=True)
        qc = NZ.run_qc(raw, crops) if not raw.empty else raw
        n_ok = int((qc["quality_status"] == C.QC_OK).sum()) if not qc.empty else 0
        n_flag = int((qc["quality_status"] != C.QC_OK).sum()) if not qc.empty else 0
        log(f"[normalize:dry-run] rows={len(qc)} accepted={n_ok} flagged={n_flag} (未写入 Daily 数据)")
        summary.update({"rows_total": len(qc), "rows_accepted": n_ok, "qc_flagged": n_flag})
        log("job_end (dry-run)")
        return summary, EXIT_OK

    report = NZ.build(include_legacy_seed=True, write=True)
    log(f"[normalize] rows_total={report.get('rows_total')} accepted={report.get('rows_accepted')} "
        f"flagged={report.get('qc_flagged')} levels={report.get('by_level')} "
        f"max_date={report.get('date_max')}")
    cons = NZ.consistency_vs_canonical()
    log(f"[qc] consistency_vs_canonical={cons}")
    summary.update({"rows_total": report.get("rows_total"),
                    "rows_accepted": report.get("rows_accepted"),
                    "qc_flagged": report.get("qc_flagged"), "consistency": cons})

    # ---------------- 4. 特征 ----------------
    feat = FT.build(write=True)
    latest = FT.latest_by_crop(feat, as_of=target_date)
    data_date = str(latest["date"].max().date()) if not latest.empty else None
    log(f"[features] rows={len(feat)} latest_data_date={data_date}")
    summary["latest_data_date"] = data_date

    # ---------------- 5. Final Model 推理 ----------------
    assessments, adapter_meta = FA.compute_assessments(city=city, as_of=target_date,
                                                      adapter=adapter)
    log(f"[inference] adapter={adapter_meta.get('adapter')} "
        f"model_status={adapter_meta.get('model_status')} "
        f"model_version={adapter_meta.get('model_version')} "
        f"entry={adapter_meta.get('entry')} "
        f"n_evaluated={adapter_meta.get('n_crops_evaluated')} "
        f"fallback={adapter_meta.get('fallback_used')}")
    if adapter_meta.get("error"):
        log(f"[inference] error={adapter_meta['error']}")
    summary["model_status"] = adapter_meta.get("model_status")
    summary["model_version"] = adapter_meta.get("model_version")

    # ---------------- 6. Snapshot ----------------
    if no_snapshot:
        log("job_end (snapshot skipped)")
        return summary, EXIT_OK

    counts = {"records_fetched": summary.get("records_fetched", 0),
               "records_accepted": report.get("rows_accepted", 0),
               "records_rejected": int(report.get("by_status", {}).get("REJECTED", 0))}
    snap = SN.build(target_date=target_date, city=city, crawl_status=crawl_status,
                    crawl_detail=crawl_detail, adapter_meta=adapter_meta,
                    assessments=assessments, counts=counts, write=True)
    sigs = {c["crop"]: c["daily_signal"] for c in snap.get("crops", [])}
    log(f"[snapshot] status={snap['status']} freshness={snap['data_freshness']} "
        f"latest_data_date={snap['latest_data_date']} crops={len(snap.get('crops', []))} "
        f"contract_valid={snap.get('contract_valid')} hash={snap.get('snapshot_hash')}")
    log(f"[snapshot] signals={sigs}")
    summary.update({"snapshot_status": snap["status"],
                    "data_freshness": snap["data_freshness"],
                    "snapshot_hash": snap.get("snapshot_hash"),
                    "snapshot_path": f"data/processed/daily/snapshots/daily/{target_date}.json"})
    log("job_end")
    code = EXIT_OK if snap["status"] in ("complete", "partial") else EXIT_FAILED
    return summary, code


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AgriScope Daily · 每日市场脉搏流水线")
    ap.add_argument("--date", default=None, help="目标日期 YYYY-MM-DD（默认北京时间今天）；用于 backfill")
    ap.add_argument("--city", default=C.PRIMARY_CITY, help="城市（默认 沈阳）")
    ap.add_argument("--dry-run", action="store_true", help="只抓取/解析/QC，不写 Daily 数据")
    ap.add_argument("--no-collect", action="store_true", help="跳过网络采集，只用已有原始证据")
    ap.add_argument("--force", action="store_true", help="已存在的原始响应也重新抓取")
    ap.add_argument("--adapter", default="final", choices=["final", "legacy"],
                    help="模型适配器（默认 final；legacy 为显式旧信号回退，标 LEGACY_FALLBACK）")
    ap.add_argument("--markets", default=None, help="逗号分隔 marketType，默认 1,2,3")
    ap.add_argument("--no-snapshot", action="store_true", help="只跑到推理，不写 Snapshot")
    args = ap.parse_args(argv)

    target_date = args.date or IO.today_str()
    market_types = args.markets.split(",") if args.markets else None

    try:
        with IO.ProcessLock(C.LOCK_PATH):
            summary, code = run(target_date=target_date, city=args.city,
                                dry_run=args.dry_run, collect=not args.no_collect,
                                adapter=args.adapter, market_types=market_types,
                                skip_existing=not args.force, no_snapshot=args.no_snapshot)
    except RuntimeError as exc:
        print(f"[LOCK] {exc}")
        return EXIT_LOCKED
    except SN.SnapshotContractError as exc:
        Logger(_log_path(target_date))(f"[CONTRACT] {exc}")
        return EXIT_CONTRACT
    except Exception as exc:  # noqa: BLE001
        Logger(_log_path(target_date))(f"[ERROR] {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return EXIT_ERROR
    print("\nSUMMARY " + json.dumps(summary, ensure_ascii=False, default=str))
    return code


if __name__ == "__main__":
    raise SystemExit(main())