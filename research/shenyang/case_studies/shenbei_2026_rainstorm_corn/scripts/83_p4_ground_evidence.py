#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P4-13 / P4-35：真实地面证据点（G1–G5 分层）+ 标签审计 → 决定 Route A/B/C。
严格：unreported != waterlogging=0（不虚构负样本）。
"""
import os

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M2 = os.path.join(BASE, "06_models", "M2_waterlogging_spatial")
SPA = os.path.join(BASE, "05_analysis", "09_spatial_waterlogging")
os.makedirs(os.path.join(M2, "labels"), exist_ok=True)
os.makedirs(SPA, exist_ok=True)

# 坐标来源：OSM place 节点（街道中心）/ 路名代理 —— 均为**近似**，精度见 spatial_accuracy_m
ROWS = [
    dict(evidence_id="G-01", location_name="兴隆台街道（万亩农田受淹）", latitude=42.06251, longitude=123.35339,
         date="2026-07-14", evidence_type="G2_official_summary", waterlogging_observed="yes",
         water_depth="unknown", affected_area_mu=10000, crop="玉米/水稻", intervention="unknown",
         source_id="SRC-LN-GOV-2026-0717", spatial_accuracy_m=4000, confidence="medium",
         notes="官方综述转述‘7月14日凌晨兴隆台街道万亩农田受淹’；‘万亩’为量级表述；坐标为街道中心近似"),
    dict(evidence_id="G-02", location_name="新城子街道八间房村", latitude=42.05190, longitude=123.51407,
         date="2026-07-14", evidence_type="G2_media", waterlogging_observed="yes",
         water_depth=">1m", affected_area_mu=8000, crop="水稻/玉米", intervention="12台8寸泵;7-18排净",
         source_id="SRC-SYD-2026-0814", spatial_accuracy_m=5000, confidence="medium",
         notes="村名明确但无精确田块坐标；用新城子街道中心近似；‘8000余亩’为媒体量级"),
    dict(evidence_id="G-03", location_name="兴隆台街道新民村", latitude=42.06251, longitude=123.35339,
         date="2026-07-15", evidence_type="G2_official", waterlogging_observed="yes",
         water_depth="unknown", affected_area_mu=5000, crop="玉米/水稻",
         intervention="破桥清障(拆除梗阻桥涵)+机械强排",
         source_id="SRC-LN-GOV-2026-0717|SRC-SINA-20260715", spatial_accuracy_m=5000, confidence="medium-high",
         notes="★新增细化：新民村5000亩农田大面积积水；直接工程瓶颈=新叶线新民支渠桥涵过水能力不足、堵塞排水干道；上游三台子/营盘/九龙河来水持续汇入；7-15破桥清障后主干通道贯通、积水逐步消退。村支书韩庆玉"),
    dict(evidence_id="G-04", location_name="兴隆台街道101国道沿线高标准农田(大营子/大屯/兴光/单家等)", latitude=42.06871,
         longitude=123.31036, date="2026-07-14", evidence_type="G3_official_aggregate",
         waterlogging_observed="yes", water_depth="unknown", affected_area_mu=None, crop="玉米/水稻",
         intervention="unknown", source_id="SRC-LN-GOV-2026-0717|SRC-SY-NYJ-2026-GBZNT",
         spatial_accuracy_m=3000, confidence="medium",
         notes="灾情综述与2026高标准农田项目(1.55万亩)空间对象一致；坐标用兴光村OSM节点"),
    dict(evidence_id="G-05", location_name="虎石台街道（小区/道路内涝）", latitude=42.01510, longitude=123.53126,
         date="2026-07-13", evidence_type="G2_official", waterlogging_observed="yes",
         water_depth="unknown", affected_area_mu=None, crop="非农田为主", intervention="撤离/帮扶",
         source_id="SRC-NSY-GOV-2026-0714", spatial_accuracy_m=3000, confidence="medium",
         notes="官方通报内涝；以居民区/道路为主，农田证据弱"),
    dict(evidence_id="G-06", location_name="马刚街道（涉险转移）", latitude=42.02371, longitude=123.63674,
         date="2026-07-13", evidence_type="G2_official", waterlogging_observed="unknown",
         water_depth="unknown", affected_area_mu=None, crop="unknown", intervention="转移235户423人",
         source_id="SRC-NSY-GOV-2026-0715", spatial_accuracy_m=4000, confidence="low",
         notes="为人员涉险转移，未明确农田渍涝 → waterlogging_observed=unknown（不作正样本）"),
    dict(evidence_id="G-07", location_name="蒲河主干（道路积水9处）", latitude=42.05000, longitude=123.55000,
         date="2026-07-14", evidence_type="G2_official_line", waterlogging_observed="yes",
         water_depth="unknown", affected_area_mu=None, crop="n/a", intervention="无人机监测",
         source_id="SRC-SY-GOV-2026-0715-PUHE", spatial_accuracy_m=5000, confidence="medium",
         notes="线状河道/道路积水，非农田田块；坐标为蒲河近似位置"),
    dict(evidence_id="G-08", location_name="兴隆台街道3行政村（雨后巡查：无积水）", latitude=42.06251,
         longitude=123.35339, date="2026-07-17", evidence_type="G2_official_post_intervention",
         waterlogging_observed="no_after_drainage", water_depth="0", affected_area_mu=None, crop="玉米/水稻",
         intervention="已排涝", source_id="SRC-SY-RURAL-2026-0721", spatial_accuracy_m=5000, confidence="medium",
         notes="**事件后、且已排涝**的观测 → 不得当作“负样本/不易涝”，属 post-treatment 观测"),
    # ---- 第二轮补充（2026-09-23）----
    dict(evidence_id="G-09", location_name="兴隆台街道十二家子村（通州路段）", latitude=42.06251, longitude=123.35339,
         date="2026-07-14", evidence_type="G2_media", waterlogging_observed="yes",
         water_depth="unknown", affected_area_mu=None, crop="玉米/水稻",
         intervention="2台钩机+区交通局工程车;人工摸查探路+机械作业打通淤堵管口",
         source_id="SRC-AGRI-CN-20260716", spatial_accuracy_m=5000, confidence="medium",
         notes="7-14凌晨雨势加剧，农田受淹告急，积水导致路面塌陷风险；管口深藏路基底积水中需人工摸查。坐标用街道中心近似"),
    dict(evidence_id="G-10", location_name="兴隆台街道高标准农田片(大营子村/孟家台村/石佛一村/石佛二村)", latitude=42.06871,
         longitude=123.31036, date="2026-07-14", evidence_type="G2_media_positive_control",
         waterlogging_observed="yes", water_depth="unknown", affected_area_mu=None, crop="水稻/玉米",
         intervention="村书记带头、两委分片包保、逐地块逐沟渠巡查排险；大喇叭+村微信群预警",
         source_id="SRC-AGRI-CN-20260716", spatial_accuracy_m=4000, confidence="medium",
         notes="★★关键对照：报道原文“大营子村、孟家台村、石佛一村、石佛二村等高标准农田也正在经受这场暴雨的检验”+“积水及时排出，水田中水稻依然挺立”→ 同街道内高标农田片区排水明显更快（≤2天，见 03_clean/disaster/waterlogging_duration_2026.csv）。⚠️官方正面口径、非独立观测；waterlogging_observed 取 yes 是为兼容 95_p4r_stability_map 的精确匹配，“快速排出”的信息见 notes 与渍涝历时表"),
    dict(evidence_id="G-11", location_name="新城子街道北四家子村(八间房村排水站南侧水田区内涝区)", latitude=42.05190, longitude=123.51407,
         date="2026-07-13", evidence_type="G2_media", waterlogging_observed="yes",
         water_depth=">1m", affected_area_mu=8000, crop="水稻(即将抽穗)/玉米(生长关键期)",
         intervention="12台8寸泵(2台大功率泵车+50泵+3组8寸管+应急排水车);7-18下午排净;7-25完成清淤复产",
         source_id="SRC-SYD-2026-0814", spatial_accuracy_m=5000, confidence="medium",
         notes="与G-02同一内涝区(八间房村排水站南侧)，报道主体为北四家子村(村支书岳德厚)与村民送锦旗；给出完整时序：7-14初排效果不佳→7-15增援→7-18下午排净→7-25清淤复产完成→8-13送锦旗"),
]


def main():
    df = pd.DataFrame(ROWS)
    df["crop_is_corn_known"] = np.where(df.crop.str.contains("玉米"), "possible", "no")
    # ★ 契约对齐：M2_ground_evidence 要求字段 `location`。
    #   本表历史上用 location_name；86_p4_figures.py 仍在用该名，
    #   故**保留原列并新增同值别名列 location**，避免破坏下游绘图。
    df["location"] = df["location_name"]
    df.to_csv(os.path.join(M2, "labels", "ground_evidence_points.csv"), index=False, encoding="utf-8-sig")

    n_total = len(df)
    g1 = int((df.evidence_type == "G1").sum())
    g2 = int(df.evidence_type.str.startswith("G2").sum())
    g3 = int(df.evidence_type.str.startswith("G3").sum())
    pos_yes = int((df.waterlogging_observed == "yes").sum())
    pos_unknown = int((df.waterlogging_observed == "unknown").sum())
    negatives = int((df.waterlogging_observed == "no").sum())
    max_err = int(df.spatial_accuracy_m.max())

    with open(os.path.join(M2, "labels", "LABEL_AUDIT.md"), "w", encoding="utf-8") as f:
        f.write(f"""# LABEL_AUDIT.md — 标签结构审计（P4-35）

| 项 | 值 |
|---|---|
| 证据点总数 | {n_total} |
| **G1（精确位置 + 官方明确受淹）** | **{g1}** |
| G2（村/街道级官方，无精确田块） | {g2} |
| G3（权威媒体/官方聚合，可大致定位） | {g3} |
| G4（遥感疑似） | 0（本轮未生成可用逐单元阈值标签） |
| G5（模型推断） | 不计入 ground truth |
| 明确“有渍涝”证据 | {pos_yes} |
| waterlogging=unknown（如仅人员转移） | {pos_unknown} |
| **明确“无渍涝”可靠负样本** | **{negatives}** |
| 最大空间定位误差 | ≈{max_err/1000:.1f} km |

## 关键结论
1. **无 G1（精确田块级）正样本**；正样本均为 **G2/G3（村/街道级）**，空间误差 **3–5 km**。
2. **没有可靠负样本**：
   - 新闻未报道 ≠ 无积水（§33），**不得**把未报道网格设为 0；
   - 唯一的“无积水”记录（G-08）是**事件后且已排涝**的结果 → 属 **post-treatment**，不可作负样本。
3. 因此**不具备监督二分类建模条件**（正样本粗糙、负样本缺失）。
4. 唯一可用的“对照”是**全区背景分布**（背景抽样），适合 presence-background / 物理易感性思路。
5. **（第二轮补充 2026-09-23）** 新增 G-09/G-10/G-11 与渍涝历时表后，出现了“过程对照”但**仍是正样本**：
   G-10（高标农田片，≤2天排净）与 G-03（新民村，4天）同属兴隆台街道，
   可用于“排水条件 → 历时”的机制分析，**但不得当作负样本**。

## 第二轮补充（2026-09-23）

新增 G-09 / G-10 / G-11（8 → 11 条），并细化 G-03：

- **G-09** 十二家子村（通州路段）：**局部淤堵型**内涝，当日打通
- **G-10** 兴隆台街道高标准农田片 4 村：`G2_media_positive_control` —— 同街道内
  **已有高标准农田的片区排水明显更快**（≤2 天），构成“工程条件差异 → 渍涝历时差异”的对照证据
- **G-11** 北四家子村（与 G-02 同一内涝区）：提供了本事件**唯一完整的排涝时序**
- G-03 细化：新民村补 5000 亩 + **桥涵过水能力不足**的工程归因

**新增独立产物**：`03_clean/disaster/waterlogging_duration_2026.csv`
（4 点位 × 4 类机理，**5 / 4 / <1 / ≤2 天**），首次把“渍涝持续时间”由缺口变为可用输入
→ **M3 的暴露剂量可直接取用**。

**结论未变**：G1 仍为 0、可靠负样本仍为 0 → 仍**不具备监督二分类条件**，Route A 不变。

## 路线判定（§36）
> **Route A：证据重建（evidence-based susceptibility reconstruction）**
> —— 不训练监督模型；以**地形—水文易感性 + 多源事件证据叠加**为主。

Reason：ground labels 极少且粗糙；SAR 无历史对照且未定标；排水网络严重不完整（见 `M2_VARIABLE_CAUSAL_ROLE.md`）。
""")
    print(f"[P4] 证据点 {n_total}（G1={g1} G2={g2} G3={g3}）；正={pos_yes} 负={negatives} → **Route A**")
    return df


if __name__ == "__main__":
    main()
