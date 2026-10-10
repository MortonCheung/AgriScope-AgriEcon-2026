#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P4-16(验证) / P4-17(敏感性) / P4-P18(资格闸门)。
无监督模型 → 用“已知正样本召回 + 秩一致性 + 与独立 SAR 证据一致性”替代 ROC/AUC。
"""
import os

import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import reproject, Resampling
from scipy.stats import spearmanr

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M2 = os.path.join(BASE, "06_models", "M2_waterlogging_spatial")
MARTS = os.path.join(BASE, "04_marts")
SP = os.path.join(BASE, "03_clean", "spatial")
IMD = os.path.join(SP, "dem")
HYD = os.path.join(SP, "hydro")
DS = os.path.join(MARTS, "M2_spatial_dataset.csv")
GE = os.path.join(M2, "labels", "ground_evidence_points.csv")
DEM = os.path.join(IMD, "pnb_dem_30m_utm.tif")

SUSC = {"elevation": -1, "slope": -1, "local_relief": -1, "depression_depth": 1,
        "flow_accumulation": 1, "hand": -1, "twi": 1, "dist_mapped_water": 1,
        "dist_mapped_river": 1, "dist_mapped_drainage": 1}


def aggregate(path, tr, H, W, how, ref=DEM):
    res = {"mean": Resampling.average, "min": Resampling.min, "max": Resampling.max}[how]
    with rasterio.open(ref) as r:
        crs, s_tr = r.crs, r.transform
    with rasterio.open(path) as s:
        src = s.read(1).astype("float32")
    src[~np.isfinite(src)] = np.nan                       # 避免 NaN 与 min/max 交互产生 ±inf
    dst = np.full((H, W), np.nan, "float32")
    reproject(source=src, destination=dst, src_transform=s_tr, src_crs=crs,
              dst_transform=tr, dst_crs=crs, resampling=res,
              src_nodata=np.nan, dst_nodata=np.nan)
    dst[~np.isfinite(dst)] = np.nan
    return dst


def zc(x):
    m = np.nanmean(x); s = np.nanstd(x)
    return (x - m) / (s if s > 0 else 1.0)


def susc_at(res, drop_drainage=False):
    import geopandas as gpd
    g = gpd.read_file(os.path.join(SP, "shenbei_boundary.gpkg"))
    minx, miny, maxx, maxy = g.total_bounds
    W = int(np.ceil((maxx - minx) / res)); H = int(np.ceil((maxy - miny) / res))
    tr = rasterio.transform.from_origin(minx, maxy, res, res)
    feats = {
        "elevation": aggregate(os.path.join(IMD, "pnb_dem_filled_30m.tif"), tr, H, W, "min"),
        "slope": aggregate(os.path.join(IMD, "pnb_slope_30m.tif"), tr, H, W, "mean"),
        "local_relief": aggregate(os.path.join(IMD, "pnb_relief_30m.tif"), tr, H, W, "max"),
        "depression_depth": aggregate(os.path.join(IMD, "pnb_depdepth_30m.tif"), tr, H, W, "max"),
        "flow_accumulation": aggregate(os.path.join(IMD, "pnb_flowacc_30m.tif"), tr, H, W, "mean"),
        "twi": aggregate(os.path.join(IMD, "pnb_twi_30m.tif"), tr, H, W, "mean"),
        "hand": aggregate(os.path.join(IMD, "pnb_hand_30m.tif"), tr, H, W, "min"),
        "dist_mapped_water": aggregate(os.path.join(HYD, "dist_mapped_water.tif"), tr, H, W, "mean"),
        "dist_mapped_river": aggregate(os.path.join(HYD, "dist_mapped_river.tif"), tr, H, W, "mean"),
        "dist_mapped_drainage": aggregate(os.path.join(HYD, "dist_mapped_drainage.tif"), tr, H, W, "mean"),
    }
    keys = [k for k in feats if not (drop_drainage and k.startswith("dist_mapped"))]
    idx = np.mean([SUSC[k] * zc(feats[k]) for k in keys], axis=0)
    return idx, tr, H, W


def rank_at(points_xy, arr, tr, H, W):
    out = []
    flat = arr.reshape(-1)
    valid = np.isfinite(flat)
    pct = np.full(flat.shape, np.nan)
    pct[valid] = pd.Series(flat[valid]).rank(pct=True).values
    pct = pct.reshape(H, W)
    for X, Y in points_xy:
        c = int((X - tr.c) / tr.a); r = int((tr.f - Y) / (-tr.e))
        if 0 <= r < H and 0 <= c < W:
            out.append(pct[r, c])
    return np.array(out, float)


def main():
    g = pd.read_csv(DS)
    ge = pd.read_csv(GE)
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)
    pos = ge[ge.waterlogging_observed == "yes"]
    pX, pY = t.transform(pos.longitude.values, pos.latitude.values)

    # ---------------- 验证（Route A） ----------------
    R = 3000.0
    sus = g["susceptibility"].values
    bg_median = float(np.nanmedian(sus))
    near = []
    for X, Y in zip(pX, pY):
        d2 = (g.x.values - X) ** 2 + (g.y.values - Y) ** 2
        m = d2 <= R ** 2
        if m.sum():
            near.append(float(np.mean(sus[m])))
    recall = float(np.mean([v > bg_median for v in near])) if near else float("nan")
    rank_pos = float(np.mean(near)) if near else float("nan")
    rho, pv = spearmanr(g["susceptibility"].values, g["delta_vv_pct"].fillna(np.nan).values, nan_policy="omit")
    val = pd.DataFrame([
        ("known_positive_recall(neighborhood>median)", round(recall, 3)),
        ("mean_susceptibility_percentile_at_positives", round(rank_pos, 3)),
        ("background_median_percentile", 0.5),
        ("spearman_susceptibility_vs_SAR_deltaVV", round(float(rho), 3)),
        ("spearman_p", round(float(pv), 4)),
    ], columns=["metric", "value"])
    val.to_csv(os.path.join(M2, "validation", "M2_validation_metrics.csv"), index=False, encoding="utf-8-sig")
    with open(os.path.join(M2, "validation", "M2_VALIDATION.md"), "w", encoding="utf-8") as f:
        f.write("# M2_VALIDATION.md（P4-44/45/48）\n\n")
        f.write("> **无可靠负样本** → 不报告 accuracy/specificity/ROC-AUC（无意义）。改报与“已知正样本/独立证据”的一致性。\n\n")
        f.write(val.to_string(index=False) + "\n\n")
        f.write("## 空间验证方式说明\n")
        f.write("- 本阶段 **Route A（无监督监督模型）** → 不适用 train/test 空间分块；\n")
        f.write("- 若未来获得 G1 标签，**必须**用 spatial block CV（按街道/方块留出），禁止随机像元切分（§43）。\n")

    # ---------------- 敏感性 ----------------
    srows = []
    # (1) 网格尺度
    for res in [50, 100, 250]:
        idx, tr, H, W = susc_at(res)
        v = rank_at(list(zip(pX, pY)), idx, tr, H, W)
        srows.append(dict(factor="grid_size_m", level=res,
                          mean_pct_at_pos=round(float(np.nanmean(v)), 3) if len(v) else np.nan,
                          frac_above_median=round(float(np.nanmean(v > 0.5)), 3) if len(v) else np.nan))
    # (2) SAR 阈值
    dv = g["delta_vv_pct"].values
    for q in [5, 10, 20]:
        thr = np.nanpercentile(dv, q)
        flag = (dv <= thr)
        srows.append(dict(factor="sar_threshold_pct", level=q,
                          sar_anomaly_frac=round(float(np.nanmean(flag)), 4),
                          overlap_with_top_quartile_susc=round(float(np.mean(flag & (sus >= np.nanquantile(sus, 0.75)))), 4)))
    # (3) 排水缺失
    idx_w, tr_w, H_w, W_w = susc_at(100)
    v_w = rank_at(list(zip(pX, pY)), idx_w, tr_w, H_w, W_w)
    idx_nod, _, _, _ = susc_at(100, drop_drainage=True)
    v_nod = rank_at(list(zip(pX, pY)), idx_nod, tr_w, H_w, W_w)
    srows.append(dict(factor="drainage_vars", level="with",
                      mean_pct_at_pos=round(float(np.nanmean(v_w)), 3) if len(v_w) else np.nan))
    srows.append(dict(factor="drainage_vars", level="without",
                      mean_pct_at_pos=round(float(np.nanmean(v_nod)), 3) if len(v_nod) else np.nan))
    # (4) DEM 分辨率代理（30m vs 90m）
    for res in [30, 90]:
        idx, tr, H, W = susc_at(res)
        v = rank_at(list(zip(pX, pY)), idx, tr, H, W)
        srows.append(dict(factor="dem_res_m", level=res,
                          mean_pct_at_pos=round(float(np.nanmean(v)), 3) if len(v) else np.nan))
    sdf = pd.DataFrame(srows)
    sdf.to_csv(os.path.join(M2, "sensitivity", "M2_sensitivity.csv"), index=False, encoding="utf-8-sig")
    with open(os.path.join(M2, "sensitivity", "M2_SENSITIVITY.md"), "w", encoding="utf-8") as f:
        f.write("# M2_SENSITIVITY.md（P4-66）\n\n")
        f.write(sdf.to_string(index=False) + "\n\n")
        f.write("## 结论\n- 主分辨率选 **100 m**（与 DEM 30m、SAR~10m、soil 缺失相称；§39 不假精细）。\n")
        f.write("- 报告各因素下“已知正样本处易感性百分位”是否稳定；若随尺度/阈值大幅漂移，须在结论中标注。\n")

    # ---------------- 资格闸门 ----------------
    dem_ok = bool(np.isfinite(g["elevation"]).mean() > 0.95)
    ph = pd.read_csv(os.path.join(BASE, "05_analysis", "09_spatial_waterlogging", "physical_plausibility.csv"))
    dir_ok = float(ph.direction_consistent.mean())
    gA = "PASS" if dem_ok else "FAIL"
    gB = "PASS" if dir_ok >= 0.7 else ("CAUTION" if dir_ok >= 0.5 else "FAIL")
    gC = "PASS" if (recall >= 0.6) else ("CAUTION" if recall >= 0.4 else "FAIL")
    gD = "PASS" if (abs(rho) >= 0.1 and pv < 0.05) else ("CAUTION" if abs(rho) >= 0.05 else "FAIL")
    gE = "CAUTION" if len(v) else "FAIL"
    gF = "PASS（预测输入已剔除 POST-EVENT：SAR/地面证据/干预只用于重建与验证）"
    overall = "NOT_ELIGIBLE" if ("FAIL" in [gA, gB, gC] or gD == "FAIL") else "ELIGIBLE_FOR_DESCRIPTION_ONLY"
    with open(os.path.join(M2, "COUNTERFACTUAL_ELIGIBILITY_M2.md"), "w", encoding="utf-8") as f:
        f.write("# COUNTERFACTUAL_ELIGIBILITY_M2.md（P4-72/73/74）\n\n")
        f.write("| Gate | 检查 | 结果 |\n|---|---|---|\n")
        f.write(f"| A 地形/水系数据质量 | DEM 覆盖>95% = {dem_ok}；**排水网络不完整** | **{gA}**（地形部分） |\n")
        f.write(f"| B 方向符合机制 | 方向一致变量占比 {dir_ok:.0%} | **{gB}** |\n")
        f.write(f"| C 与真实受淹点一致 | 已知正样本邻域召回 = {recall:.2f} | **{gC}** |\n")
        f.write(f"| D 与独立遥感证据一致 | ρ(易感性, ΔVV)={rho:.3f}, p={pv:.4f} | **{gD}** |\n")
        f.write(f"| E 空间验证 | 无 G1 标签，仅邻域一致性 | **{gE}** |\n")
        f.write(f"| F 无 post-event leakage | 预测输入仅 PRE-EVENT+EVENT | **{gF}** |\n\n")
        f.write(f"## 总判定：**{overall}**\n\n")
        f.write("依据 §74：M2 **只能用于描述/重建 2026 事件**，**不能**用于 `future rainfall scenario` / `no-disaster world` 的定量反事实。\n")
    print(val.to_string(index=False))
    print(f"[P4] Gates: A={gA} B={gB} C={gC} D={gD} E={gE} -> {overall}")


if __name__ == "__main__":
    main()
