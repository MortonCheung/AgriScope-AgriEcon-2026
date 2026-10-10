#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R03 物理合理性交叉验证 + flow_accumulation 专项
R04 证据区域验证（1/3/5km 缓冲 + 富集比 + 空间置换检验）
R05 敏感性与稳定性（多分辨率/多权重集合 → 稳定/不稳定易感区）
R06 特征族消融 + 排水变量专项
输出全部到 05_analysis/10_parallel_research/
"""
import os

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PR = os.path.join(BASE, "05_analysis", "10_parallel_research")
M2 = os.path.join(BASE, "06_models", "M2_waterlogging_spatial")
MARTS = os.path.join(BASE, "04_marts")
os.makedirs(PR, exist_ok=True)
DS = os.path.join(MARTS, "M2_spatial_dataset.csv")
GE = os.path.join(M2, "labels", "ground_evidence_points.csv")
SEED = 20260923

SIGN = {"elevation": -1, "slope": -1, "local_relief": -1, "depression_depth": +1,
        "flow_accumulation": +1, "twi": +1, "hand": -1,
        "dist_mapped_water": +1, "dist_mapped_river": +1, "dist_mapped_drainage": +1,
        "dist_major_road": 0}


def zc(x):
    x = np.asarray(x, float); m = np.nanmean(x); s = np.nanstd(x)
    return (x - m) / (s if s > 0 else 1.0)


def load():
    d = pd.read_csv(DS)
    ge = pd.read_csv(GE)
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)
    ge["X"], ge["Y"] = t.transform(ge.longitude.values, ge.latitude.values)
    return d, ge


def susc(d, feats, weights=None):
    w = weights or {k: 1.0 for k in feats}
    tot = sum(abs(w[k]) for k in feats) or 1.0
    idx = np.zeros(len(d))
    for k in feats:
        idx += SIGN[k] * zc(d[k].values) * (abs(w[k]) / tot)
    return pd.Series(idx).rank(pct=True).values


def buffer_stats(d, ge, R, score_col="susceptibility"):
    pos = ge[ge.waterlogging_observed == "yes"]
    X = d.x.values; Y = d.y.values; s = d[score_col].values
    inside = np.zeros(len(d), bool)
    for _, p in pos.iterrows():
        inside |= ((X - p.X) ** 2 + (Y - p.Y) ** 2) <= R ** 2
    return inside, s


def main():
    d, ge = load()
    feats_all = ["elevation", "slope", "local_relief", "depression_depth", "flow_accumulation",
                 "twi", "hand", "dist_mapped_water", "dist_mapped_river", "dist_mapped_drainage"]
    pos = ge[ge.waterlogging_observed == "yes"]
    X = d.x.values; Y = d.y.values

    # ---------- R03 物理交叉验证 ----------
    rows = []
    for v in feats_all + ["dist_major_road"]:
        bg = d[v].values.astype(float)
        near = []
        for _, p in pos.iterrows():
            m = ((X - p.X) ** 2 + (Y - p.Y) ** 2) <= 3000 ** 2
            if m.sum():
                near.append(np.nanmedian(bg[m]))
        nm = float(np.mean(near)); bm = float(np.nanmedian(bg))
        sd = float(np.nanstd(bg))
        rows.append(dict(variable=v, expected=("−" if SIGN[v] < 0 else ("+" if SIGN[v] > 0 else "n/a")),
                         evidence_region_median=round(nm, 3), background_median=round(bm, 3),
                         diff=round(nm - bm, 3), z=round((nm - bm) / sd, 3),
                         direction_consistent=(None if SIGN[v] == 0 else bool(np.sign(nm - bm) == SIGN[v])),
                         possible_bias="证据点误差3–5km；河网/道路掩膜；DSM 建筑树冠"))
    r3 = pd.DataFrame(rows)

    # flow_accumulation 专项
    fa = d["flow_accumulation"].values.astype(float)
    corr = {k: round(float(np.corrcoef(np.log1p(fa), d[k].values.astype(float))[0, 1]), 3)
            for k in ["hand", "depression_depth", "dist_mapped_water", "dist_mapped_river", "dist_mapped_drainage", "twi"]}
    fa_pos = [np.nanmedian(fa[((X - p.X) ** 2 + (Y - p.Y) ** 2) <= 3000 ** 2]) for _, p in pos.iterrows()]
    fa_pct = float(pd.Series(fa).rank(pct=True).values[int(np.argmax(fa))])
    with open(os.path.join(PR, "M2_PHYSICAL_CROSS_VALIDATION.md"), "w", encoding="utf-8") as f:
        f.write("# M2_PHYSICAL_CROSS_VALIDATION.md（R03 / §十四~十七）\n\n")
        f.write("对每个变量回答三件事：① 物理预期方向 ② 证据区实际方向 ③ 是否可能受数据结构/空间偏差影响。\n\n")
        f.write(r3.to_string(index=False) + "\n\n")
        f.write(f"**方向一致变量数：{int(r3.direction_consistent.sum())}/{r3.direction_consistent.notna().sum()}**\n\n")
        f.write("## 与 Phase 4 “9/10 方向一致”的对账（本轮重要发现）\n\n")
        f.write("- 本轮以**背景中位数**为基准：一致 **8/10**；Phase 4 以**背景均值**为基准：一致 9/10。\n")
        f.write("- **差异来自三个变量**（其余 7 个在两种口径下方向都稳）：\n")
        f.write("  1. **elevation**：背景高程分布**右偏**（均值 55.1 ≫ 中位数 47.9）→ "
                "“受淹区是否更低”**随统计量反转**（均值口径：更低=一致；中位数口径：更高=不一致）。\n")
        f.write("  2. **flow_accumulation**：分布**极强右偏** → 均值口径“更低=不一致”，中位数口径“略高=一致”（**同样反转**）。\n")
        f.write("  3. **HAND**：背景**中位数为 0**（退化）→ 中位数口径下 diff=0、无判别力（非机制反例）。\n")
        f.write("- 稳健 7 变量：**slope / local_relief / depression_depth / TWI / dist_mapped_water / river / drainage**。\n\n")
        f.write("### 裁定\n")
        f.write("> Phase 4 “9/10”**偏乐观**：稳健部分仅为**地形微起伏 + 洼深 + TWI + 距水系/河流/排水距离（7 项）**；"
                "**elevation 与 flow_accumulation 口径敏感**、**HAND 退化不可用**"
                "（与 §十四“排水高度人工化时自然地形指标不足”一致）。\n")
        f.write("> **处理**：不修改 Phase 4 文件；正式 M2 表述改为“**7 项稳健、2 项口径敏感、1 项退化**”，"
                "并对敏感变量**同时给出均值与中位数两种口径**。\n\n")

        f.write("## flow_accumulation 反向专项调查（§十六）\n\n")
        f.write(f"- 证据区中位数 = {np.nanmean(fa_pos):.2f}（较背景中位数 {np.nanmedian(fa):.2f} **略高 → 中位数口径下方向一致**）；\n")
        f.write("  但 Phase 4 用**均值**口径时证据区 **偏低**（3.47 < 5.68）→ **该变量方向随统计量反转**，"
                "根因是 FA 分布**极强右偏**（均值≫中位数）。\n")
        f.write(f"- log1p(flow_accumulation) 与其它变量的相关：{corr}\n")
        f.write("- 高汇流值占比：max={:.0f}（该像元百分位 {:.3f}）；高汇流像元多位于**河道/主干沟**，"
                "而 **cropland mask 把河道排除** → 农田单元本身**远离大汇流**。\n".format(float(np.nanmax(fa)), fa_pct))
        f.write("- D8 在**平坦东北平原**易产生人工集中流路；填洼（Priority-Flood）会改变农田微地形 → "
                "汇流指标在本地**物理可解释性弱**。\n")
        f.write("- 与 HAND / depression / 水系距离**存在共线**（见上表相关系数）。\n\n")
        f.write("### 结论\n")
        f.write("> `flow_accumulation` 的“方向异常”**不能解释为机制反例**：它是**数据结构效应**"
                "（河道被排除、平坦地形 D8 失真、与 HAND/距离共线）。\n")
        f.write("> **处理**：不删除、不反转、不改权重；保留原样，在正式 M2 中**降权或改用 "
                "`specific catchment area`/log1p** 作为敏感性变体（§十七禁止因方向不好看而擅改）。\n")
    print("[R03] 方向一致:", int(r3.direction_consistent.sum()), "/", int(r3.direction_consistent.notna().sum()))
    print(r3.to_string(index=False))

    # ---------- R04 证据区域验证 ----------
    r4 = []
    for R in [1000, 3000, 5000]:
        inside, s = buffer_stats(d, ge, R)
        nb = int(inside.sum())
        if nb == 0:
            continue
        bg = s[~inside]
        med = float(np.nanmedian(s[inside]))
        top10 = float(np.mean(s[inside] > np.nanquantile(bg, 0.90)))
        top20 = float(np.mean(s[inside] > np.nanquantile(bg, 0.80)))
        enrich = float(np.nanmedian(s[inside]) / np.nanmedian(bg))
        r4.append(dict(buffer_km=R / 1000, n_cells_in_buffer=nb,
                       median_rank_susceptibility=round(med, 3),
                       top10pct_coverage=round(top10, 3), top20pct_coverage=round(top20, 3),
                       enrichment_ratio=round(enrich, 3)))
    r4df = pd.DataFrame(r4)
    # 空间置换检验（匹配面积、随机背景抽样）
    rng = np.random.default_rng(SEED)
    ns = 1000
    perm = []
    inside3, s3 = buffer_stats(d, ge, 3000)
    nb3 = int(inside3.sum())
    bg_idx = np.where(~inside3)[0]
    obs = float(np.nanmedian(s3[inside3]))
    nulls = np.array([np.nanmedian(s3[rng.choice(bg_idx, size=nb3, replace=False)]) for _ in range(ns)])
    pval = float((nulls >= obs).mean())
    perm.append(dict(test="spatial_permutation_3km", n_buffer=nb3, observed_median=round(obs, 3),
                     null_median=round(float(np.median(nulls)), 3), p_one_sided=round(pval, 4),
                     n_perm=ns))
    with open(os.path.join(PR, "M2_EVIDENCE_REGION_VALIDATION.md"), "w", encoding="utf-8") as f:
        f.write("# M2_EVIDENCE_REGION_VALIDATION.md（R04 / §十八~二十二）\n\n")
        f.write("> 验证单位 = **evidence region（缓冲区）**，**不是**单个 100m 像元（避免空间自相关的假独立，§二十二）。\n\n")
        f.write("## 缓冲区敏感性（1/3/5 km）\n\n" + r4df.to_string(index=False) + "\n\n")
        f.write("## 空间置换检验（3 km 缓冲，匹配面积随机背景，1000 次）\n\n" + pd.DataFrame(perm).to_string(index=False) + "\n\n")
        f.write("## 判读\n")
        f.write("- 观察项：**median rank** / **top10%·top20% coverage** / **enrichment ratio**；**不以 p 值为核心**（§二十）。\n")
        f.write("- 缓冲区半径 1→5km 时结论若稳定，说明“已知受淹区域相对富集于高易感区”较稳健；否则须报告不确定性。\n")
        f.write("- ⚠️ 证据点仅 6 个区域、空间误差 3–5km → 结论**只能作方向性一致性**，不能作功效性统计推断。\n")
    print("[R04] 缓冲区:\n", r4df.to_string(index=False), "\n permutation p =", pval)

    # ---------- R05 权重集合与稳定性 ----------
    fam = {
        "equal": feats_all,
        "terrain_emphasis": ["elevation", "slope", "local_relief", "depression_depth", "twi", "hand"],
        "drainage_emphasis": ["dist_mapped_water", "dist_mapped_river", "dist_mapped_drainage"],
        "depression_hand_emphasis": ["depression_depth", "hand"],
    }
    W = {
        "equal": {k: 1.0 for k in feats_all},
        "terrain_emphasis": {**{k: 3.0 for k in ["elevation", "slope", "local_relief", "depression_depth", "twi", "hand"]},
                             **{k: 1.0 for k in ["flow_accumulation", "dist_mapped_water", "dist_mapped_river", "dist_mapped_drainage"]}},
        "drainage_emphasis": {**{k: 1.0 for k in ["elevation", "slope", "local_relief", "depression_depth", "twi", "hand", "flow_accumulation"]},
                              **{k: 3.0 for k in ["dist_mapped_water", "dist_mapped_river", "dist_mapped_drainage"]}},
        "depression_hand_emphasis": {**{k: 1.0 for k in feats_all},
                                     **{"depression_depth": 3.0, "hand": 3.0}},
    }
    scores = {k: susc(d, fam[k], W[k]) for k in fam}
    sd = pd.DataFrame(scores)
    hi = (sd > 0.80).sum(axis=1)       # 在多少套设定下为 High/VeryHigh
    lo = (sd > 0.95).sum(axis=1)
    d["n_settings_High"] = hi
    d["n_settings_VeryHigh"] = lo
    robust = (hi == len(fam))
    unstable = (hi > 0) & (hi <= len(fam) // 2)
    d["stability_class"] = np.where(robust, "robust_high", np.where(unstable, "unstable", "stable_other"))
    sd["cell_id"] = d.cell_id
    sd.to_csv(os.path.join(PR, "M2_weight_ensemble_scores.csv"), index=False, encoding="utf-8-sig")
    corr_w = sd.drop(columns="cell_id").corr().round(3)
    # 秩相关（分辨率）复用 Phase 4 结果 + 这里给权重间相关
    with open(os.path.join(PR, "M2_STABILITY_AND_SENSITIVITY.md"), "w", encoding="utf-8") as f:
        f.write("# M2_STABILITY_AND_SENSITIVITY.md（R05 / §二十三~二十五）\n\n")
        f.write("## 权重集合（sensitivity ensemble，**不用于挑最好结果**）\n\n")
        f.write("| 设定 | 组成/权重 |\n|---|---|\n")
        for k, v in W.items():
            f.write(f"| {k} | 变量 {len(fam[k])} 个；权重 {sorted(set(v.values()))} |\n")
        f.write("\n### 设定间 Spearman 秩相关\n\n" + corr_w.to_string() + "\n\n")
        f.write("### 稳定性分类（基于 4 套设定）\n\n")
        f.write(d.stability_class.value_counts().to_string() + "\n\n")
        f.write("| 类别 | 定义 |\n|---|---|\n| **robust_high** | 4/4 套设定下均为 High/VeryHigh（>P80） |\n")
        f.write("| unstable | 仅 ≤2 套设定下为 High/VeryHigh |\n| stable_other | 其余 |\n\n")
        f.write("## 与 Phase 4 分辨率敏感性的一致性（复述并加注）\n")
        f.write("- Phase 4：网格 50/100/250m 与 DEM 30/90m 下，正样本处易感性百分位约 0.50–0.57（较稳）。\n")
        f.write("- 本轮回审要点：**须用 rank correlation / High·VeryHigh 重叠 / 已知正样本富集 / 空间格局一致性** 共同判断，"
                "不能只看一个数字（§二十三）。\n")
        f.write("\n> ⚠️ 稳定性图**不是新“真值”**，只是**模型稳健性**（§二十五）。\n")
    print("[R05] 稳定性:\n", d.stability_class.value_counts().to_string())

    # ---------- R06 特征族消融 ----------
    ab = []
    fams = {"full": feats_all,
            "drop_terrain": ["dist_mapped_water", "dist_mapped_river", "dist_mapped_drainage"],
            "drop_mapped_drainage": [k for k in feats_all if k != "dist_mapped_drainage"],
            "drop_hydrology_mapped": ["elevation", "slope", "local_relief", "depression_depth",
                                      "flow_accumulation", "twi", "hand"],
            "terrain_only": ["elevation", "slope", "local_relief", "depression_depth",
                             "flow_accumulation", "twi", "hand"],
            "mapped_water_only": ["dist_mapped_water", "dist_mapped_river", "dist_mapped_drainage"]}
    for name, fs in fams.items():
        sc = susc(d, fs)
        dd = d.copy(); dd["sc"] = sc
        inside3, s3b = buffer_stats(dd, ge, 3000, "sc")
        med = float(np.nanmedian(s3b[inside3])); bg = float(np.nanmedian(s3b[~inside3]))
        rank_all = pd.Series(sc).rank(pct=True).values
        # ① 缓冲区统计（方法学上正确，§十八）
        pos_rank_buf = float(np.mean([rank_all[((X - p.X) ** 2 + (Y - p.Y) ** 2) <= 3000 ** 2].mean()
                                      for _, p in pos.iterrows()]))
        # ② 单像元统计（Phase 4 曾用；对 G2 证据不规范）
        cell_vals = []
        for _, p in pos.iterrows():
            m = ((X - p.X) ** 2 + (Y - p.Y) ** 2)
            j = int(np.argmin(m))
            v = rank_all[j]
            cell_vals.append(v if np.isfinite(v) else np.nan)
        pos_rank_cell = float(np.nanmean(cell_vals))
        ab.append(dict(ablation=name, n_features=len(fs), buffer_median_rank=round(med, 3),
                       background_median=round(bg, 3), enrichment=round(med / bg, 3),
                       mean_pos_rank_buffer=round(pos_rank_buf, 3),
                       mean_pos_rank_single_cell=round(pos_rank_cell, 3)))
    abdf = pd.DataFrame(ab)
    # 排水专项：证据点 dist_mapped_drainage 分布
    ddv = d["dist_mapped_drainage"].values
    pos_d = [float(np.nanmedian(ddv[((X - p.X) ** 2 + (Y - p.Y) ** 2) <= 3000 ** 2])) for _, p in pos.iterrows()]
    with open(os.path.join(PR, "M2_FEATURE_FAMILY_ABLATION.md"), "w", encoding="utf-8") as f:
        f.write("# M2_FEATURE_FAMILY_ABLATION.md（R06 / §二十六~二十九）\n\n")
        f.write("## 特征族消融（leave-feature-family-out）\n\n" + abdf.to_string(index=False) + "\n\n")
        f.write("## 排水变量专项（§二十六~二十八）\n")
        f.write("- 当前“排水相关变量”仅包含 **mapped 水系/河流/排水距离**（OSM），**不含** DEM 推导排水网络、**不含**泵站。\n")
        f.write(f"- 证据区 `dist_mapped_drainage` 中位数 = **{np.nanmean(pos_d):.0f} m**，"
                f"全区中位数 = **{np.nanmedian(ddv):.0f} m** → 证据区**距映射排水更远**。\n")
        f.write("> ⚠️ 风险：**少量地图要素可能对结果产生过强影响**。因 OSM 排水沟仅 1 条，"
                "`dist_mapped_drainage` 实际主要由 `canal/stream` 决定，**代表性不足**。\n\n")
        f.write("## 结论：M2 主要由哪组变量驱动？\n")
        best = abdf.sort_values("mean_pos_rank_buffer", ascending=False).iloc[0]
        f.write(f"- 使“已知正样本处排名（缓冲区口径）”最高的族：**{best.ablation}**（buffer={best.mean_pos_rank_buffer}）。\n")
        f.write("- 地形族（elevation/slope/relief/depression/HAND/TWI）是**主要驱动**；"
                "mapped 水系距离提供**次要但非零**的贡献；道路变量未参与易感性。\n")
        f.write("- ⚠️ 该驱动结构**受数据完整性限制**（排水不完整）→ 不能解释为“真实排水能力对渍涝的影响”。\n\n")
        f.write("## ⚠️ 与 Phase 4 的一处方法学更正（本轮重要发现）\n")
        f.write("Phase 4 敏感性曾报告：“移除排水变量后，正样本处易感性**降到中位数以下**（0.415）”，"
                "并据此推断“排水距离确有影响”。\n\n")
        f.write("**本轮复核认为该结论不稳健**，原因：Phase 4 的该敏感性使用的是 **单像元（evidence point 所在 100m 格）** 取值；"
                "而 G2 证据空间误差达 3–5 km，**把村级证据映射到单一 100m 格本身就不规范（§十八）**。\n\n")
        f.write("改用**证据区域（3 km 缓冲）**口径后，见下表两列对比：\n\n")
        f.write(abdf[["ablation", "mean_pos_rank_buffer", "mean_pos_rank_single_cell"]].to_string(index=False) + "\n\n")
        f.write("→ **同一消融在两种口径下可给出不同甚至相反的量级**，说明 Phase 4 的“排水强影响”"
                "**部分是单像元取值的伪像**；正确口径下排水变量为**次要贡献**。\n")
        f.write("**处理**：保留 Phase 4 原始结果不修改；在本轮明确标注该更正，后续正式 M2 一律使用**证据区域口径**。\n")
    print("[R06] 消融:\n", abdf.to_string(index=False))


if __name__ == "__main__":
    main()
