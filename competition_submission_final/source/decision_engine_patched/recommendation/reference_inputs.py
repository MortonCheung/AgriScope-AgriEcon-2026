# -*- coding: utf-8 -*-
"""Phase 0 / §6 §54-§57: 参考输入层（成本 / 亩产 / 外部数据适配器）。

原则（写死）：
  - 用户显式输入永远优先于任何参考值；
  - 参考值必须带 provenance（来源级别 + 出处 + 是否 proxy + 单位口径）；
  - 禁止把 proxy 当作官方成本；proxy 参与推荐时必须标注并降低 confidence；
  - V3/V2 数据是 optional enhancement：缺失时 v2 仍可运行。

来源优先级：
  成本：user_input > observed_city > neighboring_city > regional_proxy > sector_proxy
  亩产：user_input > observed_city_county_crop > observed_city_aggregate(设施蔬菜合计)
"""
from __future__ import annotations
import json
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from decision_engine.common import ROOT, de_path, ensure_dir, paths, sha256_file

SNAP_V2 = de_path("data", "snapshots", "v2")
V2_DIR = "city_data/reference/decision_engine_supplement_v2"
V3_DIR = "city_data/reference/decision_engine_supplement_v3"

# 作物同义词 → 本项目标准名（仅做明确的同名映射，不做跨作物猜测）
CROP_SYNONYMS = {
    "番茄": "西红柿", "西红柿": "西红柿",
    "马铃薯": "土豆", "土豆": "土豆",
    "黄瓜": "黄瓜", "芹菜": "芹菜", "韭菜": "韭菜",
    "青椒": "青椒", "尖椒": "尖椒",
    "茄子": "茄子", "芸豆": "芸豆", "菜豆": "芸豆",
    "甘蓝": "甘蓝", "卷心菜": "甘蓝",
}

PY_M2_PER_MU = 666.6667  # 1 亩 = 666.6667 m²

# 仅接受辽宁省内来源（避免外省 proxy 混入，如宁夏灵武）
LIAONING_PREFIXES = ["沈阳", "大连", "鞍山", "抚顺", "本溪", "丹东", "锦州", "营口",
                     "阜新", "辽阳", "盘锦", "铁岭", "朝阳", "葫芦岛", "新民", "北票",
                     "黑山", "昌图", "开原", "辽中", "法库", "康平", "凌海", "海城"]


def _is_liaoning(city_str: str) -> bool:
    s = str(city_str)
    return any(s.startswith(p) or p in s for p in LIAONING_PREFIXES)


def _norm_crop(x) -> Optional[str]:
    s = str(x).strip()
    return CROP_SYNONYMS.get(s)


def _expand_combined_crop(label: str) -> List[str]:
    """处理「番茄/黄瓜」这类合并口径标签 → 展开为多个标准作物（并标注）。"""
    out = []
    for part in str(label).replace("、", "/").split("/"):
        c = _norm_crop(part.strip())
        if c and c not in out:
            out.append(c)
    return out


# ---------------------------------------------------------------- 亩产
def load_reference_yields() -> pd.DataFrame:
    """V3 crop_spatial_structure → 城市/区县 × 作物 亩产（kg/亩）。"""
    p = SNAP_V2 / V3_DIR / "crop_spatial_structure.csv"
    if not p.exists():
        return pd.DataFrame(columns=["city", "county", "crop", "yield_kg_per_mu", "year", "level", "source_name"])
    d = pd.read_csv(p, low_memory=False)
    d["crop"] = d["crop_standard"].map(_norm_crop)
    d = d[d["crop"].notna() & d["yield_kg_per_mu"].notna()].copy()
    d["year"] = pd.to_numeric(d["year_or_period"], errors="coerce")
    out = pd.DataFrame({
        "city": d["city"].astype(str),
        "county": d["district"].astype(str),
        "crop": d["crop"],
        "yield_kg_per_mu": pd.to_numeric(d["yield_kg_per_mu"], errors="coerce").round(1),
        "year": d["year"].astype("Int64"),
        "level": "observed_city_county_crop",
        "source_name": d.get("source_name", pd.Series("", index=d.index)),
        "source_level": d.get("source_level", pd.Series("", index=d.index)),
        "confidence": d.get("confidence", pd.Series("", index=d.index)),
        "production_system": d.get("facility_type", pd.Series("", index=d.index)),
    })
    return out.sort_values(["city", "crop", "year"])


def load_aggregate_vegetable_yield(city: str = "沈阳") -> Optional[Dict]:
    """城市级「蔬菜(设施合计)」亩产 → 仅作 sector/aggregate proxy（必须标注）。"""
    p = SNAP_V2 / V3_DIR / "crop_spatial_structure.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p, low_memory=False)
    m = (d["city"].astype(str) == city) & (d["crop_standard"].astype(str) == "蔬菜(设施合计)") \
        & d["yield_kg_per_mu"].notna()
    s = d[m]
    if len(s) == 0:
        return None
    s = s.assign(year=pd.to_numeric(s["year_or_period"], errors="coerce")).dropna(subset=["year"]).sort_values("year")
    last = s.iloc[-1]
    return {"city": city, "yield_kg_per_mu": float(last["yield_kg_per_mu"]), "year": int(last["year"]),
            "level": "observed_city_aggregate", "note": "蔬菜(设施合计)口径，非单一作物亩产；仅作 sector proxy"}


# ---------------------------------------------------------------- 成本
def load_reference_costs() -> pd.DataFrame:
    """V3 crop_cost_components → 亩均成本（元/亩·季 或 元/亩·年）。

    单位口径换算：per_mu/per_667m2/per_667m2_year/per_season → 统一到元/亩（per_season 表示元/亩·季）。
    """
    p = SNAP_V2 / V3_DIR / "crop_cost_components.csv"
    if not p.exists():
        return pd.DataFrame(columns=["source_city", "crop", "cost_per_mu", "basis", "level", "is_proxy"])
    d = pd.read_csv(p, low_memory=False)
    factor = {"per_mu": 1.0, "per_667m2": PY_M2_PER_MU / 667.0,
              "per_667m2_year": PY_M2_PER_MU / 667.0, "per_season": 1.0}
    rows = []
    for _, r in d.iterrows():
        raw_crop = str(r.get("crop_standard", "") or r.get("crop_raw", ""))
        label_crops = _expand_combined_crop(raw_crop)
        if not label_crops:
            single = _norm_crop(r.get("crop_raw"))
            label_crops = [single] if single else []
        # 蔬菜混合/合计口径 → 伪作物，作为 sector proxy 使用
        sector = False
        if not label_crops and "蔬菜" in raw_crop:
            label_crops = ["蔬菜(混合)"]
            sector = True
        cost = pd.to_numeric(r.get("total_cost"), errors="coerce")
        if not np.isfinite(cost) or not label_crops:
            continue
        basis = str(r.get("cost_basis", "per_mu"))
        geo = str(r.get("geo_level", ""))
        file_level = {"city": "observed_city", "neighboring_city": "neighboring_city",
                      "regional_proxy": "regional_proxy"}.get(geo, geo or "unknown")
        src_city = str(r.get("city", ""))
        prov_city = src_city.split("(")[0].strip()
        if not _is_liaoning(prov_city):
            continue                      # 外省 proxy（如宁夏灵武）不进入参考层
        combined = len(label_crops) > 1
        for crop in label_crops:
            rows.append({
                "source_city": src_city, "province_city": prov_city, "crop": crop,
                "cost_per_mu": round(float(cost) * factor.get(basis, 1.0), 2),
                "basis": basis, "file_level": file_level,
                "level": "sector_proxy" if sector else file_level,
                "is_proxy": bool(r.get("is_proxy", False)) or sector,
                "combined_label": combined,
                "annual_basis": basis == "per_667m2_year",
                "production_system": r.get("production_system"), "year": r.get("year"),
                "source_level": r.get("source_level"), "source_name": r.get("source_name"),
                "note": r.get("note"),
            })
    return pd.DataFrame(rows)


def load_grain_costs() -> pd.DataFrame:
    """V2 crop_cost_yearly_extended（粮食作物，供背景/对照，不用于蔬菜推荐）。"""
    p = SNAP_V2 / V2_DIR / "crop_cost_yearly_extended.csv"
    if not p.exists():
        return pd.DataFrame()
    d = pd.read_csv(p, low_memory=False)
    return d[["year", "city", "crop", "total_cost_per_mu", "geo_level", "source_level"]].copy()


# ---------------------------------------------------------------- 解析
def resolve_cost(city: str, crop: str, user_value: Optional[float] = None,
                 allow_proxy: bool = True) -> Dict:
    """返回 {available, cost_per_mu, level, is_proxy, evidence, warning}。"""
    if user_value is not None and np.isfinite(user_value) and user_value > 0:
        return {"available": True, "cost_per_mu": float(user_value), "level": "user_input",
                "is_proxy": False, "evidence": "用户显式输入", "warning": None}
    ref = load_reference_costs()
    if len(ref):
        ref = ref.assign(same_city=(ref["province_city"] == city))
        cand = ref[(ref["crop"] == crop)].copy()
        if len(cand):
            # 排序优先级：真实观测优先 > 同城 > 非合并口径 > 非年度口径 > 年份新
            cand["proxy_rank"] = cand["is_proxy"].astype(int)
            cand = cand.sort_values(["proxy_rank", "same_city", "combined_label", "annual_basis", "year"],
                                    ascending=[True, False, True, True, False])
            r = cand.iloc[0]
            lvl = ("observed_city" if (r["same_city"] and not r["is_proxy"])
                   else ("regional_proxy" if r["file_level"] == "regional_proxy" or not r["same_city"]
                         else "neighboring_city"))
            warn = []
            if lvl != "observed_city":
                warn.append("⚠ 跨城/区域参考成本（非目标城市实测），已降低 confidence")
            if r["combined_label"]:
                warn.append("合并口径（如番茄/黄瓜）")
            if r["annual_basis"]:
                warn.append("年度口径（含多茬），仅作上限参考")
            src_note = str(r.get("note") or "")
            if "种子+肥料+农药" in src_note or "未拆分" in src_note:
                warn.append("⚠ 成本口径不含人工/地租/折旧等（原文仅部分科目）→ 利润可能高估")
            return {"available": True, "cost_per_mu": float(r["cost_per_mu"]), "level": lvl,
                    "is_proxy": bool(lvl != "observed_city" or r["combined_label"] or r["annual_basis"]),
                    "basis": r["basis"],
                    "evidence": f"{r['source_city']} {r['year']}（{r['basis']}"
                                + ("，合并口径" if r["combined_label"] else "")
                                + f"，source_level={r['source_level']}）"
                                + (f"｜来源说明：{src_note[:80]}" if src_note else ""),
                    "warning": "；".join(warn) if warn else "城市级参考成本（参考值，非用户实际成本）"}
        if allow_proxy:
            sec = ref[ref["crop"] == "蔬菜(混合)"]
            if len(sec):
                r = sec.sort_values("year", ascending=False).iloc[0]
                return {"available": True, "cost_per_mu": float(r["cost_per_mu"]), "level": "sector_proxy",
                        "is_proxy": True, "basis": r["basis"],
                        "evidence": f"蔬菜混合 sector proxy：{r['source_city']} {r['year']}（{r['basis']}）",
                        "warning": "⚠ sector proxy（蔬菜混合口径，非该作物），误差较大，已降低 confidence"}
    return {"available": False, "cost_per_mu": None, "level": None, "is_proxy": True,
            "evidence": None, "warning": "无可用成本（必须用户输入）"}


def resolve_yield(city: str, crop: str, user_value: Optional[float] = None,
                  allow_proxy: bool = True) -> Dict:
    if user_value is not None and np.isfinite(user_value) and user_value > 0:
        return {"available": True, "yield_kg_per_mu": float(user_value), "level": "user_input",
                "is_proxy": False, "evidence": "用户显式输入", "warning": None}
    y = load_reference_yields()
    if len(y):
        exact = y[(y["city"] == city) & (y["crop"] == crop)]
        if len(exact):
            r = exact.sort_values("year").iloc[-1]
            return {"available": True, "yield_kg_per_mu": float(r["yield_kg_per_mu"]),
                    "level": "observed_city_county_crop", "is_proxy": False,
                    "evidence": f"{r['city']}·{r['county']} {int(r['year']) if pd.notna(r['year']) else ''}"
                                f"（source_level={r['source_level']}，confidence={r['confidence']}）",
                    "warning": "区县级实测亩产（参考）；不同地块存在差异"}
    if allow_proxy:
        agg = load_aggregate_vegetable_yield(city)
        if agg:
            return {"available": True, "yield_kg_per_mu": agg["yield_kg_per_mu"],
                    "level": "observed_city_aggregate", "is_proxy": True,
                    "evidence": f"{city} 蔬菜(设施合计) {agg['year']}",
                    "warning": "⚠ 城市级蔬菜合计口径 proxy（非该作物亩产），已降低 confidence"}
        # 省级/跨城 proxy（明确标注；仅用于使 P1/P2 简化推荐可行）
        p = SNAP_V2 / V3_DIR / "crop_spatial_structure.csv"
        if p.exists():
            d = pd.read_csv(p, low_memory=False)
            d["_crop"] = d["crop_standard"].map(_norm_crop)
            sub = d[(d["_crop"] == crop) & d["yield_kg_per_mu"].notna()]
            if len(sub):
                sub = sub.assign(_y=pd.to_numeric(sub["year_or_period"], errors="coerce")).sort_values("_y")
                r = sub.iloc[-1]
                return {"available": True, "yield_kg_per_mu": float(r["yield_kg_per_mu"]),
                        "level": "cross_city_proxy", "is_proxy": True,
                        "evidence": f"{r['city']}·{r.get('district','')} {r.get('year_or_period','')}（同作物跨城 proxy）",
                        "warning": "⚠ 跨城同作物亩产 proxy（非本城市实测），已显著降低 confidence"}
    return {"available": False, "yield_kg_per_mu": None, "level": None, "is_proxy": True,
            "evidence": None, "warning": "无可用亩产（必须用户输入）"}


def reference_table(city: str, crops: List[str],
                    user_costs: Optional[Dict[str, float]] = None,
                    user_yields: Optional[Dict[str, float]] = None) -> pd.DataFrame:
    user_costs = user_costs or {}
    user_yields = user_yields or {}
    rows = []
    for c in crops:
        rc = resolve_cost(city, c, user_costs.get(c))
        ry = resolve_yield(city, c, user_yields.get(c))
        rows.append({
            "city": city, "crop": c,
            "cost_per_mu": rc.get("cost_per_mu"), "cost_level": rc.get("level"),
            "cost_is_proxy": rc.get("is_proxy"), "cost_evidence": rc.get("evidence"),
            "yield_kg_per_mu": ry.get("yield_kg_per_mu"), "yield_level": ry.get("level"),
            "yield_is_proxy": ry.get("is_proxy"), "yield_evidence": ry.get("evidence"),
            "usable": bool(rc.get("available") and ry.get("available")),
            "warning": " | ".join([w for w in [rc.get("warning"), ry.get("warning")] if w]) or None,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- §54/§55 外部数据适配器
def refresh_external_data(verbose: bool = True) -> Dict:
    """重扫 supplement_v2/v3（以及候选的 supplement_v3+），对比快照 manifest：

    返回新增/变更文件清单；**不自动吸收**，只报告（optional enhancement 机制）。
    """
    man_p = de_path("data", "manifests", "input_manifest_v2.csv")
    known = set()
    if man_p.exists():
        m = pd.read_csv(man_p)
        known = set(m["source_path"].astype(str))
    cfg = paths()
    current = {}
    for g in cfg.get("snapshot_globs_v2", []):
        for f in sorted(ROOT.glob(g)):
            if f.is_file():
                rel = str(f.relative_to(ROOT))
                current[rel] = f
    new_files, changed = [], []
    for rel, f in current.items():
        if rel not in known:
            new_files.append(rel)
        else:
            changed.append(rel)
    # 也扫描可能的 v3+ 目录
    extra_dirs = sorted([p.name for p in (ROOT / "city_data/reference").glob("decision_engine_supplement_v*")])
    out = {"snapshot_manifest": str(man_p.relative_to(ROOT)) if man_p.exists() else None,
           "known_files": len(known), "current_files": len(current),
           "new_files": new_files, "supplement_dirs": extra_dirs,
           "note": "新增文件需人工确认后加入 snapshot_globs_v2 并重建快照；v2 不依赖新数据即可运行"}
    if verbose:
        print(f"[refresh] known={len(known)} current={len(current)} new={len(new_files)} dirs={extra_dirs}")
    return out


V3_ENHANCEMENT_MAP = [
    ("crop_cost_components.csv", "Profit / reference_inputs", True, "reference_cost（标注 proxy）"),
    ("crop_spatial_structure.csv", "reference_inputs / Production Context", True, "reference_yield（区县级实测）"),
    ("market_registry_v3.csv", "推荐证据层", True, "市场通道背景（不进入价格模型）"),
    ("market_supply_proxy.csv", "HRI 解释/证据", False, "仅当与价格信号同向时才作为解释证据"),
    ("remote_sensing_ndvi_city_monthly.csv", "Climate / Production Context", True, "长势背景 + ablation，不进入价格模型"),
    ("remote_sensing_evi_city_monthly.csv", "Climate / Production Context", True, "同上"),
    ("agri_insurance_claims_v3.csv", "Limitations / 背景", False, "不进入利润模型"),
    ("cold_chain_capacity_v3.csv", "Limitations / 背景", False, "不进入利润模型"),
    ("herding_events_v3.csv", "HRI 定性验证", True, "扩充跟风案例库"),
    ("demand_yearly_v3.csv", "背景/证据", False, "年度需求背景"),
    ("pest_events.csv", "Climate / Production Context（证据）", False, "事件证据，不建因果"),
    ("price_lnnync_veg_weekly_historical.csv", "省级价格背景", True, "长历史省域周价（背景对照）"),
]


def scan_v3_enhancements() -> pd.DataFrame:
    rows = []
    for fname, target, enabled, reason in V3_ENHANCEMENT_MAP:
        p = SNAP_V2 / V3_DIR / fname
        rows.append({"file": fname, "exists": p.exists(), "target_module": target,
                     "enabled": bool(enabled and p.exists()), "reason": reason})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    print(reference_table("沈阳", ["西红柿", "黄瓜", "芸豆", "土豆", "韭菜", "芹菜", "青椒", "尖椒", "茄子", "甘蓝"]).to_string())
    print()
    print(refresh_external_data())
    print()
    print(scan_v3_enhancements().to_string(index=False))