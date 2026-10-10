"""STEP 01–02：扫描真实数据源 + 冻结数据版本。

产出：
  data/data_snapshot.json              每个输入表的路径 / SHA256 / 行数 / 列数 / 日期范围 / 修改时间
  outputs/tables/input_inventory.csv   同一内容的表格形式
  reports/01_DATA_AUDIT.md             Phase 0 数据审计报告（数据冻结 + 事实核对 + 版本冲突）

原则：
  文档与磁盘事实冲突时，以磁盘事实为准，并把冲突显式记录到报告中。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    ANALYSIS, CROPS_CFG, PATHS, env_info, file_signature, get_logger, read_input,
    save_table, sha256_of,
)

LOG = get_logger("00_inventory")

# 每个输入表的「实体列 / 日期列」规格，用于自动推断覆盖范围
TABLE_SPEC = {
    "fact_price_city": dict(dates=["date"], entity=["price_type", "city", "crop_raw"]),
    "fact_market_supply": dict(dates=["date"], entity=["city", "crop"]),
    "fact_price_weekly": dict(dates=["week_start"], entity=["city", "crop", "geo_level"]),
    "fact_weather_daily": dict(dates=["date"], entity=["city"]),
    "fact_weather_extra_daily": dict(dates=["date"], entity=["city"]),
    "fact_soil_daily": dict(dates=["date"], entity=["city"]),
    "fact_city_climate_official": dict(dates=[], entity=["city"]),
    "fact_disaster_events": dict(dates=["start_date", "end_date"], entity=["city", "event_type"]),
    "fact_disaster_events_shenyang_2026_official": dict(
        dates=["start_date", "end_date"], entity=["city", "spatial_level"]),
    "fact_disaster_reports": dict(dates=["date"], entity=["city"]),
    "weekly_disaster_exposure": dict(dates=["week_start"], entity=["city"]),
    "fact_production_yearly": dict(dates=[], entity=["city", "crop"]),
    "fact_production_yearly_2020_2024": dict(dates=[], entity=["city", "crop"]),
    "fact_production_yearly_2025_shenyang": dict(dates=[], entity=["city", "crop"]),
    "dim_calendar": dict(dates=["date"], entity=[]),
    "crops": dict(dates=[], entity=[]),
    "cities": dict(dates=[], entity=[]),
    "city_static": dict(dates=[], entity=["city"]),
    "crop_calendar": dict(dates=[], entity=["crop", "region"]),
    "crop_agronomy": dict(dates=[], entity=["crop", "growth_stage"]),
    "source_registry": dict(dates=[], entity=[]),
    "weekly_climatology": dict(dates=[], entity=["city"]),
}


def probe(name: str) -> dict:
    """读取表头级别信息 + 关键覆盖范围（不把整表读进内存后长期持有）。"""
    p = PATHS.inp(name)
    spec = TABLE_SPEC.get(name, dict(dates=[], entity=[]))
    info = file_signature(p, compute_hash=True)
    info["name"] = name

    if p.suffix == ".parquet":
        df = pd.read_parquet(p)
    else:
        df = pd.read_csv(p, low_memory=False)

    info["rows"] = int(len(df))
    info["columns_list"] = list(df.columns)
    info["n_columns"] = int(df.shape[1])
    info["null_rate_overall"] = float(df.isna().mean().mean().round(6))

    for d in spec["dates"]:
        if d in df.columns:
            s = pd.to_datetime(df[d], errors="coerce")
            info[f"{d}_min"] = str(s.min().date()) if s.notna().any() else None
            info[f"{d}_max"] = str(s.max().date()) if s.notna().any() else None
            info[f"{d}_n_unique"] = int(s.nunique())
            info[f"{d}_invalid"] = int(s.isna().sum() - df[d].isna().sum())

    for e in spec["entity"]:
        if e in df.columns:
            vc = df[e].value_counts()
            info[f"{e}_n_unique"] = int(vc.size)
            if vc.size <= 12:
                info[f"{e}_values"] = {str(k): int(v) for k, v in vc.items()}

    # 沈阳子集覆盖（市场 / 气象 / 生产相关表才有意义）
    if "city" in df.columns:
        sub = df[df["city"] == "沈阳"]
        info["shenyang_rows"] = int(len(sub))
        for d in spec["dates"]:
            if d in sub.columns and len(sub):
                s = pd.to_datetime(sub[d], errors="coerce")
                info[f"shenyang_{d}_min"] = str(s.min().date()) if s.notna().any() else None
                info[f"shenyang_{d}_max"] = str(s.max().date()) if s.notna().any() else None
    return info


def baseline_signature() -> dict:
    """1991-2020 日值气候基线（JSON）单独登记。"""
    p = PATHS.inp("baseline_daily_json")
    sig = file_signature(p, compute_hash=True)
    data = json.loads(p.read_text(encoding="utf-8"))
    daily = data.get("daily", {})
    t = pd.to_datetime(pd.Series(daily.get("time", [])))
    sig.update({
        "name": "baseline_daily_json (沈阳 1991-2020)",
        "rows": int(len(t)),
        "date_min": str(t.min().date()) if len(t) else None,
        "date_max": str(t.max().date()) if len(t) else None,
        "variables": sorted(daily.keys()),
    })
    return sig


def raw_price_corpus_signature() -> dict:
    """原始市场价格语料（目录级）签名，用于复现「是否新增采集」。"""
    d = PATHS.inp("raw_price_dir")
    files = sorted(d.glob("*.json"))
    mt = {"1": 0, "2": 0, "3": 0}
    for f in files:
        key = f.stem.split("_")[-1].replace("mt", "")
        if key in mt:
            mt[key] += 1
    dates = sorted({f.name[:10] for f in files})
    return {
        "name": "raw_price_dir (shenyang_clz)",
        "path": str(d),
        "n_files": len(files),
        "by_market_type": mt,
        "date_min": dates[0] if dates else None,
        "date_max": dates[-1] if dates else None,
        "n_dates": len(dates),
        "note": "目录级签名（文件过多，不逐文件哈希）；文件内容哈希由 warehouse 的 data_manifest.csv 负责",
    }


def check_version_conflicts(snapshot: dict) -> list:
    """把「文档结论 vs 磁盘事实」冲突显式列出。"""
    conflicts = []
    wd = snapshot["tables"]["fact_weather_daily"]
    sy_w_max = wd.get("shenyang_date_max")
    planned_end = str(ANALYSIS["time"]["core_end_planned"])
    if sy_w_max and planned_end > sy_w_max:
        conflicts.append({
            "item": "天气覆盖结束日",
            "doc_claim": "SHENYANG_DATA_TEMPLATE.md 记价格 2020-01-02~2026-09-21；任务书 §八 期望核心窗口至 2026-09",
            "disk_fact": f"沈阳 ERA5 日值气象实际截止 {sy_w_max}（再分析数据滞后于实时价格）",
            "resolution": f"核心研究窗口结束日 = 三源共同覆盖最后一天 = {sy_w_max}；不补造 2026-09-15 以后的气象",
        })
    wh = snapshot.get("warehouse_manifest_rows")
    conflicts.append({
        "item": "成交量单位",
        "doc_claim": "fact_market_supply.unit_raw = 「未标注(推断为吨)」",
        "disk_fact": "官方接口无 volume 单位字段；推断值仅为备注",
        "resolution": "全研究保留 volume_unit=unknown；禁止任何「吨」表述，仅用相对变化/标准化",
    })
    conflicts.append({
        "item": "文档滞后性",
        "doc_claim": "data/research/reference/reports/FINAL_REPORT.md、AUDIT_REPORT.md、README 含历史结论",
        "disk_fact": "本轮以 city_data/reference/marts 实际表体为准重新核对（见下表覆盖事实）",
        "resolution": "结论一律来自 city_data/reference/marts 实体读取，不引用历史报告数字",
    })
    return conflicts


def write_audit_report(snapshot: dict, conflicts: list) -> Path:
    t = snapshot["tables"]
    L: list = []
    A = L.append
    A("# 01 DATA AUDIT — 沈阳农业气象风险研究（Phase 0 数据冻结与审计）\n")
    A(f"> 生成时间：{snapshot['generated_at']}  ")
    A(f"> 数据仓库：`{PATHS.warehouse_root}`  ")
    A(f"> 分析项目：`{PATHS.project['config'].parent}`  ")
    A(f"> 环境：Python {snapshot['env']['python']} / pandas {snapshot['env']['packages']['pandas']} "
      f"/ statsmodels {snapshot['env']['packages']['statsmodels']} / lightgbm {snapshot['env']['packages']['lightgbm']}\n")
    A("本报告由 `src/00_inventory.py`（冻结与来源）与 `src/02_data_qa.py`（质量检查）共同生成。\n")
    A("---\n")
    A("## 0. 数据事实优先级\n")
    A("```text\n当前真实 Mart / Curated  >  最新 Metadata  >  Raw  >  最新模板  >  历史报告\n```\n")
    A("文档与磁盘冲突时 **以实际数据为准，并记录冲突**（见 §3）。\n")

    A("## 1. 数据快照（data_snapshot.json）\n")
    A("| 输入表 | 行数 | 列数 | 日期范围 | SHA256(前16) |")
    A("|---|---|---|---|---|")
    order = [
        "fact_price_city", "fact_market_supply", "fact_price_weekly",
        "fact_weather_daily", "fact_weather_extra_daily", "fact_soil_daily",
        "fact_city_climate_official", "fact_disaster_events",
        "fact_disaster_events_shenyang_2026_official", "fact_disaster_reports",
        "weekly_disaster_exposure", "fact_production_yearly",
        "fact_production_yearly_2020_2024", "fact_production_yearly_2025_shenyang",
        "dim_calendar", "crops", "cities", "city_static", "crop_calendar",
        "crop_agronomy", "source_registry", "weekly_climatology",
    ]
    for k in order:
        if k not in t:
            continue
        d = t[k]
        rng = "—"
        for a, b in [("date_min", "date_max"), ("start_date_min", "start_date_max"),
                     ("week_start_min", "week_start_max")]:
            if d.get(a) and d.get(b):
                rng = f"{d[a]} ~ {d[b]}"
                break
        h = (d.get("sha256") or "")[:16]
        A(f"| {k} | {d.get('rows'):,} | {d.get('n_columns')} | {rng} | `{h}` |")
    A("")
    A(f"沈阳 1991–2020 日值气候基线：`baseline_daily_json`，{t['baseline_daily_json']['rows']:,} 天，"
      f"变量 {t['baseline_daily_json']['variables']}\n")
    rp = t["raw_price_dir"]
    A(f"原始市场价格语料：{rp['n_files']:,} 个 JSON（批发 {rp['by_market_type']['1']} / "
      f"超市零售 {rp['by_market_type']['2']} / 集市零售 {rp['by_market_type']['3']}），"
      f"{rp['date_min']} ~ {rp['date_max']}\n")

    A("## 2. 沈阳关键覆盖事实（磁盘实测）\n")
    m = t["fact_market_supply"]
    pc = t["fact_price_city"]
    wd = t["fact_weather_daily"]
    sd = t["fact_soil_daily"]
    ed = t["fact_weather_extra_daily"]
    rows = [
        ("批发成交量记录（仅批发口径有真实 volume）", f"{m['rows']:,} 条 / {m['date_n_unique']} 个交易日 / {m['crop_n_unique']} 个品种",
         f"{m['date_min']} ~ {m['date_max']}"),
        ("城市价格记录（含零售，沈阳）", f"{pc.get('shenyang_rows', 0):,} 条", f"{pc.get('shenyang_date_min')} ~ {pc.get('shenyang_date_max')}"),
        ("气象日值（沈阳，ERA5 再分析）", f"{wd.get('shenyang_rows', 0):,} 天", f"{wd.get('shenyang_date_min')} ~ {wd.get('shenyang_date_max')}"),
        ("土壤日值（沈阳，ERA5-Land）", f"{sd.get('shenyang_rows', 0):,} 天", f"{sd.get('shenyang_date_min')} ~ {sd.get('shenyang_date_max')}"),
        ("扩展气象日值（沈阳）", f"{ed.get('shenyang_rows', 0):,} 天", f"{ed.get('shenyang_date_min')} ~ {ed.get('shenyang_date_max')}"),
        ("派生极端天气事件（沈阳）", "见 §4", "—"),
        ("官方灾害通报（沈阳，2026）", f"{t['fact_disaster_events_shenyang_2026_official']['rows']} 条", "2026-07-12 ~ 2026-09-02"),
    ]
    A("| 事实 | 规模 | 范围 |")
    A("|---|---|---|")
    for a, b, c in rows:
        A(f"| {a} | {b} | {c} |")
    A("")

    A("## 3. 版本冲突与处理（以磁盘事实为准）\n")
    A("| 冲突项 | 文档主张 | 磁盘事实 | 处理 |")
    A("|---|---|---|---|")
    for c in conflicts:
        A(f"| {c['item']} | {c['doc_claim']} | {c['disk_fact']} | {c['resolution']} |")
    A("")

    A("## 4. 极端天气事件（两种来源严格分离）\n")
    A("详见 `outputs/tables/event_catalog.csv`（由 `src/02_data_qa.py` 生成）与 "
      "`outputs/tables/event_overlap_flags.csv`。\n")
    A("- `event_source = derived_weather`：ERA5 日值阈值识别，**不是**官方灾情；")
    A("- `event_source = official`：沈阳市 / 沈北新区政府门户通报，含空间级别 city/district/township/village；")
    A("- 省级 290 万亩受灾口径 `spatial_level = province`，**禁止**摊派到市级。\n")

    A("## 5. 数据仓库未取得（NOT_PUBLIC）与本研究影响\n")
    A("| 缺口 | 状态 | 对研究的影响 |")
    A("|---|---|---|")
    A("| 沈阳批发成交量单位 | 官方未公开 | volume 仅做相对/标准化分析，报告禁止「吨」 |")
    A("| 批发蔬菜产地追踪 | 未公开 | 天气—市场关系不得表述为已证明的本地因果 |")
    A("| 市级农业受灾/成灾/绝收面积、直接经济损失 | 未公开 | 报告不得给出市级灾损估算值当作事实 |")
    A("| 10 种批发蔬菜分品种年度生产 | 年鉴/公报未单列 | 年度生产层仅到「蔬菜及食用菌」合计 |")
    A("| 2026-09-15 以后气象再分析 | 再分析滞后 | 核心窗口截止 2026-09-14 |")
    A("")

    p = PATHS.report("01_DATA_AUDIT.md")
    p.write_text("\n".join(L), encoding="utf-8")
    return p


def main() -> None:
    LOG.info("开始扫描数据仓库：%s", PATHS.warehouse_root)
    tables = {}
    skip = {"baseline_daily_json", "raw_price_dir"}
    for name in PATHS.inputs:
        if name in skip:
            continue
        try:
            tables[name] = probe(name)
            LOG.info("  [OK] %-45s rows=%-9s", name, tables[name].get("rows"))
        except Exception as e:  # noqa: BLE001
            LOG.error("  [FAIL] %s: %s", name, e)
            tables[name] = {"name": name, "error": f"{type(e).__name__}: {e}"}

    tables["baseline_daily_json"] = baseline_signature()
    tables["raw_price_dir"] = raw_price_corpus_signature()

    snapshot = {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "warehouse_root": str(PATHS.warehouse_root),
        "project_root": str(PATHS.project["config"].parent),
        "env": env_info(),
        "crop_config": CROPS_CFG["market"],
        "tables": tables,
        "config_hashes": {
            k: sha256_of(CONFIG) for k, CONFIG in {
                "paths.yaml": PATHS.project["config"] / "paths.yaml",
                "analysis.yaml": PATHS.project["config"] / "analysis.yaml",
                "crops.yaml": PATHS.project["config"] / "crops.yaml",
                "events.yaml": PATHS.project["config"] / "events.yaml",
            }.items()
        },
    }

    conflicts = check_version_conflicts(snapshot)
    snapshot["version_conflicts"] = conflicts

    sp = PATHS.out("snapshot")
    sp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    LOG.info("快照写入 %s", sp)

    flat = []
    for k, v in tables.items():
        row = {"table": k}
        for kk, vv in v.items():
            if isinstance(vv, (str, int, float, bool)) or vv is None:
                row[kk] = vv
        flat.append(row)
    save_table(pd.DataFrame(flat), "input_inventory.csv")

    rp = write_audit_report(snapshot, conflicts)
    LOG.info("审计报告写入 %s", rp)


if __name__ == "__main__":
    main()
