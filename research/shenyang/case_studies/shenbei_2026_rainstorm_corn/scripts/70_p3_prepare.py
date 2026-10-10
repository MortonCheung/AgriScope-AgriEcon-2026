#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P3-01~P3-03：主曝光指标选择 / 数据冻结 / 指纹 / 文献先验审计 / 输入审计。
输出目录：06_models/M1_bayesian_yield_response/
"""
import hashlib
import os

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M1 = os.path.join(BASE, "06_models", "M1_bayesian_yield_response")
for sub in ["", "data", "priors", "fits", "diagnostics", "validation", "sensitivity", "figures"]:
    os.makedirs(os.path.join(M1, sub), exist_ok=True)

DATA = os.path.join(BASE, "04_marts", "corn_model_dataset_annual.csv")
FEAT = os.path.join(BASE, "04_marts", "corn_year_weather_features.csv")
HIST = os.path.join(BASE, "03_clean", "agriculture", "corn_history_extended.csv")
LIT = os.path.join(BASE, "04_marts", "literature_parameter_library.csv")
PHEN = os.path.join(BASE, "03_clean", "phenology", "corn_phenology_reference.csv")
INTER = os.path.join(BASE, "03_clean", "intervention", "intervention_quantified.csv")
DIS = os.path.join(BASE, "03_clean", "disaster", "disaster_outcomes_2026.csv")
REG = os.path.join(BASE, "01_sources", "DATA_SOURCE_REGISTRY.csv")
UPSTREAM = [DATA, FEAT, HIST, LIT, PHEN, INTER, DIS, REG]


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    d = pd.read_csv(DATA)
    feat = pd.read_csv(FEAT)
    lit = pd.read_csv(LIT)

    # ---------------- P3-01 曝光指标审计 ----------------
    d = d.sort_values("year").reset_index(drop=True)
    t = d["time_index"].values.astype(float)
    exp_cols = ["repro_precip_max_5d", "repro_heavy_rain_days"]
    rows = []
    for c in exp_cols:
        x = d[c].values.astype(float)
        r_time = float(np.corrcoef(x, t)[0, 1])
        f26 = feat[feat["year"] == 2026]
        v26 = float(f26[c].iloc[0]) if len(f26) else float("nan")
        hist = feat[(feat["year"] >= 1991) & (feat["year"] <= 2025)][c].astype(float)
        rows.append(dict(
            exposure=c, n=len(x), missing=int(d[c].isna().sum()),
            vmin=round(float(x.min()), 1), vmax=round(float(x.max()), 1),
            mean=round(float(x.mean()), 1), sd=round(float(x.std(ddof=1)), 2),
            n_unique=int(d[c].nunique()),
            cor_with_time=round(r_time, 3),
            v2026=round(v26, 1),
            pct_1991_2025=round(float((hist < v26).mean() * 100), 1),
            p95_1991_2025=round(float(np.percentile(hist, 95)), 1),
            p99_1991_2025=round(float(np.percentile(hist, 99)), 1),
            in_train_range_2018_2025=bool(x.min() <= v26 <= x.max()),
        ))
    exp = pd.DataFrame(rows)
    exp.to_csv(os.path.join(M1, "data", "EXPOSURE_AUDIT.csv"), index=False, encoding="utf-8-sig")

    # 决策：机制(连续强降雨→渍涝) + 年际变异 + 连续性 → 主指标 = repro_precip_max_5d
    primary = "repro_precip_max_5d"
    alternative = "repro_heavy_rain_days"
    pr = exp[exp.exposure == primary].iloc[0]
    alt = exp[exp.exposure == alternative].iloc[0]

    with open(os.path.join(M1, "EXPOSURE_SELECTION.md"), "w", encoding="utf-8") as f:
        f.write(f"""# EXPOSURE_SELECTION.md — 主降雨指标选择（P3-01）

> 规则：**先按农业机制与数据质量选定，再看产量结果**；不得按“谁拟合最好”选择（避免数据窥探/多重比较）。

## 1. 两个候选（来自 Phase 2）

| 指标 | 定义 | 2018–2025 范围 | 均值±SD | 唯一值数 | cor(·, time) | 2026 值 | 1991–2025 分位 |
|---|---|---|---|---|---|---|---|
| **{primary}** | 抽雄吐丝期最大连续 5 日累计降水 (mm) | {pr.vmin}–{pr.vmax} | {pr['mean']}±{pr.sd} | {pr.n_unique} | {pr.cor_with_time} | {pr.v2026} | {pr.pct_1991_2025} |
| {alternative} | 抽雄吐丝期暴雨日数（≥25mm，天） | {alt.vmin}–{alt.vmax} | {alt['mean']}±{alt.sd} | {alt.n_unique} | {alt.cor_with_time} | {alt.v2026} | {alt.pct_1991_2025} |

## 2. 六个评价角度

1. **农业机制**：渍涝由“**连续强降雨**”而非单日成灾；`{primary}` 表达抽雄—吐丝阶段的短期累计极端强度，与“连续强降雨→渍涝”机制一致；`{alternative}` 仅为计数，损失了强度信息。
2. **数据连续性**：两者在 2018–2025 **均无缺失**、定义一致（同一 ERA5 网格点、同一定义）。
3. **年际变异**：`{primary}` 唯一值 {pr.n_unique} 个、SD {pr.sd}，变异充足；`{alternative}` 唯一值仅 {alt.n_unique} 个（取值为 0/1/2/5），在 n=8 下**离散度不足**，回归系数不稳定。
4. **与时间趋势相关性**：`{primary}` cor(time)={pr.cor_with_time}，`{alternative}` cor(time)={alt.cor_with_time}；二者均**未显示强时间共线**（|r|<0.6），不构成“降雨替代趋势”的问题。
5. **2026 事件表达能力**：`{primary}` 2026 = {pr.v2026} mm，位于 1991–2025 的 **{pr.pct_1991_2025} 分位**；`{alternative}` 2026 = {alt.v2026} 天（位 {alt.pct_1991_2025} 分位）。两者都捕捉到该事件，但 `{primary}` 更能表达“极端程度”。
6. **数据来源可靠性**：两者均来自**ERA5 再分析**（Level C）。Phase 2 已证明再分析**对极端降水日的识别一致性仅 0.391**（vs NASA POWER）→ **极端降水变量的测量误差可能明显高于平均气温等变量**，此不确定性必须随结论一并报告。

## 3. 决策

**主指标 primary_exposure = `{primary}`**；备选 `alternative_exposure = `{alternative}`（仅用于敏感性）。

理由：满足“连续强降雨→渍涝”的机制表达；2018–2025 变异充足；与时间趋势无强共线；能表达 2026 事件的极端程度。
**未**依据“与产量关系强弱”做选择——本研究未在选指标阶段计算 exposure–yield 关系。
""")

    # ---------------- 预注册 ----------------
    with open(os.path.join(M1, "MODEL_PREREGISTRATION.md"), "w", encoding="utf-8") as f:
        f.write(f"""# MODEL_PREREGISTRATION.md — 模型预注册（P3-01）

| 字段 | 值 |
|---|---|
| primary_exposure | `{primary}` |
| selection_reason | 机制（连续强降雨→渍涝）+ 年际变异充足 + 与时间趋势无强共线 + 能表达 2026 极端程度；**未**按拟合优度选择 |
| alternative_exposure | `{alternative}`（仅敏感性） |
| selection_date | 2026-09-22 |
| outcome | 沈北新区玉米单产 corn_yield_kg_ha（2018–2025，n=8） |
| trend_term | time_index（1..8） |
| model_family | 贝叶斯线性（log 单产） |
| priors | S0 Skeptical / S1（方向弱信息，非数值文献先验）/ S2 Wider |
| validation | Exact Leave-One-Year-Out（主要）+ 后验预测检查 + prior 敏感性 |

> **冻结声明**：主指标与模型结构一经登记，**后续不得因结果不理想而更换变量**（S1/S2 仅用于敏感性，不作为“换到满意为止”的通道）。
""")

    # ---------------- P3-03 冻结数据集 ----------------
    frozen = pd.DataFrame({
        "year": d["year"].astype(int),
        "yield_kg_ha": d["corn_yield_kg_ha"].astype(float),
        "time_index": d["time_index"].astype(int),
        "primary_rain_exposure": d[primary].astype(float),
        "yield_quality": d["yield_quality"],
        "weather_quality": d["weather_quality"],
        "comparability": d["comparability"],
        "source_ids": "SRC-SY-YB-DISTRICT|SRC-PNB-YB-2025|SRC-OM-ERA5-HOURLY",
    })
    fz = os.path.join(M1, "data", "M1_dataset_frozen.csv")
    frozen.to_csv(fz, index=False, encoding="utf-8-sig")

    with open(os.path.join(M1, "data", "M1_DATA_DICTIONARY.md"), "w", encoding="utf-8") as f:
        f.write(f"""# M1_DATA_DICTIONARY.md

| 变量 | 含义 | 单位 | 来源 | 备注 |
|---|---|---|---|---|
| year | 统计年度（表内年度） | 年 | 官方年鉴 | 2018–2025 |
| yield_kg_ha | 沈北玉米单产 | kg/ha | 沈阳统计年鉴(A)/沈北区级年鉴(B,2025) | 结果变量 |
| time_index | 长期趋势变量 = year−2017 | 1..8 | 派生 | Z 标准化后入模 |
| primary_rain_exposure | 抽雄吐丝期最大连续 5 日累计降水 = `{primary}` | mm | ERA5 再分析(D) | 主暴露；GDD 物候定义阶段 |
| yield_quality | 单产质量等级 | 文本 | — | A / B |
| weather_quality | 气象质量 | 文本 | — | D_reanalysis_era5_gridcell |
| comparability | 行政可比性 | 文本 | ADMIN_BOUNDARY_HISTORY | DIRECTLY_COMPARABLE |
| source_ids | 来源标识 | 文本 | registry | — |
""")

    # ---------------- 指纹 ----------------
    def stat(p):
        if not os.path.exists(p):
            return dict(file=os.path.relpath(p, BASE), sha256="MISSING", rows="", ymin="", ymax="", missing="")
        df = pd.read_csv(p)
        yr = ""
        if "year" in df.columns:
            yr = (int(df.year.min()), int(df.year.max()))
        return dict(file=os.path.relpath(p, BASE), sha256=sha256(p)[:16], rows=len(df),
                    ymin=yr[0] if yr else "", ymax=yr[1] if yr else "",
                    missing=round(float(df.isna().mean().mean()), 4))

    up = pd.DataFrame([stat(p) for p in UPSTREAM])
    up.to_csv(os.path.join(M1, "data", "M1_UPSTREAM_FINGERPRINTS.csv"), index=False, encoding="utf-8-sig")
    fzn = stat(fz)
    with open(os.path.join(M1, "M1_DATA_VERSION.md"), "w", encoding="utf-8") as f:
        f.write(f"""# M1_DATA_VERSION.md — 数据版本与指纹

| 项 | 值 |
|---|---|
| frozen_dataset | `data/M1_dataset_frozen.csv` |
| frozen_sha256(前16) | `{fzn['sha256']}` |
| rows | {fzn['rows']} |
| year_range | {fzn['ymin']}–{fzn['ymax']} |
| missing_rate | {fzn['missing']} |
| generator_script | `scripts/70_p3_prepare.py` |
| primary_exposure | `{primary}` |

## 上游文件指纹（SHA256 前16位）
""")
        f.write("| file | sha256(前16) | rows | year_min | year_max | missing_rate |\n|---|---|---|---|---|---|\n")
        for _, r in up.iterrows():
            f.write(f"| {r['file']} | `{r['sha256']}` | {r['rows']} | {r['ymin']} | {r['ymax']} | {r['missing']} |\n")
        f.write("\n\n> 目的：当模型/前端更新时，可确认“当时模型用了哪一版数据”。\n")

    # ---------------- P3-03 文献先验审计 ----------------
    lit_rows = [
        dict(paper_id="LIT-YU2014", crop="夏玉米", region="黄淮", climate_similarity="低（暖温带半湿润 vs 东北中温带）",
             maize_type="夏玉米", growth_stage="拔节/抽雄期", stress_type="人工淹水/渍水",
             exposure_definition="淹水天数(d)", outcome_definition="产量损失率(%)",
             effect_metric="拔节淹3d=-28.4%; 抽雄淹5d=-42.8%", sample_size="田间试验(非样本数)",
             can_map_to_M1_exposure="NO", transportability="低",
             use_for_numeric_prior="NO", reason="处理=淹水天数，M1 变量=降雨量(mm)；单位不可映射；夏玉米≠春玉米"),
        dict(paper_id="LIT-LIUZG2013", crop="夏玉米", region="黄淮(新乡)", climate_similarity="低",
             maize_type="夏玉米", growth_stage="苗/拔/抽雄吐丝/灌浆", stress_type="测坑淹涝",
             exposure_definition="淹涝天数(d)", outcome_definition="减产率(%)",
             effect_metric="抽雄吐丝淹6d=-12.99%; 各期区间-2.58~28.63%", sample_size="测坑试验",
             can_map_to_M1_exposure="NO", transportability="低",
             use_for_numeric_prior="NO", reason="天数→减产，无法映射到 mm 降雨；仅提供方向与量级范围"),
        dict(paper_id="LIT-LIUXF2021", crop="夏玉米", region="黄淮(农科院灌溉所)", climate_similarity="低",
             maize_type="夏玉米", growth_stage="苗/拔/抽雄吐丝/灌浆", stress_type="桶栽淹涝",
             exposure_definition="淹涝历时(d)", outcome_definition="减产率(%)",
             effect_metric="减产<10%阈值 抽雄吐丝1.5d; >20% 4d", sample_size="桶栽试验",
             can_map_to_M1_exposure="NO", transportability="低",
             use_for_numeric_prior="NO", reason="同上；桶栽非田间，尺度差异大"),
        dict(paper_id="LIT-FENG2013", crop="夏玉米", region="黄淮(开封)", climate_similarity="低",
             maize_type="夏玉米", growth_stage="抽雄期", stress_type="测坑淹水",
             exposure_definition="淹水天数(d)", outcome_definition="减产率(%)",
             effect_metric="抽雄淹6-10d=-10.5~48.7%", sample_size="测坑试验",
             can_map_to_M1_exposure="NO", transportability="低",
             use_for_numeric_prior="NO", reason="天数→减产；仅提供方向（负）与不规则量级"),
    ]
    pea = pd.DataFrame(lit_rows)
    pea["prior_class"] = "Class C（机制证据，用于 M3；不作为 M1 降雨斜率数值先验）"
    pea["usable_for_M1_direction_only"] = "YES（仅方向：渍涝不利于单产）"
    pea.to_csv(os.path.join(M1, "priors", "PRIOR_EVIDENCE_AUDIT.csv"), index=False, encoding="utf-8-sig")

    with open(os.path.join(M1, "priors", "PRIOR_EVIDENCE_AUDIT_SUMMARY.md"), "w", encoding="utf-8") as f:
        f.write("""# PRIOR_EVIDENCE_AUDIT_SUMMARY.md — 文献先验审计结论（P3-03）

## 分类
- **Class A（可直接数值先验）**：**无**。
  没有文献研究「**抽雄—吐丝阶段累计极端降水(mm) → 玉米单产**」且单位可映射到本研究主变量。
- **Class B（部分可比）**：无严格 B；4 篇均为“**淹水天数 → 减产%**”，与“**降雨 mm → 单产**”不可换算。
- **Class C（机制证据）**：**4 篇全部属于 Class C**。它们支持：
  1. 渍涝/淹水对玉米单产不利（方向）；
  2. 抽雄—吐丝期为敏感期；
  3. 效应量级随淹水时长非线性上升（大致 3–6 天出现 10%–40% 损失）。
  这些用于 **M3 渍涝损伤模型**，**不用于 M1 的降雨斜率数值先验**。

## 结论（对应规格 §13）
> **当前文献不足以构造直接的 `rainfall → yield` 信息性先验。**

因此 M1′ **不伪造“文献先验”**，改用以 0 为中心的 **skeptical / weakly informative prior**；
另设一个**方向弱信息**情景（S1）仅用于敏感性，且**明确标注其并非可映射的数值文献先验**。
""")

    # ---------------- M1_INPUT_AUDIT.md ----------------
    with open(os.path.join(M1, "M1_INPUT_AUDIT.md"), "w", encoding="utf-8") as f:
        f.write(f"""# M1_INPUT_AUDIT.md — 输入事实冻结（P3 起始）

## 结果变量
- 沈北新区玉米**单位面积产量** `corn_yield_kg_ha`（kg/ha）

## 有效年份 / 样本量
- **2018–2025**；**n = 8**

## 2026
- **只有天气与事件，没有正式年度玉米单产结果**（`not_available`）

## 天气历史
- **1991–2026 日值特征**（ERA5 再分析，D 级；`corn_year_weather_features.csv`）

## 物候
- 已有 **GDD 年际物候估计**（`corn_phenology_yearly_gdd.csv`；抽雄≈7月中旬、吐丝≈7月中旬）

## 关键事件
- **2026-07-13 左右极端降雨**，位于**抽雄—吐丝窗口**附近。

## 当前不能直接观测
- 全区 **Waterlogging**（隐变量）
- **CropStress**
- **2026 区级实际灾损**

## 模型定位（重要）
> M1′ 当前研究的是 **“天气暴露—年度单产响应”（response / association model）**，
> **不是**完整因果链 `Weather→Waterlogging→CropStress→Yield`。
> 因此结果**不得**表述为 **causal effect**，除非未来获得充分因果证据。

## 训练／使用边界
- 训练年份：2018–2025（n=8）
- 2026 用于**情景推演**，其暴露值是否落在训练范围见 `validation/EXTRAPOLATION_AUDIT.md`
""")

    print("[P3-prepare] EXPOSURE_AUDIT:")
    print(exp.to_string(index=False))
    print("[P3-prepare] frozen rows=", len(frozen), "| M1 dir =", os.path.relpath(M1, BASE))
    return primary, alternative


if __name__ == "__main__":
    main()
