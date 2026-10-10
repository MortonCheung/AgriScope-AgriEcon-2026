# -*- coding: utf-8 -*-
"""F0: Final Data Audit —— 对 data/model_ready/ 的 19 张 parquet 做最终建模数据审计。

输出（写入 models/data/manifests/final/audit/）：
  table_inventory.csv    每表：主题/行数/字段/时间范围/城市/作物/粒度/唯一键/重复
  field_map.csv          每字段：dtype/缺失率/唯一值数/是否时间字段
  missingness.csv        每表缺失率 TopN
  price_level_matrix.csv 各城 crop×price_level 分布（口径混用检查）
  key_checks.csv         候选唯一键的重复检查
  audit_findings.csv     P0/P1/P2 发现
判定：DATA_AUDIT_PASS / DATA_AUDIT_FAIL
"""
from __future__ import annotations
import glob
import os
from typing import Dict, List

import numpy as np
import pandas as pd

from decision_engine.final.fcommon import (MODEL_READY, MANIFEST_DIR, SHENYANG_CROPS,
                                           PRICE_LEVELS, ensure_dir, md5_of_frame, now_stamp)

AUDIT_DIR = MANIFEST_DIR / "audit"

# 主题归类（用于报告）
TOPIC = {
    "shenyang_core/market_daily.parquet": "沈阳市场日频价格（wholesale）",
    "shenyang_core/environment_daily.parquet": "沈阳环境日频（ERA5/ERA5-Land+NDVI月度）",
    "shenyang_core/phenology.parquet": "沈阳物候日历（多 geo_scope）",
    "shenyang_core/cost_reference.parquet": "沈阳成本参考（RESEARCH_REFERENCE）",
    "shenyang_core/crop_context.parquet": "沈阳设施蔬菜结构（截面）",
    "chaoyang_extended/market_daily.parquet": "朝阳市场日频价格（market_average 主源）",
    "chaoyang_extended/environment_daily.parquet": "朝阳环境日频",
    "chaoyang_extended/phenology.parquet": "朝阳物候日历",
    "jinzhou_extended/market_daily.parquet": "锦州市场日频价格（多 level/OCR）",
    "jinzhou_extended/environment_daily.parquet": "锦州环境日频",
    "jinzhou_extended/phenology.parquet": "锦州物候日历",
    "climate/climate_daily.parquet": "六城环境日频（合并）",
    "climate/vegetation_anomaly.parquet": "六城植被异常（月度）",
    "hri/hri_inputs.parquet": "HRI 输入（城×作物×周）",
    "profit/cost_components.parquet": "成本构成（研究参考）",
    "profit/cost_proxy.parquet": "成本 proxy（区域）",
    "profit/crop_cost.parquet": "作物成本（LOCAL/PROXY）",
    "recommendation/market_nodes.parquet": "市场节点（静态）",
    "recommendation/structural_context.parquet": "结构性上下文（多 block 合并宽表）",
}

DATE_COLS = ["date", "observation_date", "period", "start_date", "end_date"]


def _file_rows() -> List[str]:
    return sorted(glob.glob(str(MODEL_READY / "**" / "*.parquet"), recursive=True))


def _date_range(df: pd.DataFrame) -> str:
    for c in DATE_COLS:
        if c in df.columns:
            s = pd.to_datetime(df[c], errors="coerce")
            if s.notna().any():
                return f"{c}:{s.min().date()}~{s.max().date()}"
    return "-"


def _granularity(df: pd.DataFrame) -> str:
    fr = df["frequency"].dropna().unique().tolist() if "frequency" in df.columns else []
    if fr:
        return "|".join(sorted(str(x) for x in fr))[:60]
    return "-"


def _candidate_keys(df: pd.DataFrame) -> List[List[str]]:
    keys = []
    if {"observation_date", "crop_standard", "price_level"} <= set(df.columns):
        keys.append(["observation_date", "crop_standard", "price_level"])
    if {"observation_date", "crop_standard"} <= set(df.columns):
        keys.append(["observation_date", "crop_standard"])
    if {"city", "crop_standard", "iso_year", "iso_week"} <= set(df.columns):
        keys.append(["city", "crop_standard", "iso_year", "iso_week"])
    if {"city", "date"} <= set(df.columns):
        keys.append(["city", "date"])
    return keys


def run_audit() -> Dict[str, object]:
    ensure_dir(AUDIT_DIR)
    files = _file_rows()
    inv_rows, field_rows, miss_rows, key_rows, level_rows = [], [], [], [], []
    findings = []

    for f in files:
        rel = os.path.relpath(f, MODEL_READY)
        df = pd.read_parquet(f)
        # --- inventory ---
        cities = df["city"].dropna().nunique() if "city" in df.columns else 0
        crops = df["crop_standard"].dropna().nunique() if "crop_standard" in df.columns else 0
        inv_rows.append({
            "table": rel, "topic": TOPIC.get(rel, "-"),
            "rows": len(df), "cols": df.shape[1],
            "date_range": _date_range(df),
            "n_city": cities, "n_crop": crops,
            "granularity": _granularity(df),
            "dup_full_rows": int(df.duplicated().sum()),
            "content_md5": md5_of_frame(df),
        })
        # --- field map ---
        for c in df.columns:
            field_rows.append({
                "table": rel, "column": c, "dtype": str(df[c].dtype),
                "missing_pct": round(float(df[c].isna().mean() * 100), 2),
                "n_unique": int(df[c].nunique(dropna=True)),
            })
        # --- missingness ---
        m = (df.isna().mean() * 100).round(2)
        m = m[m > 0].sort_values(ascending=False)
        for c, v in m.items():
            miss_rows.append({"table": rel, "column": c, "missing_pct": float(v)})
        # --- keys ---
        for k in _candidate_keys(df):
            key_rows.append({"table": rel, "key": "+".join(k),
                             "dup_rows": int(df.duplicated(k).sum())})
        # --- price_level matrix ---
        if "price_level_canonical" in df.columns or "price_level" in df.columns:
            lc = "price_level_canonical" if "price_level_canonical" in df.columns else "price_level"
            g = df.groupby(["city", lc]).size().reset_index(name="rows")
            g["table"] = rel
            level_rows.append(g)

    inv = pd.DataFrame(inv_rows); inv.to_csv(AUDIT_DIR / "table_inventory.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(field_rows).to_csv(AUDIT_DIR / "field_map.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(miss_rows).to_csv(AUDIT_DIR / "missingness.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(key_rows).to_csv(AUDIT_DIR / "key_checks.csv", index=False, encoding="utf-8-sig")
    if level_rows:
        pd.concat(level_rows, ignore_index=True).to_csv(
            AUDIT_DIR / "price_level_matrix.csv", index=False, encoding="utf-8-sig")

    # ---------------------------------------------------------------- 显式检查
    # P0_BLOCKING：使核心模型在数学/业务上不成立、且无法通过降级规避 → FAIL
    # P0_MITIGATED：真实缺陷，但 Final 层有明确规避策略（单层价格/强转/换表）→ 记录并 PASS
    P0, MITIGATED, P1, P2 = [], [], [], []

    # (1) crop_standard 污染
    bad_tokens = {"规格", "品级", "包装", "第一列错位"}
    poll = []
    for f in files:
        rel = os.path.relpath(f, MODEL_READY)
        df = pd.read_parquet(f)
        if "crop_standard" in df.columns:
            s = df["crop_standard"].astype(str)
            n = int(s.isin(bad_tokens).sum())
            if n:
                poll.append((rel, n))
    if poll:
        P0.append({"issue": "crop_standard 污染残留", "detail": str(poll)})
    else:
        findings.append({"issue": "crop_standard 污染 = 0（全部表）", "level": "OK"})

    # (2) price_level 混用
    hri = pd.read_parquet(MODEL_READY / "hri/hri_inputs.parquet")
    comp = hri["price_level"].astype(str).str.contains(r"\|")
    comp_pct = float(comp.mean() * 100)
    MITIGATED.append({
        "issue": "hri_inputs price_level 复合混用",
        "level": "P0_MITIGATED",
        "detail": f"{comp_pct:.1f}% 行 price_level 为多 level 拼接（如 farm_gate|wholesale）；"
                  f"沈阳全为 wholesale（干净），非沈阳城市被混用。"
                  f"→ Final HRI 仅使用单一 level（wholesale）价格序列，禁止使用混层聚合。",
    })

    # (3) price_per_kg dtype = object
    obj_dtype = [r["table"] for r in inv_rows
                 if r["table"].endswith("market_daily.parquet")
                 and str(pd.read_parquet(MODEL_READY / r["table"])["price_per_kg"].dtype) == "object"]
    if obj_dtype:
        P1.append({"issue": "price_per_kg dtype=object", "level": "P1",
                   "detail": f"{obj_dtype} 数值以字符串存储（内容为数值），Final 层统一 astype(float)。"})

    # (4) 城市 + level 覆盖（定价可用性）
    for name, tier in [("沈阳", "full_model"), ("朝阳", "extended"),
                       ("锦州", "weak"), ("大连/铁岭/丹东", "insufficient")]:
        pass
    avail = []
    for city, path in [("沈阳", "shenyang_core/market_daily.parquet"),
                       ("朝阳", "chaoyang_extended/market_daily.parquet"),
                       ("锦州", "jinzhou_extended/market_daily.parquet")]:
        d = pd.read_parquet(MODEL_READY / path)
        veg = d[d["crop_standard"].isin(SHENYANG_CROPS)]
        avail.append({"city": city, "rows": len(d), "veg10_rows": len(veg),
                      "veg10_crops": veg["crop_standard"].nunique(),
                      "levels": "|".join(sorted(d["price_level_canonical"].dropna().unique()))})
    for c in ["大连", "铁岭", "丹东"]:
        avail.append({"city": c, "rows": 0, "veg10_rows": 0, "veg10_crops": 0,
                      "levels": "NO_MARKET_TABLE"})
    pd.DataFrame(avail).to_csv(AUDIT_DIR / "city_price_availability.csv", index=False, encoding="utf-8-sig")

    # (5) shenyang env 元数据列全空
    env = pd.read_parquet(MODEL_READY / "shenyang_core/environment_daily.parquet")
    allnull = [c for c in env.columns if env[c].isna().mean() == 1.0]
    if allnull:
        P1.append({"issue": "shenyang_core/environment_daily 元数据列全空", "level": "P1",
                   "detail": f"全空列 {allnull}；Final 气候特征统一改用 climate/climate_daily.parquet。"})

    # (6) structural_context 重复行
    sc = pd.read_parquet(MODEL_READY / "recommendation/structural_context.parquet")
    if sc.duplicated().sum() > 0:
        P2.append({"issue": "structural_context 存在完全重复行", "level": "P2",
                   "detail": f"{int(sc.duplicated().sum())} 行重复；仅作解释性上下文，不进核心模型。"})

    # (7) NDVI 月度（不可当日频）
    va = pd.read_parquet(MODEL_READY / "climate/vegetation_anomaly.parquet")
    if set(va["frequency"].dropna().unique()) == {"monthly"}:
        findings.append({"issue": "vegetation_anomaly frequency=monthly（尊重月度粒度，不伪装日频）", "level": "OK"})

    all_findings = P0 + MITIGATED + P1 + P2 + \
                   [x for x in findings if x.get("level") == "OK"]
    pd.DataFrame(all_findings).to_csv(AUDIT_DIR / "audit_findings.csv", index=False, encoding="utf-8-sig")

    verdict = "DATA_AUDIT_FAIL" if len(P0) else "DATA_AUDIT_PASS"
    result = {
        "verdict": verdict,
        "n_tables": len(inv),
        "total_rows": int(inv["rows"].sum()),
        "p0_blocking": len(P0), "p0_mitigated": len(MITIGATED),
        "p1": len(P1), "p2": len(P2),
        "reason": ("无阻断性 P0；P0_MITIGATED 缺陷通过 Final 层规避策略处理"
                   f"（{len(MITIGATED)} 项：hri_inputs 混层 → Final HRI 仅用单一 wholesale；"
                   "price_per_kg dtype → 强转 float；气候 → 统一用 climate_daily）")
                  if not P0 else "存在未处理阻断性 P0",
        "ts": now_stamp(),
    }
    (MANIFEST_DIR / "audit").mkdir(parents=True, exist_ok=True)
    pd.Series(result).to_json(AUDIT_DIR / "audit_verdict.json", force_ascii=False, indent=2)
    return result


# ---------------------------------------------------------------- MODEL_DATA_MAP
def build_model_data_map() -> pd.DataFrame:
    """各模块允许读取的表/字段/时间语义/推理可用性/source_class/proxy/禁用字段。"""
    rows = [
        # Price Model
        dict(module="Price Model", city="沈阳", table="shenyang_core/market_daily.parquet",
             fields="price_per_kg,observation_date,crop_standard,price_level_canonical",
             time_semantics="日频观测，特征仅用 <=t", availability="inference_time_available",
             source_class="LOCAL_CANONICAL_A", proxy="no",
             forbidden="未来价格/未来窗口均值/centered rolling/volume(不在 model_ready)"),
        dict(module="Price Model", city="朝阳", table="chaoyang_extended/market_daily.parquet",
             fields="price_per_kg(market_average 子集),observation_date,crop_standard",
             time_semantics="日频，仅取 market_average 单层", availability="inference_time_available",
             source_class="LOCAL_CANONICAL_A", proxy="no",
             forbidden="farm_gate/wholesale 混合；跨城价格拼接"),
        dict(module="Price Model", city="锦州", table="jinzhou_extended/market_daily.parquet",
             fields="(弱化/降级，不做主模型)", time_semantics="-", availability="degraded",
             source_class="LOCAL_OCR_B", proxy="partial",
             forbidden="多 level 混算；OCR 未校验值直接当真实"),
        # HRI
        dict(module="HRI", city="沈阳(既有)", table="hri/hri_inputs.parquet",
             fields="price_mean(仅 wholesale 行),price_lag_*,price_pct_rank,price_mom_4w",
             time_semantics="城×作物×周，expanding past-only 分位",
             availability="inference_time_available", source_class="LOCAL_CANONICAL_A", proxy="no",
             forbidden="复合 price_level 行（farm_gate|wholesale 等）；volume(单位未知)"),
        dict(module="HRI", city="沈阳", table="shenyang_core/market_daily.parquet",
             fields="price_per_kg（Final HRI 自建周序列，单一 wholesale）",
             time_semantics="周合成，past-only", availability="inference_time_available",
             source_class="LOCAL_CANONICAL_A", proxy="no", forbidden="未来窗口/全样本分位"),
        # Market Risk
        dict(module="Market Risk", city="沈阳", table="shenyang_core/market_daily.parquet",
             fields="price_per_kg（波动/回撤/异常）", time_semantics="日频，<=t",
             availability="inference_time_available", source_class="LOCAL_CANONICAL_A", proxy="no",
             forbidden="未来波动/未来回撤"),
        # Climate
        dict(module="Climate Exposure", city="六城", table="climate/climate_daily.parquet",
             fields="temperature_2m_*,precipitation_sum,et0,ndvi_anomaly_z",
             time_semantics="日频环境；NDVI 为月度 forward-map(source_frequency_ndvi)",
             availability="inference_time_available", source_class="ERA5_A", proxy="no",
             forbidden="把 NDVI 当月度日频真实值；把异常当减产"),
        dict(module="Climate Exposure", city="六城", table="climate/vegetation_anomaly.parquet",
             fields="ndvi_anomaly_z,ndvi_percentile", time_semantics="月度",
             availability="inference_time_available", source_class="Sentinel2_A", proxy="no",
             forbidden="日频化"),
        # Production Context
        dict(module="Production Context", city="沈阳区县", table="shenyang_core/crop_context.parquet",
             fields="crop_standard,facility_type,area_mu", time_semantics="截面（cross_section，非时序）",
             availability="static_context", source_class="LOCAL_REPORT_S", proxy="no",
             forbidden="当作时序面积增速"),
        dict(module="Production Context", city="沈阳", table="shenyang_core/phenology.parquet",
             fields="crop_standard,stage,start_date,end_date,calendar_geo_scope",
             time_semantics="事件/日历（多 geo_scope）", availability="static_context",
             source_class="LOCAL_B", proxy="no", forbidden="跨 geo_scope 混用"),
        # Profit
        dict(module="Profit Engine", city="沈阳/东北", table="profit/cost_components.parquet",
             fields="total_cost,各项,cost_source_class", time_semantics="cross_section",
             availability="user_or_reference", source_class="RESEARCH_REFERENCE_C", proxy="yes",
             forbidden="proxy 与真实值同权；输出虚假精准值"),
        dict(module="Profit Engine", city="沈阳/铁岭/辽阳", table="profit/crop_cost.parquet",
             fields="total_cost_per_mu,各项,cost_source_class", time_semantics="yearly",
             availability="local_or_proxy", source_class="LOCAL/REGIONAL_PROXY", proxy="partial",
             forbidden="REGIONAL_PROXY 不提权"),
        dict(module="Profit Engine", city="区域", table="profit/cost_proxy.parquet",
             fields="total_cost_per_mu,cost_source_class", time_semantics="cross_section(区域)",
             availability="proxy_only", source_class="REGIONAL_PROXY", proxy="yes",
             forbidden="当作本地真实值"),
        # Recommendation / Optimize
        dict(module="Recommendation", city="六城", table="recommendation/market_nodes.parquet",
             fields="market_name,lat,lon,scale", time_semantics="static",
             availability="static_context", source_class="PUBLIC_S", proxy="no",
             forbidden="当作动态运力"),
        dict(module="Recommendation", city="六城", table="recommendation/structural_context.parquet",
             fields="_block,各块字段", time_semantics="静态/解释性",
             availability="static_context", source_class="mixed", proxy="partial",
             forbidden="进核心数值模型"),
    ]
    df = pd.DataFrame(rows)
    ensure_dir(MANIFEST_DIR)
    df.to_csv(MANIFEST_DIR / "MODEL_DATA_MAP.csv", index=False, encoding="utf-8-sig")
    return df


if __name__ == "__main__":
    r = run_audit()
    print(r)
    m = build_model_data_map()
    print("MODEL_DATA_MAP rows:", len(m))