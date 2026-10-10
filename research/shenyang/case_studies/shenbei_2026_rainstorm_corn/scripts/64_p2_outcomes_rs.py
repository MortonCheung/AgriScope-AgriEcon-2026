#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P2-08 灾害结果变量 → 03_clean/disaster/disaster_outcomes_2026.csv（有则填，无则 missing，绝不估）
P2-09 遥感影像可得性枚举 → 03_clean/remote_sensing/rs_scene_manifest.csv
"""
import csv
import json
import os
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(BASE, "03_clean")
os.makedirs(os.path.join(CLEAN, "remote_sensing"), exist_ok=True)

# ---------------- P2-08 结果变量 ----------------
OUTCOMES_COLS = ["location", "date", "crop", "affected_area_mu", "damaged_area_mu",
                 "destroyed_area_mu", "waterlogged_area_mu", "yield_loss_pct",
                 "economic_loss_yuan", "evidence_type", "source_id", "quality_level", "notes"]

OUTCOMES = [
    ["沈北新区（全区）", "2026-07", "玉米/水稻", "not_available", "not_available", "not_available",
     "not_available", "not_available", "not_available", "未公开", "无", "missing",
     "官方未按区公开沈北农业受灾/成灾/绝收/经济损失；需政府信息公开申请"],
    ["沈阳市沈北新区兴隆台街道", "2026-07-14", "玉米/水稻", "not_available", "not_available",
     "not_available", "10000", "not_available", "not_available", "官方综述转述", "SRC-LN-GOV-2026-0717",
     "E", "‘万亩农田受淹’为量级表述，非精确统计"],
    ["沈阳市沈北新区新城子街道八间房村", "2026-07-14", "玉米/水稻", "8000", "not_available",
     "not_available", "8000", "not_available", "not_available", "权威媒体", "SRC-SYD-2026-0814",
     "E", "‘8000余亩’媒体量级；最深>1米"],
    ["辽宁省（口径，非沈北）", "2026-07-15", "玉米/水稻", "2900000", "not_available",
     "not_available", "532700", "not_available", "not_available", "官方", "SRC-LN-GOV-2026-0717",
     "A", "全省受影响约290万亩；排空积水53.27万亩；严禁按比例拆分到沈北"],
]


def write_outcomes():
    p = os.path.join(CLEAN, "disaster", "disaster_outcomes_2026.csv")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(OUTCOMES_COLS)
        w.writerows(OUTCOMES)
    print("[P2-08] disaster_outcomes_2026 rows=", len(OUTCOMES), "(全部区级=not_available)")


# ---------------- P2-09 遥感枚举 ----------------
BBOX = [123.30, 41.85, 123.90, 42.20]
PC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"


def stac(collection, dt):
    body = json.dumps({"collections": [collection], "bbox": BBOX, "datetime": dt, "limit": 200}).encode()
    req = urllib.request.Request(PC, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def enumerate_rs():
    rows = []
    # Sentinel-1 GRD：整段 2026-05-01~2026-09-01（含暴雨前后）
    for coll in ["sentinel-1-grd", "sentinel-2-l2a"]:
        try:
            js = stac(coll, "2026-05-01T00:00:00Z/2026-09-10T00:00:00Z")
        except Exception as e:  # noqa
            print(f"[P2-09] {coll} 查询失败: {e}")
            continue
        for ft in js.get("features", []):
            pr = ft.get("properties", {})
            rows.append(dict(
                collection=coll, scene_id=ft.get("id"),
                datetime=pr.get("datetime"),
                platform=pr.get("platform"),
                orbit=pr.get("sat:orbit_state"),
                rel_orbit=pr.get("sat:relative_orbit"),
                polarization=pr.get("sar:polarizations") if coll.startswith("sentinel-1") else None,
                cloud_cover=pr.get("eo:cloud_cover") if coll.startswith("sentinel-2") else None,
                assets=",".join(list(ft.get("assets", {}).keys())[:6]),
            ))
    p = os.path.join(CLEAN, "remote_sensing", "rs_scene_manifest.csv")
    if rows:
        import pandas as pd
        df = pd.DataFrame(rows).sort_values(["collection", "datetime"])
        df.to_csv(p, index=False, encoding="utf-8-sig")
        s1 = df[df.collection == "sentinel-1-grd"]
        s2 = df[df.collection == "sentinel-2-l2a"]
        print(f"[P2-09] S1 scenes={len(s1)} 日期范围={s1.datetime.min()}~{s1.datetime.max()}")
        print(f"[P2-09] S2 scenes={len(s2)} (含云量) 云量中位数={None if s2.empty else round(s2.cloud_cover.median(),1)}")
        # 关键：事件前后 S1 覆盖
        if not s1.empty:
            s1 = s1.copy(); s1["d"] = pd.to_datetime(s1["datetime"])
            pre = s1[(s1.d >= "2026-07-05") & (s1.d <= "2026-07-12")]
            post = s1[(s1.d >= "2026-07-14") & (s1.d <= "2026-07-25")]
            print(f"[P2-09] 事件前(7-05~7-12) S1={len(pre)} 景；事件后(7-14~7-25) S1={len(post)} 景")
    else:
        print("[P2-09] 未获取到场景")
    return rows


if __name__ == "__main__":
    write_outcomes()
    enumerate_rs()
