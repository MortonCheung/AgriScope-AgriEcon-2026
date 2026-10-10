#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P4-79~八十一：M2 正式研究图件（含比例尺/指北针/CRS/图例/来源）。"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M2 = os.path.join(BASE, "06_models", "M2_waterlogging_spatial")
FIG = os.path.join(BASE, "08_figures", "M2")
SP = os.path.join(BASE, "03_clean", "spatial")
MARTS = os.path.join(BASE, "04_marts")
os.makedirs(FIG, exist_ok=True)
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "Heiti TC", "PingFang SC", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False
CRS_TXT = "CRS: EPSG:32651 (UTM 51N, m)"
RES100 = 100.0

DS = pd.read_csv(os.path.join(MARTS, "M2_spatial_dataset.csv"))
H100 = int(DS.row.max()) + 1; W100 = int(DS.col.max()) + 1
import geopandas as gpd
BND = gpd.read_file(os.path.join(SP, "shenbei_boundary.gpkg"))
minx, miny, maxx, maxy = BND.total_bounds
EXT100 = [minx, minx + W100 * RES100, miny, miny + H100 * RES100]


def grid_arr(col):
    a = np.full((H100, W100), np.nan, "float32")
    a[DS.row.values, DS.col.values] = DS[col].values
    return a


def decorate(ax, title, source, scale_km=5):
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
    L = (x1 - x0) * 0.22
    ax.plot([x0 + L * 0.05, x0 + L * 0.05 + scale_km * 1000], [y0 + (y1 - y0) * 0.05] * 2, "k-", lw=3)
    ax.text(x0 + L * 0.05 + scale_km * 500, y0 + (y1 - y0) * 0.075, f"{scale_km} km", ha="center", fontsize=7)
    ax.annotate("N", xy=(x1 - (x1 - x0) * 0.06, y1 - (y1 - y0) * 0.10), xytext=(x1 - (x1 - x0) * 0.06, y1 - (y1 - y0) * 0.17),
                ha="center", fontsize=9, arrowprops=dict(arrowstyle="-|>", color="k"))
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("Easting (m)"); ax.set_ylabel("Northing (m)")
    ax.text(0.01, -0.14, f"{CRS_TXT} | 数据来源: {source}", transform=ax.transAxes, fontsize=7)


def plot30(path, title, source, cmap="terrain", fname=None):
    with rasterio.open(path) as s:
        a = s.read(1); b = s.bounds
    fig, ax = plt.subplots(figsize=(8, 7))
    im = ax.imshow(a, extent=[b.left, b.right, b.bottom, b.top], cmap=cmap, origin="upper")
    plt.colorbar(im, ax=ax, shrink=0.8)
    decorate(ax, title, source, 5)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, fname), dpi=140, bbox_inches="tight"); plt.close(fig)


def main():
    bnd = BND.boundary
    # F1 研究区 + 耕地
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.imshow(np.where(np.isfinite(grid_arr("cropland_frac")), grid_arr("cropland_frac"), np.nan),
              extent=EXT100, cmap="Greens", vmin=0.5, vmax=1, origin="upper")
    bnd.plot(ax=ax, facecolor="none", edgecolor="red", lw=1.2)
    decorate(ax, "图1 沈北新区研究区与耕地（WorldCover 2021, 100m）", "边界:DataV | 耕地:ESA WorldCover 10m", 10)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "F1_study_area_cropland.png"), dpi=140, bbox_inches="tight"); plt.close(fig)

    plot30(os.path.join(SP, "dem", "pnb_dem_filled_30m.tif"), "图2 DEM（Copernicus 30m, 已填洼）",
           "Copernicus DEM GLO-30", "terrain", "F2_DEM.png")
    plot30(os.path.join(SP, "dem", "pnb_depdepth_30m.tif"), "图3 洼地深度 depression depth（m）",
           "Copernicus DEM GLO-30", "YlOrRd", "F3_depression.png")
    plot30(os.path.join(SP, "dem", "pnb_flowacc_30m.tif"), "图4 汇流累积 flow accumulation（像元数）",
           "Copernicus DEM GLO-30", "Blues", "F4_flowacc.png")

    # F5 水系/道路
    import json
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)
    fig, ax = plt.subplots(figsize=(8, 7))
    bnd.plot(ax=ax, facecolor="#f7fafc", edgecolor="red", lw=1.0)
    for fn, style, lab in [("osm_waterway.json", dict(color="#2b6cb0", lw=1.0), "waterway/water (OSM)"),
                           ("osm_roads.json", dict(color="#718096", lw=0.5), "roads/railway (OSM)")]:
        d = json.load(open(os.path.join(BASE, "02_raw", "spatial", fn), encoding="utf-8"))
        for e in d["elements"]:
            g = e.get("geometry") or []
            if len(g) < 2:
                continue
            X, Y = t.transform([p["lon"] for p in g], [p["lat"] for p in g])
            ax.plot(X, Y, **style)
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([0], [0], color="#2b6cb0", lw=1.5, label="水系/水体 (OSM)"),
                       Line2D([0], [0], color="#718096", lw=1, label="道路/铁路 (OSM)")], fontsize=8, loc="lower left")
    decorate(ax, "图5 水系与道路（OSM）——排水沟渠明显不完整", "OpenStreetMap (OSM)", 10)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "F5_drainage_roads.png"), dpi=140, bbox_inches="tight"); plt.close(fig)

    # F6 事件暴露（常值 → 仅示意）
    fig, ax = plt.subplots(figsize=(8, 7))
    im = ax.imshow(grid_arr("event_precip_mm"), extent=EXT100, cmap="Blues", vmin=200, vmax=240, origin="upper")
    bnd.plot(ax=ax, facecolor="none", edgecolor="red", lw=1.0)
    plt.colorbar(im, ax=ax, shrink=0.8, label="mm")
    decorate(ax, "图6 2026 事件降雨暴露（7-13~14，mm）\n⚠ 单 ERA5 网格点 → event-wide forcing，无空间差异",
             "Open-Meteo ERA5", 10)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "F6_event_exposure.png"), dpi=140, bbox_inches="tight"); plt.close(fig)

    # F7 S1 delta
    fig, axes = plt.subplots(1, 3, figsize=(17, 6))
    for ax, col, ttl, cm in zip(axes, ["vv_before", "vv_after", "delta_vv_pct"],
                                ["事件前 VV (2026-07-06)", "事件后 VV (2026-07-18)", "ΔVV (%)  后−前"],
                                ["gray", "gray", "RdBu_r"]):
        a = grid_arr(col)
        im = ax.imshow(a, extent=EXT100, cmap=cm, origin="upper",
                       vmin=(0 if col != "delta_vv_pct" else -50), vmax=(600 if col != "delta_vv_pct" else 50))
        plt.colorbar(im, ax=ax, shrink=0.75)
        ax.set_title(ttl, fontsize=9); ax.set_xlabel("E"); ax.set_ylabel("N")
    axes[2].text(0.01, -0.13, "Sentinel-1C 同相对轨道(3)descending；未辐射定标、无历史对照 → 仅异常证据", transform=axes[2].transAxes, fontsize=7)
    axes[0].text(0.01, -0.13, CRS_TXT, transform=axes[0].transAxes, fontsize=7)
    fig.suptitle("图7 Sentinel-1 事件前后 VV 与变化（100m）")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "F7_sentinel1.png"), dpi=140, bbox_inches="tight"); plt.close(fig)

    # F8 地面证据
    ge = pd.read_csv(os.path.join(M2, "labels", "ground_evidence_points.csv"))
    fig, ax = plt.subplots(figsize=(8, 7))
    bnd.plot(ax=ax, facecolor="#f7fafc", edgecolor="red", lw=1.0)
    cols = {"yes": "#e53e3e", "unknown": "#dd6b20", "no_after_drainage": "#38a169"}
    for _, r in ge.iterrows():
        X, Y = t.transform(r.longitude, r.latitude)
        ax.scatter(X, Y, s=90, c=cols.get(r.waterlogging_observed, "k"), edgecolor="k", zorder=5)
        ax.annotate(f"{r.evidence_id}\n{r.location_name[:12]}", (X, Y), fontsize=6, xytext=(4, 4), textcoords="offset points")
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([0], [0], marker="o", ls="", mfc=c, mec="k", label=l) for l, c in
                       [("有渍涝证据", "#e53e3e"), ("unknown(仅转移)", "#dd6b20"), ("事后已排净", "#38a169")]],
              fontsize=8, loc="lower left")
    decorate(ax, "图8 真实地面灾情证据点（G2/G3，空间误差3–5km）", "官方通报/权威媒体（见 ground_evidence_points.csv）", 10)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "F8_ground_evidence.png"), dpi=140, bbox_inches="tight"); plt.close(fig)

    # F9/F10/F11 风险图
    for col, ttl, fn, cm in [
        ("susceptibility", "图9 物理易涝性 susceptibility（地形—水文，0-1）", "F9_susceptibility.png", "YlOrRd"),
        ("event_exposure_rank", "图10 2026 事件暴露 rank（降雨+前期湿润）", "F10_event_exposure_rank.png", "PuBu"),
        ("M2R_risk", "图11 M2R 2026 渍涝风险重建（易感性+暴露+SAR+地面证据）", "F11_M2R_risk.png", "YlOrRd")]:
        fig, ax = plt.subplots(figsize=(8, 7))
        im = ax.imshow(grid_arr(col), extent=EXT100, cmap=cm, vmin=0, vmax=1, origin="upper")
        bnd.plot(ax=ax, facecolor="none", edgecolor="red", lw=1.0)
        plt.colorbar(im, ax=ax, shrink=0.8, label="0–1 (percentile)")
        decorate(ax, ttl, "本研究 M2（Route A 物理启发+证据叠加）", 10)
        fig.tight_layout(); fig.savefig(os.path.join(FIG, fn), dpi=140, bbox_inches="tight"); plt.close(fig)

    # F12 风险 × 置信度
    fig, axes = plt.subplots(1, 2, figsize=(15, 6.5))
    for ax, col, ttl, cm in [(axes[0], "M2R_risk", "风险 Risk", "YlOrRd"),
                             (axes[1], "confidence_score", "置信度 Confidence", "viridis")]:
        im = ax.imshow(grid_arr(col), extent=EXT100, cmap=cm, vmin=0, vmax=1, origin="upper")
        plt.colorbar(im, ax=ax, shrink=0.75, label="0–1")
        ax.set_title(f"图12 {ttl}", fontsize=10)
        ax.set_xlabel("Easting (m)"); ax.set_ylabel("Northing (m)")
        bnd.plot(ax=ax, facecolor="none", edgecolor="red", lw=0.8)
    axes[0].text(0.01, -0.13, f"{CRS_TXT} | 风险与置信度分开表达（§55）；来源: 本研究 M2",
                 transform=axes[0].transAxes, fontsize=7)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "F12_risk_confidence.png"), dpi=140, bbox_inches="tight"); plt.close(fig)

    with open(os.path.join(FIG, "FIGURES_README.md"), "w", encoding="utf-8") as f:
        f.write("""# M2 FIGURES_README

| 图 | 文件 | 内容 |
|---|---|---|
| 1 | F1_study_area_cropland.png | 研究区 + 耕地 |
| 2 | F2_DEM.png | DEM（30m 已填洼） |
| 3 | F3_depression.png | 洼地深度 |
| 4 | F4_flowacc.png | 汇流累积 |
| 5 | F5_drainage_roads.png | 水系/道路（OSM，排水不完整） |
| 6 | F6_event_exposure.png | 2026 事件降雨暴露（event-wide） |
| 7 | F7_sentinel1.png | S1 before/after/delta |
| 8 | F8_ground_evidence.png | 真实受淹证据点 |
| 9 | F9_susceptibility.png | 物理易涝性 |
| 10 | F10_event_exposure_rank.png | 事件暴露 rank |
| 11 | F11_M2R_risk.png | M2R 2026 重建风险 |
| 12 | F12_risk_confidence.png | 风险 × 置信度（分开表达） |

所有图：比例尺 + 指北针 + CRS + 图例 + 数据来源。图件为**研究图**，非网页风格。
""")
    print("figures:", sorted(os.listdir(FIG)))


if __name__ == "__main__":
    main()
