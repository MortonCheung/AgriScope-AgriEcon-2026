#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P2-02 历史玉米序列表 + P2-11 统一年度建模数据集。
- 03_clean/agriculture/corn_history_extended.csv
- 04_marts/corn_model_dataset_annual.csv
"""
import os

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(BASE, "03_clean")
MARTS = os.path.join(BASE, "04_marts")


def build_history():
    c = pd.read_csv(os.path.join(CLEAN, "agriculture", "corn_annual_pnb.csv"))
    c = c.sort_values("year")
    out = pd.DataFrame({
        "year": c["year"].astype(int),
        "admin_name": "沈北新区",
        "corn_area_ha": c["corn_area_ha"],
        "corn_yield_kg_ha": c["corn_yield_kg_ha"],
        "corn_production_t": c["corn_production_t"],
        "area_source_id": c["area_src"],
        "yield_source_id": c["yield_src"],
        "production_source_id": c["prod_src"],
        # 更名前新城子区与今沈北“行政区域不变、驻地不变”(沈政发[2006]27号) → 空间可直接比
        "comparability": "DIRECTLY_COMPARABLE",
        "quality_level": c["quality"],
        "notes": "沈阳统计年鉴分区县表(A)；2025由沈北区级年鉴(B)；2010-2017官方未公开",
    })
    out.to_csv(os.path.join(CLEAN, "agriculture", "corn_history_extended.csv"),
               index=False, encoding="utf-8-sig")
    print("[P2-02] corn_history_extended rows=", len(out), "years", out.year.min(), "-", out.year.max())
    return out


def build_dataset():
    hist = pd.read_csv(os.path.join(CLEAN, "agriculture", "corn_history_extended.csv"))
    feat = pd.read_csv(os.path.join(MARTS, "corn_year_weather_features.csv"))
    feat = feat.rename(columns={"year": "year"})
    m = hist.merge(feat, on="year", how="left")
    m["time_index"] = m["year"] - m["year"].min() + 1
    m["phenology_quality"] = "model_estimate_gdd_calibrated"
    m["weather_quality"] = "D_reanalysis_era5_gridcell"
    m["yield_quality"] = m["quality_level"]
    # 停用与“事件前”概念不一致的前置湿润列名，改用抽雄期为基准（已在特征中生成）
    # CORE（克制：围绕机制，控制特征数）
    core = ["year", "corn_yield_kg_ha", "corn_area_ha", "time_index",
            "veg_precip_sum", "repro_precip_sum", "repro_precip_max_5d",
            "repro_heavy_rain_days", "repro_tmax_mean", "repro_hot_days",
            "grain_filling_precip_sum", "rx1day", "rx5day", "antecedent_precip_14d",
            "phenology_quality", "weather_quality", "yield_quality", "comparability"]
    core = [c for c in core if c in m.columns]
    m.to_csv(os.path.join(MARTS, "corn_model_dataset_annual.csv"), index=False, encoding="utf-8-sig")
    m[core].to_csv(os.path.join(MARTS, "corn_model_dataset_annual_CORE.csv"), index=False, encoding="utf-8-sig")
    print("[P2-11] dataset rows=", len(m), "total cols=", len(m.columns), "CORE cols=", len(core))
    return m


if __name__ == "__main__":
    build_history()
    m = build_dataset()
    pd.set_option("display.width", 250)
    print(m[["year", "corn_yield_kg_ha", "repro_precip_sum", "repro_precip_max_5d",
             "repro_heavy_rain_days", "repro_tmax_mean", "repro_hot_days", "rx1day", "antecedent_precip_14d"]].to_string())
