#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成阶段一图件（08_figures/）。"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(BASE, "03_clean")
MARTS = os.path.join(BASE, "04_marts")
ANA = os.path.join(BASE, "05_analysis")
FIG = os.path.join(BASE, "08_figures")
os.makedirs(FIG, exist_ok=True)
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "Heiti TC", "PingFang SC", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

# F1 2026 7月逐日降水
f = pd.read_csv(os.path.join(MARTS, "rainfall_event_features.csv"))
f["date"] = pd.to_datetime(f["date"])
j = f[(f["date"] >= "2026-07-01") & (f["date"] <= "2026-07-31")]
fig, ax = plt.subplots(figsize=(10, 4))
ax.bar(j["date"], j["precip_mm"], color="#2b6cb0", label="日降水")
ax.plot(j["date"], j["precip_prev_7d"], color="#c53030", marker="o", ms=3, lw=1, label="前7日累计")
ax.set_title("沈北新区 2026年7月 日降水与前7日累计（ERA5再分析）")
ax.set_ylabel("mm"); ax.legend(); fig.tight_layout()
fig.savefig(os.path.join(FIG, "F01_2026_07_daily_precip.png"), dpi=140); plt.close(fig)

# F2 玉米年度序列
c = pd.read_csv(os.path.join(MARTS, "corn_annual_baseline.csv"))
fig, ax1 = plt.subplots(figsize=(9, 4))
ax1.bar(c["year"], c["corn_production_t"] / 1e4, color="#90cdf4", label="总产量(万吨)")
ax1.set_ylabel("总产量(万吨)"); ax1.set_xlabel("年")
ax2 = ax1.twinx()
ax2.plot(c["year"], c["corn_yield_kg_ha"], color="#c53030", marker="o", label="单产(kg/ha)")
ax2.set_ylabel("单产(kg/ha)")
ax1.set_title("沈北新区玉米 播种面积/总产/单产 2018-2025（官方年鉴）")
ax1.set_xticks(c["year"])
fig.tight_layout(); fig.savefig(os.path.join(FIG, "F02_corn_yield_series.png"), dpi=140); plt.close(fig)

# F3 七月日降水分布 + 2026-07-13
d = pd.read_parquet(os.path.join(CLEAN, "weather", "pnb_daily_1991_2026.parquet"))
d["date"] = pd.to_datetime(d["date"])
jul = d[(d["date"] >= "1991-01-01") & (d["date"] <= "2020-12-31") & (d["date"].dt.month == 7)]
fig, ax = plt.subplots(figsize=(8, 4))
ax.hist(jul["precipitation_sum"], bins=40, color="#a0aec0", label="1991-2020 各年7月日降水")
ax.axvline(153.1, color="#c53030", lw=2, label="2026-07-13 = 153.1mm")
ax.set_xlabel("日降水量(mm)"); ax.set_ylabel("天数")
ax.set_title("七月日降水分布与2026-07-13极值位置（ERA5网格点）")
ax.legend(); fig.tight_layout()
fig.savefig(os.path.join(FIG, "F03_july_precip_distribution.png"), dpi=140); plt.close(fig)
print("figures ->", os.listdir(FIG))
