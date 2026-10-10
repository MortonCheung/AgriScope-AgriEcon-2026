"""生成 RESEARCH_TREE_DATA_GAPS.csv —— 研究树缺口表（基于真实文件统计）。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir()) / "data/raw/retained_source/city_data"
OUT = ROOT.parent / "archive" / "audits" / "gap_analysis_20260922"
OUT.mkdir(exist_ok=True)

audit = pd.read_csv(OUT / "CITY_DATA_AUDIT_V2.csv", encoding="utf-8-sig")


def rows_for(city_cn, dataset):
    r = audit[(audit["city"] == city_cn) & (audit["dataset"] == dataset)]
    if len(r) == 0:
        return None
    return r.iloc[0]


# (research_branch, research_question, dataset_needed, cities, target_requirement, priority, candidate_source)
SPEC = [
    ("天气→生产", "气象因子对产量的影响", "production_yearly", ["铁岭", "锦州", "丹东", "大连", "朝阳"],
     "unit归一(吨)+公式一致", "P4", "现有 fact_production_yearly*"),
    ("生产→供应→价格", "供应冲击如何传导到价格", "volume_observations",
     ["铁岭", "锦州", "丹东", "大连", "朝阳"], "≥2-3城 / ≥2市场 / ≥1-2年", "P0",
     "批发市场日报/商务预报/农业农村部/电子结算"),
    ("跨城市价格传播", "同作物跨城价格是否联动", "price_observation",
     ["铁岭", "丹东"], "同作物同price_level 共同窗口≥3-4城", "P1",
     "铁岭县/昌图/开原/西丰；东港/凤城/宽甸"),
    ("天气→价格", "气象对价格的传导", "price_observation",
     ["铁岭", "锦州", "丹东", "大连", "朝阳"], "核心作物价格≥3年且周级", "P1",
     "各市官方价格监测/批发市场/农业B2B"),
    ("物候窗口", "生育期气象暴露", "phenology_events",
     ["锦州", "丹东", "大连", "铁岭", "朝阳"], "核心作物播种/生育期/成熟/收获窗口", "P2",
     "农业农村局/农技站/气象局/农业气象旬报"),
    ("灾害冲击", "真实灾损对产量/价格影响", "disaster_events_observed",
     ["丹东", "大连", "朝阳", "铁岭", "锦州"], "每城若干真实可验证事件", "P3",
     "农业农村局/应急管理/气象/水利/政府新闻"),
    ("政策缓冲", "干预对市场冲击的缓冲", "policy_events",
     ["丹东", "锦州", "朝阳", "铁岭", "大连"], "干预时间线（区分 geo_level）", "P3",
     "发改委/商务局/农业农村局/政府公告"),
]

out = []
for branch, q, ds, cities, target, prio, src in SPEC:
    for c in cities:
        r = rows_for(c, ds)
        cur_rows = int(r["rows"]) if r is not None else 0
        cur_dates = int(r["unique_dates"]) if r is not None else 0
        status = "OK" if cur_rows and (cur_rows > 100 or ds.startswith("production")) else (
            "PARTIAL" if cur_rows else "EMPTY")
        # 生产特殊：视为已有
        if ds == "production_yearly" and cur_rows:
            status = "HAS (需单位QC)"
        out.append({
            "research_branch": branch, "research_question": q, "dataset_needed": ds,
            "city": c, "crop": "", "current_status": status,
            "current_rows": cur_rows, "current_dates": cur_dates,
            "current_years": f"{r['start_date']}~{r['end_date']}" if r is not None else "",
            "missing_reason": "" if cur_rows else "该城该数据集为空",
            "target_requirement": target, "priority": prio,
            "candidate_source": src, "collection_status": "TODO", "notes": "",
        })

df = pd.DataFrame(out)
df.to_csv(OUT / "RESEARCH_TREE_DATA_GAPS.csv", index=False, encoding="utf-8-sig")
# 同时放一份到 city_data 根，便于查看
df.to_csv(ROOT / "reference" / "registries" / "RESEARCH_TREE_DATA_GAPS.csv", index=False, encoding="utf-8-sig")
print(f"[OK] RESEARCH_TREE_DATA_GAPS.csv {df.shape}")
print(df.groupby(['priority', 'dataset_needed', 'current_status']).size().to_string())
