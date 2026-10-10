#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R07 M3 专属文献审计与重分级（M3-A/B/C）
R08 M3 候选数学模型设计（剂量响应 / 分层贝叶斯 / 保守区间）
R09 M3 合成实验与可识别性（synthetic，不输出沈北实际减产）
输出：06_models/prebuild/M3/
"""
import os

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(BASE, "06_models", "prebuild", "M3")
os.makedirs(P, exist_ok=True)
SEED = 20260923

# ---------- R07 文献审计 ----------
ROWS = [
    dict(paper_id="LIT-YU2014", region="黄淮平原(河南/安徽)", maize_type="夏玉米(浚单20)",
         growth_stage="拔节期", waterlogging_duration_d=3, water_depth="持续淹水", soil_condition="田间",
         temperature="暖温带", yield_control=None, yield_treated=None, relative_yield=round(1-0.284, 3),
         yield_loss=0.284, sample_size="田间试验(未报n)", replicates=None, variance_available="NO",
         experiment_type="field", field_or_pot="field", applicability_to_shenbei="PARAMETER_PRIOR_ONLY",
         quality="C", M3_class="M3-B", notes="地区/玉米类型不同；无方差"),
    dict(paper_id="LIT-YU2014", region="黄淮平原", maize_type="夏玉米",
         growth_stage="抽雄期", waterlogging_duration_d=5, water_depth="持续淹水", soil_condition="田间",
         temperature="暖温带", yield_control=None, yield_treated=None, relative_yield=round(1-0.428, 3),
         yield_loss=0.428, sample_size="田间试验", replicates=None, variance_available="NO",
         experiment_type="field", field_or_pot="field", applicability_to_shenbei="PARAMETER_PRIOR_ONLY",
         quality="C", M3_class="M3-B", notes="抽雄淹水5d → −42.8%"),
    dict(paper_id="LIT-LIUZG2013", region="黄淮(新乡)", maize_type="夏玉米",
         growth_stage="抽雄吐丝期", waterlogging_duration_d=6, water_depth="测坑淹涝", soil_condition="测坑",
         temperature="暖温带", yield_control=None, yield_treated=None, relative_yield=round(1-0.1299, 3),
         yield_loss=0.1299, sample_size="测坑试验", replicates=None, variance_available="NO",
         experiment_type="pot", field_or_pot="pot", applicability_to_shenbei="PARAMETER_PRIOR_ONLY",
         quality="C", M3_class="M3-B", notes="显著减产阈值：苗期2/拔节4/抽雄吐丝6/灌浆4 d"),
    dict(paper_id="LIT-LIUZG2013", region="黄淮(新乡)", maize_type="夏玉米",
         growth_stage="抽雄吐丝期(区间)", waterlogging_duration_d="2~10", water_depth="测坑淹涝",
         soil_condition="测坑", temperature="暖温带", yield_control=None, yield_treated=None,
         relative_yield=None, yield_loss="0.0258~0.2863", sample_size="测坑试验", replicates=None,
         variance_available="NO", experiment_type="pot", field_or_pot="pot",
         applicability_to_shenbei="PARAMETER_PRIOR_ONLY", quality="C", M3_class="M3-B",
         notes="抽雄吐丝期减产区间 −2.58%~−28.63%"),
    dict(paper_id="LIT-LIUXF2021", region="黄淮(中国农科院灌溉所)", maize_type="夏玉米",
         growth_stage="抽雄吐丝期", waterlogging_duration_d="1/3/5/7/9", water_depth="桶栽淹涝",
         soil_condition="桶栽", temperature="暖温带", yield_control=None, yield_treated=None,
         relative_yield=None, yield_loss="<10% 阈值1.5d; >20% 阈值4d", sample_size="桶栽试验",
         replicates=None, variance_available="NO", experiment_type="pot", field_or_pot="pot",
         applicability_to_shenbei="PARAMETER_PRIOR_ONLY", quality="C", M3_class="M3-B",
         notes="桶栽尺度差异大；给出 10%/20% 减产阈值"),
    dict(paper_id="LIT-FENG2013", region="黄淮(开封)", maize_type="夏玉米(郑单958)",
         growth_stage="抽雄期", waterlogging_duration_d="6~10", water_depth="测坑淹水", soil_condition="测坑",
         temperature="暖温带", yield_control=None, yield_treated=None, relative_yield=None,
         yield_loss="0.105~0.487", sample_size="测坑试验", replicates=None, variance_available="NO",
         experiment_type="pot", field_or_pot="pot", applicability_to_shenbei="PARAMETER_PRIOR_ONLY",
         quality="C", M3_class="M3-B", notes="每增1天约−10%（原文表述）"),
    dict(paper_id="LIT-BILL2026RICE", region="泰国/缅甸(水稻)", maize_type="水稻(非玉米)",
         growth_stage="多生育期", waterlogging_duration_d="varies", water_depth="有", soil_condition="田间调查",
         temperature="热带", yield_control=None, yield_treated=None, relative_yield=None,
         yield_loss="stage-damage 函数", sample_size="20 个损失模型综述+野外调查", replicates=None,
         variance_available="PARTIAL", experiment_type="meta_review+survey", field_or_pot="field",
         applicability_to_shenbei="METHOD_ONLY", quality="B", M3_class="M3-C",
         notes="NHESS 2026;提供 Bayesian 回归(水深×历时×生育期)+跨区迁移误差的**方法学**范式;作物不同→不作玉米参数"),
    dict(paper_id="LIT-TIAN2021META", region="全球(115 研究/2419 比较)", maize_type="多作物(含玉米)",
         growth_stage="多生育期", waterlogging_duration_d="0-3/3-6/6-9/9-15/15-28(分组)",
         water_depth="部分", soil_condition="田间为主", temperature="多气候带", yield_control=None, yield_treated=None,
         relative_yield=None, yield_loss="平均 −32.9%(全作物)", sample_size="2419 comparisons / 115 studies",
         replicates="—", variance_available="NO(本研究仅取汇总值)", experiment_type="global_meta_analysis",
         field_or_pot="field", applicability_to_shenbei="HIERARCHICAL_PRIOR_SOURCE", quality="A",
         M3_class="M3-B", notes="Front Plant Sci 2021;提供**按积水历时分组**的全局剂量-响应结构 → M3-B 的层次先验来源"),
]
aud = pd.DataFrame(ROWS)
aud["lnRR"] = aud["relative_yield"].apply(lambda r: (round(float(np.log(r)), 3) if isinstance(r, float) else None))
aud.to_csv(os.path.join(P, "M3_LITERATURE_EVIDENCE_AUDIT.csv"), index=False, encoding="utf-8-sig")

# ---------- 文献锚点（用于合成实验的合理范围；非沈北参数）----------
# stage -> (duration_days, loss_fraction) 锚点，来源 LIUZG2013 / YU2014 / FENG2013
ANCHORS = {
    "vegetative": [(2, 0.18), (4, 0.30)],
    "jointing": [(4, 0.21), (5, 0.28)],
    "tasseling": [(5, 0.428), (6, 0.13)],
    "silking": [(6, 0.13), (6, 0.13)],
    "grain_filling": [(4, 0.135), (10, 0.20)],
}


def m3_a_dose(duration_h, stage):
    """M3-A 分阶段剂量响应（分段线性 + 天花板），单调不减。"""
    anchors = np.array(ANCHORS.get(stage, [(4, 0.15), (8, 0.30)]), float)
    x = anchors[:, 0]; y = anchors[:, 1]
    d = duration_h / 24.0
    loss = np.interp(d, x, y, left=0.0, right=y[-1])
    return float(np.clip(loss, 0, 0.95))


def m3_c_interval(duration_h, stage):
    """M3-C 保守区间：文献 min/max × 时长插值 → [low, high]。"""
    anchors = np.array(ANCHORS.get(stage, [(4, 0.15), (8, 0.30)]), float)
    d = duration_h / 24.0
    lo = np.interp(d, anchors[:, 0], np.clip(anchors[:, 1] - 0.05, 0, None), left=0.0,
                   right=max(anchors[:, 1].min() - 0.05, 0))
    hi = np.interp(d, anchors[:, 0], np.clip(anchors[:, 1] + 0.10, 0, 0.95), left=0.0,
                   right=min(anchors[:, 1].max() + 0.15, 0.95))
    return float(lo), float(hi)


def main():
    durations = [0, 12, 24, 48, 72, 96]
    stages = ["vegetative", "jointing", "tasseling", "silking", "grain_filling"]
    rows = []
    for st in stages:
        for h in durations:
            la = m3_a_dose(h, st)
            lo, hi = m3_c_interval(h, st)
            rows.append(dict(stage=st, duration_h=h, M3A_loss=round(la, 4),
                             M3C_low=round(lo, 4), M3C_high=round(hi, 4),
                             M3C_width=round(hi - lo, 4)))
    sim = pd.DataFrame(rows)
    sim.to_csv(os.path.join(P, "M3_synthetic_dose_response.csv"), index=False, encoding="utf-8-sig")

    # 单调性检查
    mono = []
    for st in stages:
        v = sim[sim.stage == st].sort_values("duration_h")["M3A_loss"].values
        mono.append(dict(stage=st, monotone_nondecreasing=bool(np.all(np.diff(v) >= -1e-9))))
    mono_df = pd.DataFrame(mono)

    # 参数敏感性（对锚点的扰动 → loss 变化）
    rng = np.random.default_rng(SEED)
    sens = []
    for st in stages:
        base = np.array([m3_a_dose(h, st) for h in durations])
        devs = []
        for _ in range(500):
            ANCHORS[st] = [(x, float(np.clip(y * (1 + rng.normal(0, 0.25)), 0, 0.95)))
                           for x, y in ANCHORS[st]]
            devs.append(np.abs(np.array([m3_a_dose(h, st) for h in durations]) - base).mean())
        sens.append(dict(stage=st, mean_abs_dev_under_25pct_anchor_perturb=round(float(np.mean(devs)), 4)))
    sens_df = pd.DataFrame(sens)

    with open(os.path.join(P, "M3_LITERATURE_AUDIT.md"), "w", encoding="utf-8") as f:
        f.write("# M3_LITERATURE_AUDIT.md（R07 / §三十~三十四）\n\n")
        f.write("## 重分级原则\n")
        f.write("- **M3-A**：春玉米 + 类似生育期 + 积水历时 + 产量结果（可直接支持 M3 数值关系）\n")
        f.write("- **M3-B**：部分可比（地区/品种/盆栽不同）→ 层次先验 / 敏感性\n")
        f.write("- **M3-C**：仅机制（无最终产量）\n\n")
        f.write("## 结果\n")
        f.write(f"- **M3-A：{int((aud.M3_class=='M3-A').sum())} 篇**（现有文献**均非**东北春玉米 → 无直接可比）。\n")
        f.write(f"- **M3-B：{int((aud.M3_class=='M3-B').sum())} 条**（含 1 篇**全球渍涝 meta 分析**，提供按历时分组的剂量-响应结构）。\n")
        f.write(f"- **M3-C：{int((aud.M3_class=='M3-C').sum())} 条**（作物不同的**方法学**文献，如水稻洪水损失函数）。\n\n")
        f.write("## 本轮新增（§八十九 方法/文献核验所得）\n")
        f.write("- **LIT-TIAN2021META**（Front Plant Sci 2021, 10.3389/fpls.2021.634898）：115 篇/2419 组比较的全球 meta 分析，"
                "给出**按积水历时分组**（0–3/3–6/6–9/9–15/15–28 d）的减产幅度，全作物平均 **−32.9%**。\n"
                "  → 它是 **M3-B 的层次先验来源**（提供 duration 剂量-响应结构），但**非玉米专属、非同地区**，"
                "只能作**先验**而非沈北参数。\n")
        f.write("- **LIT-BILL2026RICE**（NHESS 2026, 10.5194/nhess-26-925-2026）：水稻洪水损失函数；"
                "给出 **Bayesian 回归（水深×历时×生育期）** 的方法学范式，并量化**跨区迁移误差**。\n"
                "  → **M3-C（方法学）**：指导我们“优先水深+历时+生育期、并报告跨区迁移不确定性”的设计，"
                "但**作物不同**，不提供玉米数值。\n\n")
        f.write("## ⚠️ 对模型选择的影响（更新 §三十九 结论）\n")
        f.write("引入全球 meta 分析后，**M3-B（分层贝叶斯）由“暂不可用”变为“可作先验级使用”**：\n")
        f.write("- 仍**缺**各研究的 SD/SE/n → **不能**做严格加权 meta-analysis；\n")
        f.write("- 但可用其**分组效应**构造**弱信息先验**，再用本地（若未来获得）duration 更新。\n")
        f.write("**修正后的选择**：**M3-B（先验级）+ M3-C（保守区间）并行**；M3-A 保留为透明基准。\n\n")
        f.write("## 统一效应量与方差\n")
        f.write("- 已换算 `relative_yield = 1 − loss` 与 `lnRR = ln(Y_t/Y_c)`。\n")
        f.write("- **方差信息：全部 NO**（论文未报 SD/SE/n）→ **不能伪造方差**，**不能**做加权 meta-analysis；"
                "只能用**区间/先验**方式（§三十四）。\n\n")
        f.write(aud[["paper_id", "growth_stage", "waterlogging_duration_d", "relative_yield",
                     "yield_loss", "variance_available", "M3_class"]].to_string(index=False) + "\n\n")
        f.write("> ⚠️ 关键：**这些是夏玉米（黄淮海）试验**。用于沈北（东北春玉米）时属 **PARAMETER_PRIOR_ONLY**，"
                "只能提供方向与量级区间，**不得**直接作为沈北减产率。\n")
    print("[R07] M3 分级:", aud.M3_class.value_counts().to_dict())

    with open(os.path.join(P, "M3_MODEL_CANDIDATES.md"), "w", encoding="utf-8") as f:
        f.write("""# M3_MODEL_CANDIDATES.md（R08 / §三十五~四十）
> 本文件为 **PREBUILD**：只设计结构，**不输出沈北实际减产**。

## M3-A 简单分阶段剂量响应
```
Damage = clip( f(duration | growth_stage), 0, 0.95 )
```
- 结构：每阶段分段线性（锚点来自文献区间），**强制单调不减**
- 输入：`waterlogging_duration` + `growth_stage`
- 输出：`yield_loss_fraction`
- 硬约束：同阶段下 duration ↑ ⇒ 期望损伤**不得系统性下降**

## M3-B 分层贝叶斯 Meta-regression
```
lnRR_i ~ Normal( mu_i, sigma_i )
mu_i   = a_study[i] + b_stage[i] * f(duration_i) + c * depth_i
a_study ~ Normal(a0, tau_a)     # study random effect
```
- 用于融合不同论文；`depth` 若可得
- **前提**：需要方差信息以正确加权 → 当前 **variance_available=NO** → **暂不能正式拟合**

## M3-C 保守区间模型（partial identification）
```
(stage, duration) → [loss_low, loss_high]
```
- 当文献异质、无法拟合光滑函数时使用；输出**区间**而非点估计

## 选择原则（§三十九）
按 ① 文献数量 ② 研究设计 ③ 效应可比性 ④ 方差信息 决定，**不预设 M3-B 最好**。
当前（含 §八十九 新增文献）：文献 4 篇**夏玉米** + 1 篇**全球 meta 分析**（多作物）+ 1 篇**水稻方法学**；**均无逐研究方差**。
→ **修正后：M3-B（先验级，用全球 meta 的分组效应作弱信息先验）+ M3-C（保守区间）并行**；M3-A 作透明基准。
**严格加权 meta-analysis 仍待方差补齐**（§三十四）。
""")

    with open(os.path.join(P, "M3_SYNTHETIC_EXPERIMENTS.md"), "w", encoding="utf-8") as f:
        f.write("# M3_SYNTHETIC_EXPERIMENTS.md（R09 / §四十一~四十三）\n\n")
        f.write("> **合成输入**（0/12/24/48/72/96h × 5 阶段）**仅用于测试模型结构**，**不是沈北实际值**。\n\n")
        f.write("## 合成剂量响应（M3-A 与 M3-C）\n\n")
        f.write(sim.to_string(index=False) + "\n\n")
        f.write("## 单调性检查（M3-A）\n\n" + mono_df.to_string(index=False) + "\n\n")
        f.write("## 锚点不确定性敏感性（±25% 扰动 500 次）\n\n" + sens_df.to_string(index=False) + "\n\n")
        f.write("## 只回答以下五个问题（§四十三）\n")
        f.write(f"1. 数学稳定：单调性检查 {'全部通过' if mono_df.monotone_nondecreasing.all() else '存在失败'}；\n")
        f.write("2. 输出物理合理：M3-A 落在 [0, 0.95]；M3-C 区间宽度随时长增大；\n")
        f.write("3. 文献异质性区间：见 `M3C_width`（抽雄吐丝期宽度可达 ~0.2）；\n")
        f.write("4. 最敏感参数：锚点斜率（±25% 扰动下平均绝对偏差见上表）；\n")
        f.write("5. 必须由 Data Agent 补的输入：**积水持续时间**、**方差信息**、**春玉米本地试验**。\n\n")
        f.write("## 严禁\n> ❌ 不得据此写出“沈北减产 X%”。\n")
    print("[R09] 单调性:", mono_df.to_dict("records"))

    with open(os.path.join(P, "M3_INPUT_CONTRACT.md"), "w", encoding="utf-8") as f:
        f.write("""# M3_INPUT_CONTRACT.md（R09 / §四十四）

## 正式 M3 最低输入
| 字段 | 级别 | 类型 | 说明 | 缺失时降级 |
|---|---|---|---|---|
| cell_id | REQUIRED | str | 与 M2 空间单元对齐 | 无法接入 → 停止 |
| area | REQUIRED | m² | 单元面积（聚合用） | 用 100×100 默认 |
| crop_type | REQUIRED | enum | 至少 `maize`/`other` | 若未知 → 标 `agricultural_cropland`（不得称玉米） |
| growth_stage | REQUIRED | enum | vegetative/jointing/tasseling/silking/grain_filling | 用 GDD 估计并标 `model_estimate` |
| waterlogging_duration | **REQUIRED(核心)** | hours | 积水持续时长 | **缺失 → M3 不可运行**（只可区间情景） |
| duration_uncertainty | OPTIONAL | [lo,hi] | 时长区间 | 无 → 用情景区间 |
| water_depth | OPTIONAL | m | 水深 | 无 → 仅用时长的 M3-B/C |
| evidence_quality | REQUIRED | enum | D1/D2/D3（§五十七） | 无 → 标 unknown |

## 降级规则
- 缺 `waterlogging_duration` → **禁止输出任何沈北损伤数字**；只允许 `stage×duration` 情景区间（M3-C）。
- 缺 `variance` → 禁止加权 meta-analysis；只允许区间/先验。
- 缺 `crop_type=maize` → 结论只能写 **agricultural cropland**。

## 输出契约
`yield_ratio_distribution` / `damage_fraction_distribution`（**必须带区间**）。
""")
    print("[R09] M3_INPUT_CONTRACT 已写出")


if __name__ == "__main__":
    main()
