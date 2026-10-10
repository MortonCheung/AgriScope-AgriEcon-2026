#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P4-15/16/17：变量因果角色 / 物理合理性分析 / 透明权重易感性 Baseline / M2R 事件重建 / 风险×置信度。
Route A（证据重建）：不训练监督模型。
"""
import os

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M2 = os.path.join(BASE, "06_models", "M2_waterlogging_spatial")
MARTS = os.path.join(BASE, "04_marts")
SPA = os.path.join(BASE, "05_analysis", "09_spatial_waterlogging")
DS = os.path.join(MARTS, "M2_spatial_dataset.csv")
GE = os.path.join(M2, "labels", "ground_evidence_points.csv")

# 机制方向：+1 表示“越大越易涝”，-1 表示“越大越不易涝”
SUSC = {
    "elevation": -1, "slope": -1, "local_relief": -1, "depression_depth": +1,
    "flow_accumulation": +1, "hand": -1, "twi": +1,
    "dist_mapped_water": +1, "dist_mapped_river": +1, "dist_mapped_drainage": +1,
    "cropland_frac": 0,
}


def zc(x):
    x = np.asarray(x, float)
    m = np.nanmean(x); s = np.nanstd(x)
    return (x - m) / (s if s > 0 else 1.0)


def main():
    g = pd.read_csv(DS)
    ge = pd.read_csv(GE)

    with open(os.path.join(M2, "M2_VARIABLE_CAUSAL_ROLE.md"), "w", encoding="utf-8") as f:
        f.write("""# M2_VARIABLE_CAUSAL_ROLE.md（P4-62）

| 变量 | 因果角色 | 说明 |
|---|---|---|
| elevation, slope, local_relief, depression_depth, flow_accumulation, twi, hand | **PRE-EVENT**（地形） | 事件前已存在；可作预测输入 |
| dist_mapped_drainage / _river / _water / drainage_density | **PRE-EVENT**（排水基础设施） | 基础设施；但 OSM 排水网络**不完整** → 命名用 `mapped_` |
| dist_major_road | **PRE-EVENT**（人工阻水候选） | 仅作候选机制，不预设致涝 |
| soil_clay_pct | **PRE-EVENT**（土壤） | 本轮 **not_available**（SoilGrids 取数失败） |
| cropland_frac | **PRE-EVENT**（土地覆盖） | WorldCover 2021 |
| event_precip_mm, event_max_24h_mm, antecedent_7d/14d | **EVENT**（2026 驱动） | 事件外强迫；本轮为**单网格点 event-wide forcing** |
| delta_vv_pct, vv_after | **POST-EVENT**（遥感） | **不得**作“预测是否会淹”的输入；仅作验证/更新证据 |
| ground evidence（受淹报道） | **POST-EVENT**（地面） | 同上 |
| intervention（12台8寸泵等） | **POST-EVENT** | **严格禁止**作预测输入（post-treatment leakage） |

## 结构拆分（P4-59/64）
- **M2a 自然/结构性易感性**：PRE-EVENT 地形+水系+土壤
- **M2b 2026 事件观测**：EVENT 驱动 + 干预
- **Predictive M2**：PRE-EVENT + EVENT（**不含** POST-EVENT）
- **Reconstruction M2R**：Predictive M2 **之后**再叠加 POST-EVENT（SAR / 地面证据）
""")

    # ---------- 物理合理性：证据点邻域 vs 背景 ----------
    gx = g[["x", "y"]].values
    gv = ge[["evidence_id", "latitude", "longitude", "waterlogging_observed"]].copy()
    # 证据点 UTM 坐标
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)
    gv["X"], gv["Y"] = t.transform(gv.longitude.values, gv.latitude.values)

    pos = gv[gv.waterlogging_observed == "yes"]
    rows = []
    R = 3000.0
    for var, sgn in SUSC.items():
        if sgn == 0:
            continue
        bg = g[var].values.astype(float)
        near_vals = []
        for _, p in pos.iterrows():
            d2 = (gx[:, 0] - p.X) ** 2 + (gx[:, 1] - p.Y) ** 2
            m = d2 <= R ** 2
            if m.sum() > 0:
                near_vals.append(np.nanmean(bg[m]))
        if not near_vals:
            continue
        near_mean = float(np.mean(near_vals)); bg_mean = float(np.nanmean(bg))
        bg_sd = float(np.nanstd(bg))
        rows.append(dict(variable=var, expected_direction=("+" if sgn > 0 else "−"),
                         mean_near_flooded=round(near_mean, 3), mean_background=round(bg_mean, 3),
                         diff=near_mean - bg_mean, z_diff=round((near_mean - bg_mean) / bg_sd, 3),
                         direction_consistent=bool(np.sign(near_mean - bg_mean) == sgn)))
    ph = pd.DataFrame(rows)
    ph.to_csv(os.path.join(SPA, "physical_plausibility.csv"), index=False, encoding="utf-8-sig")
    n_cons = int(ph.direction_consistent.sum())
    with open(os.path.join(SPA, "PHYSICAL_PLAUSIBILITY_ANALYSIS.md"), "w", encoding="utf-8") as f:
        f.write("# PHYSICAL_PLAUSIBILITY_ANALYSIS.md（P4-15/42）\n\n")
        f.write(f"对每个“明确受淹”证据点取 **{R/1000:.0f} km 邻域**的耕地网格均值，与全区耕地背景比较。\n\n")
        f.write(ph.to_string(index=False) + "\n\n")
        f.write(f"## 结论\n- 方向与机制一致的地形/水文变量：**{n_cons}/{len(ph)}**。\n")
        f.write("- 需注意：证据点空间误差 3–5 km，与邻域半径同量级 → 该比较**只能看方向，不能作显著性结论**。\n")
        f.write("- 若多数变量方向一致，说明“地形—水文易感性”思路与真实受淹地点**方向相符**；否则需谨慎。\n")
    print("[P4] 物理合理性方向一致:", n_cons, "/", len(ph))

    # ---------- 透明权重易感性 Baseline ----------
    z = {v: zc(g[v].values) for v in SUSC if SUSC[v] != 0}
    idx = np.mean([SUSC[v] * z[v] for v in z], axis=0)     # 等权+机制方向
    # 归一化到 0-1（百分位）
    rank = pd.Series(idx).rank(pct=True).values
    g["susceptibility"] = rank
    # 数据校准变体：权重 ∝ |mean_near - mean_bg| / sd（透明、可复现）
    w = {r.variable: abs(r.z_diff) for r in ph.itertuples()}
    totw = sum(w.values()) if sum(w.values()) > 0 else 1.0
    idx2 = np.sum([SUSC[v] * z[v] * w.get(v, 0.0) / totw for v in z], axis=0)
    g["susceptibility_calib"] = pd.Series(idx2).rank(pct=True).values

    # ---------- SAR 异常 & 事件暴露 ----------
    dv = g["delta_vv_pct"].values
    thr = np.nanpercentile(dv, 10)
    g["sar_anomaly"] = np.where(np.isfinite(dv), (dv <= thr).astype(int), np.nan)
    g["sar_anomaly"] = g["sar_anomaly"].fillna(0).astype(int)
    g["event_exposure"] = zc(g["event_precip_mm"].values) + zc(g["antecedent_14d_mm"].values)
    g["event_exposure_rank"] = pd.Series(g["event_exposure"]).rank(pct=True).values

    # ---------- M2R 重建（三层融合，透明权重） ----------
    g["evidence_proximity_m"] = [float(min([np.hypot(r.x - X, r.y - Y) for X, Y in zip(gv.X[gv.waterlogging_observed == "yes"],
                                                                                       gv.Y[gv.waterlogging_observed == "yes"])]))
                                 for r in g.itertuples()] if (gv.waterlogging_observed == "yes").any() else np.nan
    prox = np.exp(-g["evidence_proximity_m"].values / 5000.0)          # 5km 尺度
    g["evidence_proximity_score"] = prox
    g["M2R_risk"] = pd.Series(0.5 * g["susceptibility"].values + 0.15 * g["event_exposure_rank"].values
                              + 0.15 * g["sar_anomaly"].values + 0.20 * prox).rank(pct=True).values

    def cls(p):
        return pd.cut(p, [-0.01, 0.5, 0.8, 0.95, 1.01], labels=["Low", "Moderate", "High", "VeryHigh"])
    g["risk_class"] = cls(g["M2R_risk"])

    # 置信度：地形质量（DEM 有值）+ 排水完整度低 + 是否有观测证据
    conf = np.full(len(g), 0.0)
    conf += np.where(np.isfinite(g["elevation"].values), 0.4, 0.0)     # 地形可用
    conf += np.where(g["sar_anomaly"].values == 1, 0.3, 0.0)           # SAR 异常
    conf += np.where(prox > 0.3, 0.3, 0.0)                             # 靠近地面证据
    conf -= 0.2                                                        # 排水网络不完整 → 全局降级
    g["confidence_score"] = np.clip(conf, 0, 1)
    g["confidence_class"] = pd.cut(g["confidence_score"], [-0.01, 0.3, 0.6, 1.01],
                                   labels=["Low", "Medium", "High"])

    g.to_csv(os.path.join(MARTS, "M2_spatial_dataset.csv"), index=False, encoding="utf-8-sig")
    import geopandas as gpd
    gpd.GeoDataFrame(g, geometry=gpd.points_from_xy(g.x, g.y), crs="EPSG:32651").to_file(
        os.path.join(M2, "models", "M2R_reconstruction.gpkg"), driver="GPKG")

    with open(os.path.join(M2, "models", "M2_BASELINE_SPEC.md"), "w", encoding="utf-8") as f:
        f.write(f"""# M2_BASELINE_SPEC.md（P4-16/49/50）

## 方案选择
采用 **方案1（机制方向 + 简单等权）** 为主，另给 **方案2（依证据点差异透明校准）** 作变体。

## 物理易感性 Baseline（M2a / susceptibility）
对参与变量标准化后，按**机制方向**取等权平均，再取百分位→[0,1]：
```
susceptibility_raw = mean( sign_v * z(v) )    # sign 见 M2_VARIABLE_CAUSAL_ROLE 的机制表
susceptibility     = percentile_rank(susceptibility_raw)
```
- 方向：高程↓、坡度↓、局部起伏↓、洼深↑、汇流↑、HAND↓、TWI↑、到水系/排水距离↑  → 更易涝
- **权重未凭感觉设定**：等权 + 机制方向；校准变体权重 = |z_diff(证据点邻域−背景)| 归一化（可复现）

## 2026 事件暴露（Layer B）
`event_exposure` = z(event_precip) + z(antecedent_14d)；**本轮为单 ERA5 网格点 → event-wide forcing**，
空间差异不来自降雨，而来自地形/水文/排水（诚实说明，§23）。

## 观测证据（Layer C）
- `sar_anomaly`：`delta_vv_pct` ≤ 其 P10（显著后向散射下降）；**无历史对照、未定标 → 仅“异常证据”**
- `evidence_proximity_score` = exp(−dist_to_nearest_reported_flood / 5km)

## M2R 重建（三层融合）
```
M2R_risk = percentile_rank( 0.50*susceptibility + 0.15*event_exposure_rank
                          + 0.15*sar_anomaly    + 0.20*evidence_proximity )
```
风险分级：Low/Moderate/High/VeryHigh（按分位）。
置信度：地形可用(0.4) + SAR异常(0.3) + 靠近地面证据(0.3) − 排水网络不完整(0.2)。

> **权重为透明设定，非拟合**；这是 Route A 的“物理启发 + 证据叠加”，**不是监督模型**。
""")
    print("[P4] 易感性/重建完成；risk 分布:\n", g.risk_class.value_counts().to_string())
    print("confidence:\n", g.confidence_class.value_counts().to_string())


if __name__ == "__main__":
    main()
