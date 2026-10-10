# -*- coding: utf-8 -*-
"""农业农村部「全国农产品批发市场价格信息系统」(pfsc.agri.cn) 批发价采集与接口勘察。

目标
----
1) 落盘辽宁批发市场目录（含 marketCode / 经纬度 / 地址 / 区县），供建 city_data/reference/reports/market_registry.csv；
2) 落盘「市场报价」当日快照（AES-256-CBC 加密，密钥同前端 app.js），解析出市场级价格观测；
3) 记录接口勘察结论（是否可回溯历史日期、是否有成交量/交易额/电子结算字段、验证码闸门）。

事实基线（2026-09-22 实测）
--------------------------
* pfsc.agri.cn 前端：/js/app.d82b31ba.js；请求封装无鉴权头（/api/* 为公开接口）。
* 批发价接口 /price_portal/index/getMarketReportPriceChart：POST 参数 marketIDs/provinceCodes/varietyID，
  返回体 AES-256-CBC 加密（iv=密文前16字节，key=32字节明文），明文结构 {"date","x","y"}，
  x=市场名、y=价格(元/公斤)，date 恒为**当日**；**无任何日期类参数可回溯历史**（实测无效）。
* 逐品种报价表 /api/priceQuotationController/pageList：返回 404（后端未部署）；其网关带验证码
  （/api/interfaceCode 出图 + /api/checkInterfaceCode 校验），本项目**不绕过验证码**。
* 成交量/交易额：报价记录实体含 tradingVolume / totalPrice 字段，但公开接口返回均为 null；
  「电子结算」字段在公开接口中不存在。
* ncpscxx.moa.gov.cn：全部 /product/* 接口返回 502（网关不可用）→ 记 ACCESS_RESTRICTED。

禁止编造：所有字段均来自原始响应；取不到就记状态，不补造、不推断。
不绕过验证码/登录。

用法
----
    python3 collectors/collect_moa_wholesale.py            # 采集 + 解析
    python3 collectors/collect_moa_wholesale.py --probe    # 仅接口勘察，不落价格
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

from Crypto.Cipher import AES

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "moa_wholesale"
CHART_RAW = RAW / "chart"
STAGING = ROOT / "city_data/reference/staging"
REPORTS = ROOT / "city_data/reference/reports"

BASE = "https://pfsc.agri.cn"
NCP = "https://ncpscxx.moa.gov.cn"
KEY = b"7s9K$pG2xQ8zR5mB7vA3sD9fH2jW40cV"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
PROVINCE_CODE = "210000"
PROVINCE_NAME = "辽宁省"
CST = timezone(timedelta(hours=8))

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# area(地级市行政区划码) -> 城市名。来源：市场需求文档城市定义 + 国标区划码，非推测。
AREA_TO_CITY = {
    "210100": "沈阳", "210200": "大连", "210300": "鞍山", "210400": "抚顺",
    "210500": "本溪", "210600": "丹东", "210700": "锦州", "210800": "营口",
    "210900": "阜新", "211000": "辽阳", "211100": "盘锦", "211200": "铁岭",
    "211300": "朝阳", "211400": "葫芦岛",
}
# 县级市场：县域名直接来自农业农村部返回的**市场全称/企业名**（非推测）。
# 其余为市级市场，county 留空。
COUNTY_BY_MARKET = {
    "2103001": "海城市",   # 辽宁海城市南台镇禽蛋专业批发市场
    "2107003": "北镇市",   # 辽宁北宁市（今北镇市）窟窿台蔬菜批发市场
    "2113010": "凌源市",   # 辽宁省凌源市八里堡蔬菜果品批发市场
    "2113012": "北票市",   # 辽宁北票蔬菜批发市场
    "2108014": "大石桥市",  # 辽宁大石桥博洛铺蔬菜果品批发市场
}


def _fetch(url: str, method: str = "POST", body: bytes | None = b"",
           timeout: int = 40, retries: int = 4):
    """返回 (status, raw_bytes)；网络异常时 status=None。不处理任何验证码。"""
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(
                url, data=(body if method == "POST" else None), method=method,
                headers={"User-Agent": UA, "Origin": BASE, "Referer": BASE + "/",
                         "Content-Type": "application/json", "Accept": "application/json,*/*"})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except Exception as exc:
            last = exc
            time.sleep(1.5 * (a + 1))
    return None, str(last).encode()


def _json(url: str, method: str = "POST", data=None, params=None):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    body = json.dumps(data).encode() if data is not None else b""
    status, raw = _fetch(url, method=method, body=body)
    if status is None:
        return {"_network_error": True, "_detail": raw[:200].decode("utf-8", "ignore")}
    try:
        return json.loads(raw.decode("utf-8", "ignore"))
    except Exception:
        return {"_http_status": status, "_nonjson": raw[:200].decode("utf-8", "ignore")}


def decrypt_aes(e: str) -> str:
    iv = e[:16].encode("utf-8")
    ct = base64.b64decode(e[16:])
    pt = AES.new(KEY, AES.MODE_CBC, iv).decrypt(ct)
    return pt[:-pt[-1]].decode("utf-8")


def _now() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- 接口勘察
def probe_endpoints() -> dict:
    """只读勘察：历史日期参数、成交量字段、验证码闸门、ncpscxx 可用性。"""
    rep = {"checked_at": _now(), "pfsc": {}, "ncpscxx": {}}

    # 1) 当日市场报价图（含加密）是否受日期参数影响
    base_params = {"marketIDs": "", "provinceCodes": PROVINCE_CODE, "varietyID": ""}
    dates = {}

    def chart_date(params):
        r = _json(BASE + "/price_portal/index/getMarketReportPriceChart", params=params)
        d = r.get("data")
        if isinstance(d, str):
            try:
                return json.loads(decrypt_aes(d)).get("date")
            except Exception:
                return "DECRYPT_FAIL"
        return None

    dates["baseline"] = chart_date(base_params)
    for k in ("date", "queryDate", "startDate", "endDate", "startTime", "endTime",
              "queryStartTime", "queryEndTime", "tradingDate", "publishDate"):
        p = dict(base_params)
        p[k] = "2024-01-05"
        dates[k] = chart_date(p)
    rep["pfsc"]["getMarketReportPriceChart_date_under_params"] = dates
    rep["pfsc"]["date_invariant_under_date_params"] = len({v for v in dates.values() if v}) <= 1
    rep["pfsc"]["history_query_supported"] = not rep["pfsc"]["date_invariant_under_date_params"]

    # 2) 逐品种报价表 pageList
    status, raw = _fetch(BASE + "/api/priceQuotationController/pageList", body=b"{}")
    rep["pfsc"]["pageList"] = {"http_status": status,
                               "body_head": raw[:160].decode("utf-8", "ignore")}

    # 3) 验证码闸门（仅记录存在性，不请求求解）
    st_img, img = _fetch(BASE + "/api/interfaceCode?interfaceURI=/api/priceQuotationController/pageList",
                         method="GET", body=None)
    rep["pfsc"]["captcha_interfaceCode"] = {"http_status": st_img, "bytes": len(img),
                                            "is_jpeg": img[:2] == b"\xff\xd8"}
    rep["pfsc"]["captcha_checkInterfaceCode"] = _json(
        BASE + "/api/checkInterfaceCode", method="GET",
        params={"validateCode": "xxxx", "interfaceURI": "/api/priceQuotationController/pageList"})

    # 4) 成交量/交易额字段是否被填充
    today = _json(BASE + "/api/priceQuotationController/getTodayMarketByProvinceCode",
                  params={"code": PROVINCE_CODE})
    rows = today.get("content") or []
    filled = sum(1 for r in rows if r.get("tradingVolume") not in (None, "",) or r.get("totalPrice") not in (None, ""))
    rep["pfsc"]["quote_schema_has"] = ["tradingVolume(成交量)", "totalPrice(交易额)", "meteringUnit(计量单位)",
                                       "minimumPrice/middlePrice/highestPrice/finalPrice", "tradingDate(交易日期)"]
    rep["pfsc"]["quote_rows_returned"] = len(rows)
    rep["pfsc"]["quote_rows_with_volume_or_turnover"] = filled
    rep["pfsc"]["electronic_settlement_field"] = "不存在于公开接口响应"

    # 5) ncpscxx 可用性
    st, raw = _fetch(NCP + "/product/homeWholesalePrice/proAndMarket")
    rep["ncpscxx"] = {"http_status": st, "body_head": raw[:120].decode("utf-8", "ignore"),
                      "status_label": "ACCESS_RESTRICTED(502 网关不可用)" if st == 502 else "see_http_status"}
    return rep


# ---------------------------------------------------------------- 采集
def fetch_market_directory() -> list:
    """辽宁批发市场目录（marketPageList，province=210000）。"""
    out, page, page_size = [], 1, 100
    while True:
        r = _json(BASE + "/api/priceQuotationController/marketPageList",
                  data={"pageNum": page, "pageSize": page_size, "province": PROVINCE_CODE})
        content = r.get("content") or {}
        rows = content.get("list") or []
        out.extend(rows)
        total = content.get("totalCount") or 0
        if len(out) >= total or not rows or page > 20:
            break
        page += 1
    return out


def fetch_chart(market_ids: str = "", variety_id: str = ""):
    """市场报价图（加密）。返回 (raw_response, decrypted_or_None)。"""
    r = _json(BASE + "/price_portal/index/getMarketReportPriceChart",
              params={"marketIDs": market_ids, "provinceCodes": PROVINCE_CODE, "varietyID": variety_id})
    dec = None
    if isinstance(r.get("data"), str):
        try:
            dec = json.loads(decrypt_aes(r["data"]))
        except Exception:
            dec = {"_decrypt_error": True}
    return r, dec


def collect() -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    CHART_RAW.mkdir(parents=True, exist_ok=True)
    fetched_at = _now()

    # 1) 市场目录
    directory = fetch_market_directory()
    (RAW / "market_directory_liaoning.json").write_text(
        json.dumps(directory, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[目录] 辽宁市场 %d 个 -> market_directory_liaoning.json" % len(directory))

    # 2) 品种大类 / 品种树（留档，供后续核对）
    (RAW / "variety_major_categories.json").write_text(
        json.dumps(_json(BASE + "/api/priceQuotationController/getVarietyMajorCategories"),
                   ensure_ascii=False, indent=1), encoding="utf-8")
    (RAW / "variety_tree.json").write_text(
        json.dumps(_json(BASE + "/price_portal/sys-user-relation/getVarietiesTree"),
                   ensure_ascii=False, indent=1), encoding="utf-8")

    # 3) 全省 + 分市场 当日报价图
    raw, prov = fetch_chart()
    (RAW / "chart_province_210000.raw.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    if prov:
        (RAW / "chart_province_210000.decrypted.json").write_text(
            json.dumps(prov, ensure_ascii=False, indent=1), encoding="utf-8")

    per_market = {}
    for m in directory:
        mid = m.get("id")
        if not mid:
            continue
        r, d = fetch_chart(market_ids=mid)
        per_market[mid] = d
        (CHART_RAW / f"{m.get('marketCode') or mid}.raw.json").write_text(
            json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        if d:
            (CHART_RAW / f"{m.get('marketCode') or mid}.decrypted.json").write_text(
                json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(0.8)

    # 4) 勘察报告
    rep = probe_endpoints()
    rep["market_count"] = len(directory)
    rep["fetched_at"] = fetched_at
    (RAW / "probe_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    return {"directory": directory, "province_chart": prov, "per_market": per_market,
            "report": rep, "fetched_at": fetched_at}


# ---------------------------------------------------------------- 解析 / 落表
def write_registry(directory: list, market_ids_with_price: set, fetched_at: str) -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / "market_registry.csv"
    cols = ["market_id", "market_name", "city", "county", "market_type",
            "address", "lat", "lon", "source", "data_available"]
    src = "pfsc.agri.cn /api/priceQuotationController/marketPageList?province=210000"
    n = 0
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for m in sorted(directory, key=lambda x: (str(x.get("area")), str(x.get("marketCode")))):
            code = str(m.get("marketCode") or "")
            w.writerow({
                "market_id": code or m.get("id") or "",
                "market_name": (m.get("marketName") or "").strip(),
                "city": AREA_TO_CITY.get(str(m.get("area")), "") or (m.get("areaName") or ""),
                "county": COUNTY_BY_MARKET.get(code, ""),
                "market_type": (m.get("unitType") or "").strip() or "未标注品类",
                "address": (m.get("address") or "").strip(),
                "lat": m.get("latitude") or "",
                "lon": m.get("longitude") or "",
                "source": src,
                "data_available": "是(当日有报价)" if m.get("id") in market_ids_with_price
                                  else "否(目录在册/当日无报价)",
            })
            n += 1
    print("[注册表] 写出 %d 行 -> city_data/reference/reports/market_registry.csv" % n)
    return n


def write_prices(directory: list, province_chart: dict, per_market: dict, fetched_at: str) -> int:
    STAGING.mkdir(parents=True, exist_ok=True)
    path = STAGING / "moa_wholesale_prices.csv"
    cols = ["date", "market_id", "market_code", "market_name", "city", "county",
            "variety_code", "variety_name", "price", "unit", "province",
            "source_id", "source_name", "source_url", "data_layer", "quality_grade", "note"]
    # 报价图 x 用「企业全称」标识市场，故按 marketName / enterpriseName / szsmMarketName 建索引
    name_to_market = {}
    for m in directory:
        for k in ("marketName", "enterpriseName", "szsmMarketName"):
            if m.get(k):
                name_to_market.setdefault(m[k], m)

    rows, with_price = [], set()
    pts = province_chart or {}
    date = pts.get("date")
    for x, y in zip(pts.get("x") or [], pts.get("y") or []):
        m = name_to_market.get(x)
        if m:
            with_price.add(m.get("id"))
        else:
            m = {}
        code = str(m.get("marketCode") or "")
        rows.append({
            "date": date or "",
            "market_id": m.get("id") or "",
            "market_code": code,
            "market_name": m.get("marketName") or x,
            "city": AREA_TO_CITY.get(str(m.get("area")), "") or "",
            "county": COUNTY_BY_MARKET.get(code, ""),
            "variety_code": "",
            "variety_name": "",
            "price": y,
            "unit": "元/公斤",
            "province": PROVINCE_NAME,
            "source_id": "SRC-MOA-PFSC-SPOT",
            "source_name": "农业农村部 全国农产品批发市场价格信息系统（市场报价）",
            "source_url": BASE + "/price_portal/index/getMarketReportPriceChart",
            "data_layer": "official_market_spot_price",
            "quality_grade": "B",
            "note": "接口仅返回 x=市场名/y=价格，未提供品种维度；date 为系统当日快照，不可指定历史日期",
        })
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print("[价格表] 写出 %d 行 -> city_data/reference/staging/moa_wholesale_prices.csv" % len(rows))
    return len(rows), with_price


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="仅接口勘察")
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)

    if args.probe:
        rep = probe_endpoints()
        (RAW / "probe_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1),
                                               encoding="utf-8")
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return

    res = collect()
    n_price, with_price = write_prices(res["directory"], res["province_chart"],
                                       res["per_market"], res["fetched_at"])
    write_registry(res["directory"], with_price, res["fetched_at"])
    rep = res["report"]
    print("\n== 接口勘察要点 ==")
    print(" pfsc 支持历史日期查询:", rep["pfsc"]["history_query_supported"])
    print(" pfsc pageList:", rep["pfsc"]["pageList"]["http_status"])
    print(" pfsc 验证码:", rep["pfsc"]["captcha_interfaceCode"])
    print(" 报价记录含成交量字段:", rep["pfsc"]["quote_schema_has"],
          "| 已填充行数:", rep["pfsc"]["quote_rows_with_volume_or_turnover"])
    print(" ncpscxx:", rep["ncpscxx"]["http_status"], rep["ncpscxx"]["status_label"])
    print(" 市场数:", rep["market_count"], "| 价格行:", n_price)


if __name__ == "__main__":
    main()
