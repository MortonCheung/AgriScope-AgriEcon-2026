#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P4R-16：Sentinel-1 RTC 同轨多年基线 —— 破解"无历史同期对照"。

【为什么放弃 GRD 改用 RTC】
1. `sentinel-1-grd` 的 COG 在 Planetary Computer 上**没有嵌入式地理参考**
   （ds.crs=None、transform 为单位阵），而 STAC 的 `proj:transform` 又与实际
   栅格布局自相矛盾：声明的逻辑网格是 25748行×16686列(0.0002066°经向/7.368e-5°纬向)，
   但文件实际是 16686行×25748列（雷达方位×距离），且雷达几何并非北向 —— 
   结果任何基于 proj:transform 的窗口索引都会取到**错误的地理位置**。
   （82_p4_grid_sar.py 正是这样取的窗口；请求行 15805–19862 时被文件高度 16686
   截断，只回 881 行，等于把研究区最北端一条狭带拉伸铺满整个 100m 网格。）
2. `sentinel-1-rtc` 是微软的辐射地形校正产品：**EPSG:32651 UTM 10m 北向网格**
   （与研究区 100m 网格同投影）、`γ⁰` 已定标、已做地形辐射校正 → 跨场景/跨平台可比，
   不需要靠"比值抵消平台差"来凑合。
3. RTC 的逐年覆盖**比 GRD 更全**：GRD 在 2023 年 7 月断档（06-27→08-14），
   RTC 有 2023-07-21。

【方法】
- 固定 relativeOrbit=105 + descending（几何可比），逐年内取
  "事件锚定日（≈07-06 → ≈07-18）" 的一对场景，算耕地口径的 ΔdB；
- 2026 事件年的 ΔdB 与 2021–2025 基线年 ΔdB 比较，给出 z 分数与秩；
- 同时输出事件对逐像元 ΔdB 栅格，以及相对基线中位的**像元级异常**图。

【长任务纪律】增量落盘 + 单景超时 + 断点续跑（重跑自动跳过已完成的 (scene, pol)）。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import time
import urllib.request
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
from rasterio.windows import from_bounds
from affine import Affine

os.environ.setdefault("GDAL_HTTP_TIMEOUT", "60")
os.environ.setdefault("GDAL_HTTP_CONNECTTIMEOUT", "20")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "2")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "3")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("VSI_CACHE", "FALSE")

BASE = Path(__file__).resolve().parents[3]
SP = BASE / "03_clean" / "spatial"
M2 = BASE / "06_models" / "M2_waterlogging_spatial"
MARTS = BASE / "04_marts"
RS = BASE / "03_clean" / "remote_sensing"

BND = SP / "shenbei_boundary.gpkg"
CROPLAND = SP / "cropland" / "pnb_cropland_30m.tif"

PC = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-1-rtc"
BBOX_LL = [123.30, 41.95, 123.95, 42.25]
ORBIT = 105
PASS = "descending"
RES100 = 100.0
READ_RES = 20.0          # 先降到 20m 再聚合到 100m
SCENE_TIMEOUT = 300

OUT_STATS = RS / "s1rtc_multiyear_scene_stats.csv"
OUT_DELTA = MARTS / "s1rtc_change_2026_vs_baseline.csv"
OUT_SPATIAL_DIR = M2 / "remote_sensing"

EV_PRE = "2026-07-06"
EV_POST = "2026-07-18"
BASE_YEARS = (2021, 2022, 2023, 2024, 2025)

STAT_COLS = [
    "scene_id", "date", "doy", "year", "platform", "relative_orbit", "orbit_state",
    "pol", "read_ok", "error", "coverage_frac",
    "n_valid_px", "mean_power", "db_mean", "p10_db", "p50_db", "p90_db",
    "n_cropland_px", "mean_power_cropland", "db_mean_cropland",
    "p10_db_cropland", "p50_db_cropland", "p90_db_cropland",
]


def _alarm(s, f):
    raise TimeoutError("op_timeout")


signal.signal(signal.SIGALRM, _alarm)


# ---------------------------------------------------------------- 网格
def grid_geom():
    import geopandas as gpd
    g = gpd.read_file(BND)
    minx, miny, maxx, maxy = g.total_bounds
    W = int(np.ceil((maxx - minx) / RES100))
    H = int(np.ceil((maxy - miny) / RES100))
    tr = rasterio.transform.from_origin(minx, maxy, RES100, RES100)
    return dict(minx=minx, miny=miny, maxx=maxx, maxy=maxy, W=W, H=H, tr=tr, crs=g.crs, gdf=g)


def cropland_frac_on_grid(geom):
    with rasterio.open(CROPLAND) as s:
        src = s.read(1).astype("float32")
        src_tr, src_crs = s.transform, s.crs
    dst = np.full((geom["H"], geom["W"]), np.nan, "float32")
    reproject(source=src, destination=dst, src_transform=src_tr, src_crs=src_crs,
              dst_transform=geom["tr"], dst_crs=geom["crs"],
              resampling=Resampling.average, src_nodata=0, dst_nodata=np.nan)
    return np.nan_to_num(dst, nan=0.0)


# ---------------------------------------------------------------- STAC
def sas_token():
    url = f"{PC.rsplit('/stac/v1', 1)[0]}/sas/v1/token/{COLLECTION}"
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                return json.loads(r.read())["token"]
        except Exception:                        # noqa: BLE001
            time.sleep(3)
    raise RuntimeError("sas_token_failed")


def stac_search(dt_range, limit=1000):
    body = json.dumps({"collections": [COLLECTION], "bbox": BBOX_LL,
                       "datetime": dt_range, "limit": limit}).encode()
    req = urllib.request.Request(f"{PC}/search", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["features"]


def pick_scenes(doy_lo=150, doy_hi=250):
    feats = stac_search(f"2021-01-01T00:00:00Z/{time.strftime('%Y')}-12-31T23:59:59Z")
    out, seen = [], set()
    for f in feats:
        p = f["properties"]
        if p.get("sat:relative_orbit") != ORBIT:
            continue
        if (p.get("sat:orbit_state") or "").lower() != PASS:
            continue
        dt = p["datetime"][:10]
        doy = int(time.strftime("%j", time.strptime(dt, "%Y-%m-%d")))
        if not (doy_lo <= doy <= doy_hi):
            continue
        if f["id"] in seen:
            continue
        seen.add(f["id"])
        out.append(f)
    out.sort(key=lambda x: x["properties"]["datetime"])
    return out


# ---------------------------------------------------------------- 读取
def read_scene_to_grid(ft, geom, tok, pol):
    """RTC 场景 → 100m 网格。同投影(UPS 32651)，直接按 bounds 取窗 + 重采样。"""
    url = ft["assets"][pol]["href"] + "?" + tok
    with rasterio.open(url) as ds:
        if ds.crs is None:
            raise RuntimeError(f"rtc_missing_crs:{ds.crs}")
        nod = ds.nodata if ds.nodata is not None else -32768.0
        # 有效覆盖交集
        l = max(ds.bounds.left, geom["minx"]); r = min(ds.bounds.right, geom["maxx"])
        b = max(ds.bounds.bottom, geom["miny"]); t = min(ds.bounds.top, geom["maxy"])
        if l >= r or b >= t:
            raise RuntimeError("bbox_not_covered")
        win = from_bounds(l, b, r, t, transform=ds.transform)
        # 对齐到整像元，避免 GDAL 边缘插值
        win = win.round_offsets().round_lengths()
        gsd = abs(ds.transform.a)
        out_w = max(50, int(round(win.width * gsd / READ_RES)))
        out_h = max(50, int(round(win.height * gsd / READ_RES)))
        signal.alarm(SCENE_TIMEOUT)
        try:
            arr = ds.read(1, window=win, out_shape=(out_h, out_w)).astype("float32")
        finally:
            signal.alarm(0)
        src_tr = ds.window_transform(win) * Affine.scale(win.width / out_w, win.height / out_h)
        src_crs = ds.crs
    arr[arr <= nod + 1e-3] = np.nan
    arr[~np.isfinite(arr)] = np.nan
    dst = np.full((geom["H"], geom["W"]), np.nan, "float32")
    reproject(source=arr, destination=dst, src_transform=src_tr, src_crs=src_crs,
              dst_transform=geom["tr"], dst_crs=geom["crs"],
              resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
    dst[dst <= 0] = np.nan
    cov = float(np.isfinite(dst).mean())
    return dst, cov


def stat_block(power, mask=None):
    """power 为 γ⁰ 线性功率 → 转 dB 统计。"""
    m = np.isfinite(power) & (power > 0)
    if mask is not None:
        m = m & mask
    v = power[m]
    if v.size == 0:
        return dict(n=0, mean_power=np.nan, db_mean=np.nan, p10=np.nan, p50=np.nan, p90=np.nan)
    db = 10.0 * np.log10(v.astype("float64"))
    return dict(n=int(v.size), mean_power=float(v.mean()),
                db_mean=float(10.0 * np.log10(max(v.mean(), 1e-12))),
                p10=float(np.percentile(db, 10)), p50=float(np.percentile(db, 50)),
                p90=float(np.percentile(db, 90)))


# ---------------------------------------------------------------- 读取阶段
def load_done():
    if not OUT_STATS.exists():
        return set()
    done = set()
    with OUT_STATS.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r.get("read_ok") == "1":
                done.add((r["scene_id"], r["pol"]))
    return done


def run_read(args):
    geom = grid_geom()
    crop = cropland_frac_on_grid(geom)
    cmask = crop >= 0.5
    print(f"[116] 100m 网格 {geom['W']}x{geom['H']} crs={geom['crs']} | "
          f"耕地单元 {int(cmask.sum())}/{cmask.size}", flush=True)

    scenes = pick_scenes(args.doy_lo, args.doy_hi)
    pols = [p.strip() for p in args.pols.split(",") if p.strip()]
    todo = [(f, p) for f in scenes for p in pols]
    done = load_done()
    print(f"[116] RTC 同轨 {ORBIT}/{PASS} 作物季 {len(scenes)} 景 × {pols} = "
          f"{len(todo)} 任务；已完成 {len(done)}", flush=True)

    new_file = not OUT_STATS.exists()
    fh = OUT_STATS.open("a", newline="", encoding="utf-8-sig")
    wr = csv.DictWriter(fh, fieldnames=STAT_COLS)
    if new_file:
        wr.writeheader(); fh.flush()

    tok, tok_age = sas_token(), time.time()
    ok = fail = 0
    for i, (ft, pol) in enumerate(todo, 1):
        p = ft["properties"]
        sid = ft["id"]
        if (sid, pol) in done:
            continue
        if time.time() - tok_age > 600:
            tok, tok_age = sas_token(), time.time()
        dt = p["datetime"][:10]
        row = {c: "" for c in STAT_COLS}
        row.update(scene_id=sid, date=dt, year=dt[:4],
                   doy=int(time.strftime("%j", time.strptime(dt, "%Y-%m-%d"))),
                   platform=p.get("platform", ""), relative_orbit=ORBIT, orbit_state=PASS, pol=pol)
        try:
            arr, cov = read_scene_to_grid(ft, geom, tok, pol)
            a = stat_block(arr)
            b = stat_block(arr, cmask)
            row.update(read_ok=1, error="", coverage_frac=round(cov, 4),
                       n_valid_px=a["n"], mean_power=round(a["mean_power"], 6),
                       db_mean=round(a["db_mean"], 4),
                       p10_db=round(a["p10"], 4), p50_db=round(a["p50"], 4), p90_db=round(a["p90"], 4),
                       n_cropland_px=b["n"], mean_power_cropland=round(b["mean_power"], 6),
                       db_mean_cropland=round(b["db_mean"], 4),
                       p10_db_cropland=round(b["p10"], 4), p50_db_cropland=round(b["p50"], 4),
                       p90_db_cropland=round(b["p90"], 4))
            ok += 1
            print(f"  [{i}/{len(todo)}] {dt} {pol} {row['platform']:12s} "
                  f"cov={cov:.3f} dB={row['db_mean']:8.3f} 耕地dB={row['db_mean_cropland']:8.3f}",
                  flush=True)
        except Exception as e:                    # noqa: BLE001
            row.update(read_ok=0, error=f"{type(e).__name__}:{str(e)[:60]}")
            fail += 1
            print(f"  [{i}/{len(todo)}] {dt} {pol} FAILED {row['error']}", flush=True)
        wr.writerow(row); fh.flush()               # ★ 逐景增量落盘
    fh.close()
    print(f"[116] 读取完成 ok={ok} fail={fail} → {OUT_STATS.name}", flush=True)


def load_stats():
    import pandas as pd
    d = pd.read_csv(OUT_STATS, encoding="utf-8-sig")
    d = d[d.read_ok == 1].copy()
    d["date"] = pd.to_datetime(d["date"])
    return d.sort_values(["pol", "date"])


# ---------------------------------------------------------------- 年内变化与基线
def build_delta():
    import pandas as pd
    d = load_stats()
    pre_doy = int(time.strftime("%j", time.strptime(EV_PRE, "%Y-%m-%d")))
    post_doy = int(time.strftime("%j", time.strptime(EV_POST, "%Y-%m-%d")))

    rows = []
    for pol in sorted(d["pol"].unique()):
        dp = d[d["pol"] == pol]
        for y in sorted(dp["date"].dt.year.unique()):
            dy = dp[dp["date"].dt.year == y]
            if len(dy) < 2:
                continue
            a = dy.iloc[(dy["doy"] - pre_doy).abs().argsort()[:1]].iloc[0]
            b = dy.iloc[(dy["doy"] - post_doy).abs().argsort()[:1]].iloc[0]
            if a["scene_id"] == b["scene_id"]:
                continue
            if a["date"] > b["date"]:
                a, b = b, a
            rows.append(dict(
                pol=pol, year=int(y),
                pre_scene=a["scene_id"], pre_date=a["date"].date(), pre_doy=int(a["doy"]),
                post_scene=b["scene_id"], post_date=b["date"].date(), post_doy=int(b["doy"]),
                gap_days=int((b["date"] - a["date"]).days),
                pre_platform=a["platform"], post_platform=b["platform"],
                db_pre=round(a["db_mean_cropland"], 4), db_post=round(b["db_mean_cropland"], 4),
                delta_db=round(b["db_mean_cropland"] - a["db_mean_cropland"], 4),
                db_pre_all=round(a["db_mean"], 4), db_post_all=round(b["db_mean"], 4),
                delta_db_all=round(b["db_mean"] - a["db_mean"], 4),
                pre_cov=round(a["coverage_frac"], 3), post_cov=round(b["coverage_frac"], 3),
                n_scenes_in_year=int(len(dy)), is_event_year=int(y == 2026)))
    out = pd.DataFrame(rows)
    if out.empty:
        print("[116] 无可用配对", flush=True); return out

    summary = []
    for pol in sorted(out["pol"].unique()):
        o = out[out["pol"] == pol]
        base = o[(o.is_event_year == 0) & (o.gap_days <= 30)]["delta_db"].dropna()
        ev = o[o.is_event_year == 1]
        if ev.empty or base.empty:
            continue
        ev_v = float(ev.iloc[0]["delta_db"])
        mu = float(base.mean())
        sd = float(base.std(ddof=1)) if len(base) > 1 else np.nan
        z = (ev_v - mu) / sd if np.isfinite(sd) and sd > 0 else np.nan
        summary.append(dict(
            pol=pol, n_baseline=int(len(base)),
            baseline_years=";".join(str(int(v)) for v in o[(o.is_event_year == 0) & (o.gap_days <= 30)]["year"]),
            baseline_mean_delta_db=round(mu, 4),
            baseline_sd_delta_db=(round(sd, 4) if np.isfinite(sd) else ""),
            baseline_min_delta_db=round(float(base.min()), 4),
            baseline_max_delta_db=round(float(base.max()), 4),
            event_2026_delta_db=round(ev_v, 4),
            diff_vs_baseline_mean=round(ev_v - mu, 4),
            z_score=(round(z, 3) if np.isfinite(z) else ""),
            pct_change=round((10 ** ((ev_v - mu) / 10) - 1) * 100, 2),
            rank_of_2026=(int((o["delta_db"] < ev_v).sum()) + 1), n_total_years=int(len(o))))
    s = pd.DataFrame(summary)

    out.to_csv(OUT_DELTA, index=False, encoding="utf-8-sig")
    print(f"[116] 年内变化表 → {OUT_DELTA.name} ({len(out)} 行)", flush=True)
    if not s.empty:
        sp = OUT_DELTA.with_name("s1rtc_change_2026_vs_baseline_summary.csv")
        s.to_csv(sp, index=False, encoding="utf-8-sig")
        print(f"[116] 基线对比汇总 → {sp.name}", flush=True)

    print()
    print("=" * 80)
    print("逐年 pre→post 年内变化（RTC，耕地口径，ΔdB；负=后向散射变暗）")
    print("=" * 80)
    print(out.pivot_table(index="year", columns="pol", values="delta_db").round(3).to_string())
    print()
    print(out[["pol", "year", "pre_date", "post_date", "gap_days",
               "db_pre", "db_post", "delta_db"]].to_string(index=False))
    if not s.empty:
        print()
        print("=== 2026 事件年 vs 基线 ===")
        print(s.to_string(index=False))
    return out


# ---------------------------------------------------------------- 空间异常
def build_spatial():
    import pandas as pd
    geom = grid_geom()
    crop = cropland_frac_on_grid(geom)
    cmask = crop >= 0.5
    by_id = {f["id"]: f for f in pick_scenes(150, 250)}
    by_date = {f["properties"]["datetime"][:10]: f for f in by_id.values()}
    stats = load_stats()
    pre_doy = int(time.strftime("%j", time.strptime(EV_PRE, "%Y-%m-%d")))
    post_doy = int(time.strftime("%j", time.strptime(EV_POST, "%Y-%m-%d")))

    def anchor(year, doy_target, pol):
        dd = stats[(stats["pol"] == pol) & (stats["date"].dt.year == year)]
        if dd.empty:
            return None
        return dd.iloc[(dd["doy"] - doy_target).abs().argsort()[:1]].iloc[0]

    OUT_SPATIAL_DIR.mkdir(parents=True, exist_ok=True)
    prof = dict(driver="GTiff", height=geom["H"], width=geom["W"], count=1, dtype="float32",
                crs=geom["crs"], transform=geom["tr"], nodata=np.nan, compress="deflate")
    tok = sas_token()
    allsumm = []

    for pol in ("vv", "vh"):
        try:
            if EV_PRE not in by_date or EV_POST not in by_date:
                print(f"[116] {pol}: 事件对缺场景，跳过", flush=True); continue
            A, _ = read_scene_to_grid(by_date[EV_PRE], geom, tok, pol)
            B, _ = read_scene_to_grid(by_date[EV_POST], geom, tok, pol)
            with np.errstate(divide="ignore", invalid="ignore"):
                delta = 10.0 * np.log10(np.where((A > 0) & (B > 0), B / A, np.nan))
            p1 = OUT_SPATIAL_DIR / f"s1rtc_delta_{pol}_2026_event.tif"
            with rasterio.open(p1, "w", **prof) as ds:
                ds.write(delta.astype("float32"), 1)
            print(f"[116] {p1.name}", flush=True)

            stack = []
            for y in BASE_YEARS:
                ra, rb = anchor(y, pre_doy, pol), anchor(y, post_doy, pol)
                if ra is None or rb is None or ra["scene_id"] == rb["scene_id"]:
                    continue
                if ra["date"] > rb["date"]:
                    ra, rb = rb, ra
                if ra["scene_id"] not in by_id or rb["scene_id"] not in by_id:
                    print(f"[116] {pol}: 基线年 {y} 场景对象缺失，跳过", flush=True); continue
                if (rb["date"] - ra["date"]).days > 30:
                    print(f"[116] {pol}: 基线年 {y} 间隔 {(rb['date']-ra['date']).days} 天 > 30，跳过", flush=True)
                    continue
                Aa, _ = read_scene_to_grid(by_id[ra["scene_id"]], geom, tok, pol)
                Bb, _ = read_scene_to_grid(by_id[rb["scene_id"]], geom, tok, pol)
                with np.errstate(divide="ignore", invalid="ignore"):
                    stack.append(10.0 * np.log10(np.where((Aa > 0) & (Bb > 0), Bb / Aa, np.nan)))
                print(f"[116] {pol}: 基线年 {y} ({ra['date'].date()}→{rb['date'].date()}) 已算", flush=True)

            def summ(name, arr):
                v = arr[np.isfinite(arr)]
                vc = arr[cmask & np.isfinite(arr)]
                if v.size == 0:
                    return
                allsumm.append(dict(
                    pol=pol, metric=name, n_all=int(v.size), n_cropland=int(vc.size),
                    p10_crop=round(float(np.percentile(vc, 10)), 3),
                    p50_crop=round(float(np.median(vc)), 3),
                    p90_crop=round(float(np.percentile(vc, 90)), 3),
                    mean_crop=round(float(vc.mean()), 3),
                    frac_lt_neg2db=round(float((vc < -2).mean()), 4),
                    frac_lt_neg3db=round(float((vc < -3).mean()), 4),
                    frac_gt_pos2db=round(float((vc > 2).mean()), 4)))

            summ("delta_2026_event", delta)
            if stack:
                bs = np.stack(stack)
                bmed = np.nanmedian(bs, axis=0)
                bsd = np.nanstd(bs, axis=0, ddof=1) if len(stack) > 1 else np.full_like(bmed, np.nan)
                with np.errstate(invalid="ignore"):
                    anom = delta - bmed
                    z = np.where(bsd > 1.0, anom / bsd, np.nan)
                for nm, arr in ((f"s1rtc_baseline_median_{pol}_2026window.tif", bmed),
                                (f"s1rtc_anomaly_{pol}_2026_vs_baseline.tif", anom)):
                    with rasterio.open(OUT_SPATIAL_DIR / nm, "w", **prof) as ds:
                        ds.write(arr.astype("float32"), 1)
                print(f"[116] {pol}: 基线中位图 + 异常图已写出（基线年 {len(stack)} 个）", flush=True)
                summ("anomaly_vs_baseline", anom)
            else:
                print(f"[116] {pol}: 无合格基线年", flush=True)
        except Exception as e:                      # noqa: BLE001
            print(f"[116] {pol} 空间图失败: {type(e).__name__}: {str(e)[:90]}", flush=True)

    if allsumm:
        sp = MARTS / "s1rtc_spatial_summary_2026_event.csv"
        pd.DataFrame(allsumm).to_csv(sp, index=False, encoding="utf-8-sig")
        print(f"\n[116] {sp.name}", flush=True)
        print(pd.DataFrame(allsumm).to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="read", choices=["read", "delta", "spatial", "all"])
    ap.add_argument("--pols", default="vv")
    ap.add_argument("--doy-lo", type=int, default=150)
    ap.add_argument("--doy-hi", type=int, default=250)
    a = ap.parse_args()
    print(f"=== 116_p4r_s1_multiyear_baseline (RTC) | stage={a.stage} ===", flush=True)
    if a.stage in ("read", "all"):
        run_read(a)
    if a.stage in ("delta", "all"):
        build_delta()
    if a.stage in ("spatial", "all"):
        build_spatial()


if __name__ == "__main__":
    main()
