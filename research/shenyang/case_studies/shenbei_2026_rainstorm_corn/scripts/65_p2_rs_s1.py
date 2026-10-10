#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P2-09 探索性 Sentinel-1 VV 后向散射变化检测（EXPLORATORY）。
- PC 的 S1-GRD COG 为 EPSG:4326（proj:epsg=4326，未内嵌 CRS）；
- 只用同平台+同相对轨道场景；读 400x400 降采样窗口（等效多视抑斑）；
- 事件后 − 事件前 的 VV 相对变化；并与 2025 同 DOY 窗口对照得“异常变化”。
限制：GRD DN 未做绝对辐射定标/地形校正 → 仅探索性，不作为最终证据。
"""
import json
import os
import signal
import sys
import urllib.request

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(BASE, "03_clean", "remote_sensing")
os.makedirs(CLEAN, exist_ok=True)
PC = "https://planetarycomputer.microsoft.com/api/stac/v1"
BBOX_SEARCH = [123.30, 41.85, 123.90, 42.20]
WIN = (123.45, 41.95, 123.65, 42.10)   # 沈北西部低洼农田窗口


def _alarm(s, f):
    raise TimeoutError("op_timeout")


signal.signal(signal.SIGALRM, _alarm)


def token():
    with urllib.request.urlopen(f"https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-1-grd", timeout=40) as r:
        return "?" + json.loads(r.read())["token"]


def search(dt):
    body = json.dumps({"collections": ["sentinel-1-grd"], "bbox": BBOX_SEARCH, "datetime": dt, "limit": 100}).encode()
    req = urllib.request.Request(f"{PC}/search", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=70) as r:
        return json.loads(r.read())["features"]


def read_vv(ft, tok):
    import rasterio
    from affine import Affine
    from rasterio.windows import Window
    href = ft["assets"]["vv"]["href"]
    url = href + ("&" if "?" in href else "?") + tok
    # COG 未内嵌 CRS/transform → 用 STAC item 的 proj:transform 定位窗口
    A = Affine(*ft["properties"]["proj:transform"])
    x0, y0 = (WIN[0] - A.c) / A.a, (WIN[3] - A.f) / A.e
    x1, y1 = (WIN[2] - A.c) / A.a, (WIN[1] - A.f) / A.e
    c0, c1 = int(min(x0, x1)), int(max(x0, x1))
    r0, r1 = int(min(y0, y1)), int(max(y0, y1))
    win = Window(c0, r0, c1 - c0, r1 - r0)
    signal.alarm(120)
    try:
        with rasterio.open(url) as ds:
            a = ds.read(1, window=win, out_shape=(400, 400)).astype("float32")
    finally:
        signal.alarm(0)
    return a


def change(dt_pre, dt_post, tok, label, rep):
    pre, post = search(dt_pre), search(dt_post)
    if not pre or not post:
        rep.append(dict(label=label, status="no_scene", n_pre=len(pre), n_post=len(post))); return None
    for ft0 in pre:
        p = ft0["properties"]; plat, orb = p.get("platform"), p.get("sat:relative_orbit")
        po = [f for f in post if f["properties"].get("platform") == plat
              and f["properties"].get("sat:relative_orbit") == orb]
        if not po:
            continue
        a, b = read_vv(ft0, tok), read_vv(po[0], tok)
        am, bm = float(np.nanmean(a)), float(np.nanmean(b))
        rep.append(dict(label=label, status="ok", platform=plat, orbit=orb,
                        pre_scene=ft0["id"], post_scene=po[0]["id"],
                        vv_pre_mean_DN=round(am, 1), vv_post_mean_DN=round(bm, 1),
                        vv_change_pct=round((bm - am) / am * 100, 2), px=a.size))
        return (bm - am) / am * 100
    rep.append(dict(label=label, status="no_matched_orbit")); return None


def main():
    tok = token()
    rep = []
    c26 = change("2026-07-05T00:00:00Z/2026-07-12T23:59:59Z", "2026-07-14T00:00:00Z/2026-07-25T23:59:59Z", tok, "2026_event", rep)
    # 2025 对照：用 2026 相同的平台/相对轨道，取最接近同日期(07-11 与 07-23)的两景
    ref = None
    for r in rep:
        if r.get("label") == "2026_event" and r.get("status") == "ok":
            ref = (r["platform"], r["orbit"])
    c25 = None
    if ref:
        plat, orb = ref
        import datetime as dt
        for cy in [2025, 2024, 2023]:
            feats = [f for f in search(f"{cy}-06-25T00:00:00Z/{cy}-08-10T23:59:59Z")
                     if f["properties"].get("sat:relative_orbit") == orb]
            if not feats:
                continue
            feats.sort(key=lambda f: f["properties"]["datetime"])
            def nearest(target):
                return min(feats, key=lambda f: abs((dt.datetime.fromisoformat(f["properties"]["datetime"].replace("Z", "")) - target).days))
            a_f, b_f = nearest(dt.datetime(cy, 7, 11)), nearest(dt.datetime(cy, 7, 23))
            if a_f["id"] != b_f["id"]:
                a, b = read_vv(a_f, tok), read_vv(b_f, tok)
                am, bm = float(np.nanmean(a)), float(np.nanmean(b))
                c25 = (bm - am) / am * 100
                rep.append(dict(label=f"{cy}_control", status="ok", platform=a_f["properties"].get("platform"), orbit=orb,
                                pre_scene=a_f["id"], post_scene=b_f["id"],
                                vv_pre_mean_DN=round(am, 1), vv_post_mean_DN=round(bm, 1),
                                vv_change_pct=round(c25, 2), px=a.size))
                break
        if c25 is None:
            rep.append(dict(label="control", status="no_scene_in_2023_2025"))
    if c26 is not None and c25 is not None:
        rep.append(dict(label="ANOMALY_2026_minus_2025_pct", status="ok", vv_change_pct=round(c26 - c25, 2)))
    df = pd.DataFrame(rep)
    df.to_csv(os.path.join(CLEAN, "rs_s1_backscatter_exploratory.csv"), index=False, encoding="utf-8-sig")
    print(df.to_string())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa
        print("RS_EXPLORATORY_FAILED:", type(e).__name__, e)
        pd.DataFrame([{"label": "RS_EXPLORATORY", "status": f"failed:{type(e).__name__}:{e}"}]).to_csv(
            os.path.join(CLEAN, "rs_s1_backscatter_exploratory.csv"), index=False, encoding="utf-8-sig")
