"""STEP D3 — 区县代表点坐标（district_coordinates.csv）。

目的：为 8 个农业区县各定一个**有明确来源、可复现**的天气代表点。
坐标口径与现有项目保持一致：沿用 `/raw_data/metadata/cities.csv`
所用的**农业农村部 pfsc 官方地区接口**（`/price_portal/region/selectList`，JSON POST），
取区县行政中心经纬度；沈北新区坐标与现有 `weather_stations.csv` 的 `OM-沈北新区`
完全一致，确保本轮区县天气与既有沈阳天气体系同源。

区县清单（沈阳市 13 个区县中的 8 个农业区县；5 个城市核心区
和平/沈河/大东/皇姑/铁西农业极少，年鉴农业表亦不单列，故不纳入天气采集）。

红线：
  - 坐标不得估算；使用官方接口返回值；
  - pfsc 库沿用旧名（东陵区/辽中县），本表同时记录 pfsc 原名与现行标准名，
    并给出行政区划代码变更依据；
  - 不改变既有沈阳城市坐标，只新增区县行。

产出（data/processed/）：district_coordinates.csv
  district, admin_code, pfsc_id, pfsc_name, latitude, longitude,
  coordinate_method, source, source_url, is_agricultural, notes
"""
from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PATHS, StepTimer, get_logger  # noqa: E402

MOD = "22_district_coordinates"
LOG = get_logger(MOD)

API = "https://pfsc.agri.cn/price_portal/region/selectList"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# 现行标准名 → (行政区划代码, pfsc 库中的旧名或同名)
# 变更依据：2014 东陵区更名浑南区（代码 210112 沿用）；2016 辽中县撤县设区
#           （辽中区代码 210115，pfsc 库仍存旧名"辽中县"/旧码 210122）
DISTRICT_MAP = {
    "苏家屯区": ("210111", "苏家屯区"),
    "浑南区":   ("210112", "东陵区"),
    "沈北新区": ("210113", "沈北新区"),
    "于洪区":   ("210114", "于洪区"),
    "辽中区":   ("210115", "辽中县"),
    "康平县":   ("210123", "康平县"),
    "法库县":   ("210124", "法库县"),
    "新民市":   ("210181", "新民市"),
}


def fetch_regions() -> Dict[str, dict]:
    req = urllib.request.Request(API, data=b"{}",
                                 headers={"User-Agent": UA, "Content-Type": "application/json",
                                          "Referer": "https://pfsc.agri.cn/"})
    last = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            break
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(3)
    else:
        raise last
    # 按 name 与 id 双索引：name 在中国重名严重（和平区/铁西区等），仅用 name 会取到外省
    by_name: Dict[str, dict] = {}
    by_id: Dict[str, dict] = {}
    for x in d["data"]:
        by_name.setdefault(x["name"], x)
        by_id[x["id"]] = x
    by_name["__by_id__"] = by_id  # type: ignore[assignment]
    return by_name


def main() -> None:
    with StepTimer(MOD, LOG):
        log = LOG
        regions = fetch_regions()
        log.info("pfsc 接口返回 %d 个地区对象", len(regions))
        rows = []
        for std_name, (code, pfsc_name) in DISTRICT_MAP.items():
            r = regions.get(pfsc_name)
            if r is None:
                log.warning("[MISS] pfsc 未返回 %s（查名 %s）", std_name, pfsc_name)
                continue
            rows.append({
                "district": std_name,
                "admin_code": code,
                "pfsc_id": r["id"],
                "pfsc_name": r["name"],
                "latitude": float(r["lat"]),
                "longitude": float(r["lng"]),
                "coordinate_method": "区县行政中心（农业农村部 pfsc 官方地区接口返回）",
                "source": "农业农村部 全国农产品批发市场价格信息系统 pfsc.agri.cn 地区接口",
                "source_url": API,
                "is_agricultural": 1,
                "notes": ("pfsc 库沿用旧名" if pfsc_name != std_name else "名称一致") +
                         "；与既有沈阳天气体系同源（同一接口）",
            })
        # 沈阳市本级（对照行）+ 5 个城市核心区（非农业，仅登记不采天气）
        sy = regions.get("沈阳市")
        if sy:
            rows.insert(0, {
                "district": "沈阳市（全市）", "admin_code": "210100", "pfsc_id": sy["id"],
                "pfsc_name": sy["name"], "latitude": float(sy["lat"]), "longitude": float(sy["lng"]),
                "coordinate_method": "市级行政中心（pfsc 接口）",
                "source": "农业农村部 pfsc 地区接口", "source_url": API,
                "is_agricultural": 0,
                "notes": "与既有 raw_data/metadata/cities.csv 沈阳坐标一致（用于对照）",
            })
        for core, code in (("和平区", "210102"), ("沈河区", "210103"), ("大东区", "210104"),
                           ("皇姑区", "210105"), ("铁西区", "210106")):
            r = regions["__by_id__"].get(code)          # 用行政区划代码精确匹配，避免同名跨省
            if r:
                rows.append({
                    "district": core, "admin_code": code, "pfsc_id": r["id"], "pfsc_name": r["name"],
                    "latitude": float(r["lat"]), "longitude": float(r["lng"]),
                    "coordinate_method": "区行政中心（pfsc 接口，按行政区划代码匹配）",
                    "source": "农业农村部 pfsc 地区接口", "source_url": API,
                    "is_agricultural": 0,
                    "notes": "城市核心区，农业极少，年鉴农业表未单列 → 本轮不采集天气",
                })

        d = pd.DataFrame(rows)
        p = PATHS.artifacts["district_coordinates"]
        p.parent.mkdir(parents=True, exist_ok=True)
        d.to_csv(p, index=False, encoding="utf-8-sig")
        log.info("已写 %s（%d 行；其中农业区县 %d 个）",
                 p.name, len(d), int(d["is_agricultural"].sum()))
        log.info(d[["district", "admin_code", "latitude", "longitude"]].to_string(index=False))


if __name__ == "__main__":
    main()
