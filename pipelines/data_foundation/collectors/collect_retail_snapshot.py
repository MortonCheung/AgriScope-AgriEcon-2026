#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""五城（大连/丹东/铁岭/锦州/朝阳）即时零售 / 电商 公开商品价格页 可行性探测 + 快照采集。

范围（用户指定平台）：
  京东 / 京东秒送 / 七鲜 / 美团闪购 / 小象超市 / 多多买菜 / 盒马 / 淘宝闪购 / 当地超市线上商城

探测目标：在**未登录**状态下，页面是否公开可见「商品 + 规格 + 价格 + 地区 + 门店」五要素。
判定标签：
  ACCESSIBLE_PUBLIC      五要素免登录全部可见
  CURRENT_SNAPSHOT_LIMITED  页面免登录可达，但部分要素（多为价格/门店）需登录或需 APP
  ACCESS_RESTRICTED      必须登录 / 验证码 / 仅 APP 或小程序自提点
  NOT_PUBLICLY_AVAILABLE 仅营销落地页，无商品/门店页面
  NETWORK_FAILED         域名不可达 / 连接超时

红线（用户规则 + 本项目既有约定）：
  - 禁止破解、绕登录、绕验证码、伪造签名；遇登录墙一律记 ACCESS_RESTRICTED。
  - 不编造：抓不到的价格/规格一律留空并写 note，绝不推测补造。
  - 价格掩码（如京东 `"jdPrice":"1?"` 与 `priceLoginText=登录查看价格`）视为价格需登录，
    不提取残留字段充作价格。

产出：
  data/raw/prices/ecommerce/probe_report.json          各平台逐 URL 探测证据
  data/raw/prices/ecommerce/platform_probe_status.csv  平台级可行性结论
  data/raw/prices/ecommerce/jd/<sku>.html              京东商品页原始快照（部分可达平台）
  city_data/reference/staging/ecommerce_price_snapshot.csv            统一 schema 快照（price_level=instant_retail|ecommerce）

用法：
    python3 collectors/collect_retail_snapshot.py                # 探测 + 采集（默认）
    python3 collectors/collect_retail_snapshot.py --probe-only    # 只探测，不采集
    python3 collectors/collect_retail_snapshot.py --limit 10       # 京东最多采集 10 个 SKU
每日一次即可（本脚本幂等：原始 HTML 已存在则跳过下载）。
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
import zlib
from datetime import datetime
from pathlib import Path

for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "ecommerce"
JD_RAW = RAW / "jd"
STAGING = ROOT / "city_data/reference/staging"
RAW.mkdir(parents=True, exist_ok=True)
STAGING.mkdir(parents=True, exist_ok=True)

UA_PC = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
UA_MOBILE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

CITIES = ["大连", "丹东", "铁岭", "锦州", "朝阳"]
NOW = datetime.now()
RUN_DATE = NOW.strftime("%Y-%m-%d")
RETRIEVAL = NOW.isoformat(timespec="seconds")

# ---------------------------------------------------------------- 探测目标登记

# access_hint 仅为登记时的先验判断，最终状态以本次探测结果为准。
# app_first=True：该平台商品/价格/门店页仅存在于 APP 或小程序，网页端只有落地页；
#   故网页端无公开商品数据时结论记为 ACCESS_RESTRICTED（需登录/APP），而非"无此页面"。
PLATFORMS = [
    dict(key="jd", label="京东", level="ecommerce", app_first=False, access_hint="CURRENT_SNAPSHOT_LIMITED",
         urls=[("首页", "https://www.jd.com/", UA_PC),
               ("站点搜索", "https://search.jd.com/Search?keyword=%E7%99%BD%E8%8F%9C&enc=utf-8", UA_PC),
               ("SEO价格行情列表", "https://www.jd.com/jiage/122183ac2b2b42f1501ca.html", UA_PC),
               ("移动商品页(样本)", "https://item.m.jd.com/product/100068259454.html", UA_MOBILE)]),
    dict(key="jd_now", label="京东秒送", level="instant_retail", app_first=True, access_hint="ACCESS_RESTRICTED",
         urls=[("官网", "https://www.imdada.cn/", UA_PC)]),
    dict(key="7fresh", label="七鲜", level="instant_retail", app_first=True, access_hint="ACCESS_RESTRICTED",
         urls=[("官网", "https://www.7fresh.com/", UA_PC)]),
    dict(key="meituan_shangou", label="美团闪购", level="instant_retail", app_first=True, access_hint="ACCESS_RESTRICTED",
         urls=[("i.meituan", "https://i.meituan.com/", UA_MOBILE),
               ("外卖H5", "https://h5.waimai.meituan.com/", UA_MOBILE)]),
    dict(key="xiaoxiang", label="小象超市", level="instant_retail", app_first=True, access_hint="ACCESS_RESTRICTED",
         urls=[("market.meituan", "https://market.meituan.com/", UA_MOBILE)]),
    dict(key="duoduo_maicai", label="多多买菜", level="instant_retail", app_first=True, access_hint="ACCESS_RESTRICTED",
         urls=[("买菜入口", "https://mobile.yangkeduo.com/duoduo_maicai.html", UA_MOBILE)]),
    dict(key="hema", label="盒马", level="instant_retail", app_first=True, access_hint="ACCESS_RESTRICTED",
         urls=[("官网", "https://www.freshippo.com/", UA_PC)]),
    dict(key="taobao_shangou", label="淘宝闪购", level="instant_retail", app_first=True, access_hint="ACCESS_RESTRICTED",
         urls=[("淘宝闪购", "https://taobaoshangou.ele.me/", UA_MOBILE)]),
    dict(key="local_market", label="当地超市线上商城", level="instant_retail", app_first=True,
         access_hint="ACCESS_RESTRICTED",
         urls=[("大商集团", "https://www.dashang.com/", UA_PC),
               ("大润发官网", "https://www.rt-mart.com.cn/", UA_PC),
               ("华润万家", "https://www.crv.com.cn/", UA_PC),
               ("永辉超市", "https://www.yonghui.com.cn/", UA_PC),
               ("沃尔玛中国", "https://www.walmart.cn/", UA_PC)]),
]

# 未登录状态下出现即说明"必须登录/验证"的强标记
MARK_LOGIN = ["spiderindefence", "verify.meituan.com", "身份核实", "安全验证", "滑块",
              "passport.jd.com", "login.taobao.com", "请登录", "登录后查看", "登录查看价格"]
MARK_APP_ONLY = ["打开APP", "打开App", "下载APP", "下载App", "下载客户端", "客户端下载",
                 "扫码下载", "扫码", "小程序"]
MARK_LOCATE = ["收货地址", "选择门店", "切换门店", "配送至", "请选择城市", "当前城市", "定位"]
MARK_PROD = ['"skuName"', '"skuId"', 'data-skuId="', "sku-price", "goodsName",
             "minGroupPrice", "jdprice_amount"]

# ---------------------------------------------------------------- HTTP


def http_get(url: str, ua: str, referer: str | None = None,
             timeout: int = 20, retries: int = 2) -> dict:
    last = None
    for attempt in range(retries + 1):
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        }
        if referer:
            headers["Referer"] = referer
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
                raw = resp.read()
                enc = (resp.headers.get("Content-Encoding") or "").lower()
                if "gzip" in enc:
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:  # noqa: BLE001
                        pass
                elif "deflate" in enc:
                    try:
                        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
                    except Exception:  # noqa: BLE001
                        pass
                return {"ok": True, "http": resp.status, "raw": raw,
                        "final_url": resp.geturl(), "content_type": resp.headers.get("Content-Type", "")}
        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            if exc.code in (403, 404, 410):
                return {"ok": True, "http": exc.code, "raw": body, "final_url": url,
                        "content_type": (exc.headers or {}).get("Content-Type", "")}
            last = exc
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(1.2 * (attempt + 1))
    return {"ok": False, "http": 0, "raw": b"", "final_url": url,
            "content_type": "", "error": f"{type(last).__name__}: {last}"}


def decode(raw: bytes) -> str:
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(enc)
        except Exception:  # noqa: BLE001
            continue
    return raw.decode("utf-8", "ignore")


# 反爬挑战页标记：命中则非真实内容页，重试；仍命中则按"需登录/验证"记 ACCESS_RESTRICTED
ANTIBOT_MARKERS = ("京东验证", "请验证", "fas-potato/verify", "spiderindefence", "安全验证", "身份核实")


def http_get_checked(url: str, ua: str, referer: str | None = None, tries: int = 3) -> dict:
    """带反爬页重试的抓取：普通 200 挑战页不算成功，退避重试。"""
    res = http_get(url, ua, referer, retries=0)
    for i in range(1, tries):
        txt = decode(res["raw"]) if res["ok"] else ""
        if not any(m in txt for m in ANTIBOT_MARKERS):
            break
        time.sleep(1.5 * i)
        res = http_get(url, ua, referer, retries=0)
    return res


def _title(txt: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", txt, re.S | re.I)
    return m.group(1).strip()[:80] if m else ""


def signals(txt: str) -> dict:
    head = txt[:300000]
    return {
        "login": [k for k in MARK_LOGIN if k in head],
        "app_only": [k for k in MARK_APP_ONLY if k in head],
        "locate": [k for k in MARK_LOCATE if k in head],
        "prod": [k for k in MARK_PROD if k in head],
        "spa_shell": ("create-react-app" in head) or ('id="ice-container"' in head),
    }


def classify(final_url: str, http: int, txt: str, sig: dict) -> str:
    if http == 0:
        return "NETWORK_FAILED"
    if any(m in final_url for m in ("verify.meituan.com", "passport.", "error.taobao.com", "login.")):
        return "ACCESS_RESTRICTED"
    if any(m in txt for m in ("spiderindefence", "身份核实", "京东验证", "请验证", "fas-potato/verify")):
        return "ACCESS_RESTRICTED"
    # 价格需登录的显式信号（京东等）优先判定，避免模板中的 "￥" 误判为公开价
    if "登录查看价格" in txt or "登录后查看" in txt:
        return "CURRENT_SNAPSHOT_LIMITED" if sig["prod"] else "ACCESS_RESTRICTED"
    masked = re.search(r'"jdPrice":"([^"]*)"', txt)
    if masked and "?" in masked.group(1):
        return "CURRENT_SNAPSHOT_LIMITED"
    if http in (403, 404, 410):
        return "ACCESS_RESTRICTED" if http == 403 else "NOT_PUBLICLY_AVAILABLE"
    public_price = (re.search(r'"jdPrice":"\d', txt)
                    or re.search(r'"p":"[\d.]+"', txt)
                    or re.search(r'"(?:minGroupPrice|minNormalPrice)"\s*:\s*\d+', txt))
    if sig["prod"] and public_price:
        return "ACCESSIBLE_PUBLIC"
    if sig["spa_shell"] and not sig["prod"]:
        return "ACCESS_RESTRICTED"
    if not sig["prod"]:
        return "NOT_PUBLICLY_AVAILABLE"
    return "CURRENT_SNAPSHOT_LIMITED"


def probe_url(label: str, url: str, ua: str, referer: str | None = None) -> dict:
    res = http_get_checked(url, ua, referer)
    txt = decode(res["raw"]) if res["ok"] else ""
    sig = signals(txt) if txt else {"login": [], "app_only": [], "locate": [], "prod": [], "spa_shell": False}
    status = classify(res["final_url"], res["http"], txt, sig)
    return {
        "name": label, "url": url, "http": res["http"], "final_url": res["final_url"],
        "content_type": res.get("content_type", ""), "bytes": len(res["raw"]),
        "title": _title(txt), "status": status,
        "signals": sig, "error": res.get("error"),
    }


# ---------------------------------------------------------------- 平台探测


def probe_all() -> list[dict]:
    print("=" * 74)
    print("第一步：逐平台免登录可达性探测")
    print("=" * 74)
    report = []
    for plat in PLATFORMS:
        entry = dict(key=plat["key"], label=plat["label"], level=plat["level"],
                     app_first=plat["app_first"], access_hint=plat["access_hint"], probes=[])
        order = {"ACCESSIBLE_PUBLIC": 0, "CURRENT_SNAPSHOT_LIMITED": 1,
                 "ACCESS_RESTRICTED": 2, "NOT_PUBLICLY_AVAILABLE": 3, "NETWORK_FAILED": 4}
        best = "NETWORK_FAILED"
        for label, url, ua in plat["urls"]:
            ref = "https://item.m.jd.com/" if "item.m.jd.com" in url else None
            p = probe_url(label, url, ua, referer=ref)
            entry["probes"].append(p)
            if order[p["status"]] < order[best]:
                best = p["status"]
            print(f"  [{plat['label']:<10}] {label:<14} http={p['http']:<4} "
                  f"{p['status']:<24} {p['title'][:28]!r}")
            time.sleep(0.5)
        # APP/小程序优先平台：网页端只有落地页，商品/价格页在 APP 内 → 记需登录/APP
        if plat["app_first"] and best == "NOT_PUBLICLY_AVAILABLE":
            best = "ACCESS_RESTRICTED"
        entry["status"] = best
        report.append(entry)
    return report


def parse_jd_html(txt: str, sku: str) -> dict:
    """京东移动商品页：未登录可见 商品名+规格+店铺；价格由 priceLoginText 判定是否需登录。"""
    def g(key):
        m = re.search(r'"%s"\s*:\s*"([^"]{0,120})"' % key, txt)
        return m.group(1) if m else None
    return {
        "sku": sku,
        "sku_name": g("skuName"), "shop_name": g("shopName"), "brand_name": g("brandName"),
        "vender_id": g("venderId"), "area_id": g("areaId"),
        "price_login_text": g("priceLoginText"), "masked_price": g("jdPrice"),
        "has_price_field": '"jdPrice"' in txt,
    }


def jd_risk_blocked(res: dict) -> bool:
    """京东风控：跳转 cfe.m.jd.com/privatedomain/risk_handler 或返回"京东验证"页。"""
    txt = decode(res["raw"]) if res["ok"] else ""
    return "risk_handler" in (res.get("final_url") or "") or "京东验证" in txt


def fetch_jd_product(sku: str) -> tuple[dict, bytes, bool, bool]:
    """返回 (parsed, raw_bytes, from_cache, risk_blocked)。已落盘则复用，不重复请求（幂等）。"""
    target = JD_RAW / f"{sku}.html"
    if target.exists() and target.stat().st_size > 5000:
        raw = target.read_bytes()
        return parse_jd_html(decode(raw), sku), raw, True, False
    res = http_get(f"https://item.m.jd.com/product/{sku}.html", UA_MOBILE,
                   referer="https://item.m.jd.com/", retries=1)
    raw = res["raw"]
    return (parse_jd_html(decode(raw) if res["ok"] else "", sku), raw, False,
            jd_risk_blocked(res))


# ---------------------------------------------------------------- 京东快照采集

# 公开 SEO 列表页（服务端渲染，含 item.jd.com/{sku}.html 链接）——用于发现 SKU。
JD_SEO_PAGES = [
    "https://www.jd.com/jiage/122183ac2b2b42f1501ca.html",
    "https://www.jd.com/hprm/1221866ad6234966c76f8.html",
]

# 手工登记的公开生鲜 SKU（来源：上述 SEO 列表页 / 该站点公开商品链接），保证小样本可复现。
JD_SEED_SKUS = [
    "100068259454", "100163036854", "7925600", "100106239678", "100247411982",
    "100161814240", "100291627517", "100141423850", "100096610531", "100153951475",
    "100156788971", "100168642981", "100280888310", "100165071091", "100129671630",
    "100072182273", "100156788999", "3877141", "100178353922", "100094760931",
    "100115801041", "100101523077", "100036383763", "10194507266553", "10180337211423",
    "10122930474473", "10208115774459", "10197323515759", "10209011521103", "10151879152732",
    "100200027308", "10170522587043", "10151933723094",
]

CROP_MAP = [
    ("大白菜", "大白菜"), ("娃娃菜", "娃娃菜"), ("黄心白菜", "大白菜"), ("小白菜", "小白菜"),
    ("上海青", "上海青"), ("油菜", "油菜"), ("青菜", "青菜"), ("生菜", "生菜"),
    ("西兰花", "西兰花"), ("西兰苔", "西兰苔"), ("龙芽菜", "龙芽菜"), ("羽衣甘蓝", "羽衣甘蓝"),
    ("甘蓝", "甘蓝"), ("包菜", "甘蓝"), ("卷心菜", "甘蓝"),
    ("番茄", "番茄"), ("西红柿", "番茄"), ("圣女果", "樱桃番茄"),
    ("茄子", "茄子"), ("南瓜", "南瓜"), ("蜜薯", "甘薯"), ("红薯", "甘薯"),
    ("玉米", "玉米"), ("芹菜", "芹菜"),
]

_SPEC_PAT = re.compile(r"(净重\s*[\d.]+\s*[斤千克克gG]|\d+(?:\.\d+)?\s*[斤千克gG]|[\d.]+\s*[gG])\s*(?:装)?")


def extract_spec(name: str) -> str | None:
    m = _SPEC_PAT.search(name or "")
    return m.group(1).replace(" ", "") if m else None


def extract_crop(name: str) -> str | None:
    for kw, std in CROP_MAP:
        if kw in (name or ""):
            return std
    return None


def discover_jd_skus() -> list[str]:
    found: list[str] = []
    for page in JD_SEO_PAGES:
        res = http_get(page, UA_PC, referer="https://www.jd.com/")
        if not res["ok"]:
            continue
        txt = decode(res["raw"])
        found += re.findall(r"item\.jd\.com/(\d{6,})\.html", txt)
        time.sleep(0.6)
    seen, ordered = set(), []
    for s in JD_SEED_SKUS + found:
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    return ordered


def collect_jd(limit: int | None) -> list[dict]:
    print("\n" + "=" * 74)
    print("第二步：京东（CURRENT_SNAPSHOT_LIMITED）商品页快照采集")
    print("=" * 74)
    JD_RAW.mkdir(parents=True, exist_ok=True)
    skus = discover_jd_skus()
    if limit:
        skus = skus[:limit]
    rows, new_files, cache_hits, skipped, risk_streak = [], 0, 0, 0, 0
    for sku in skus:
        target = JD_RAW / f"{sku}.html"
        info, raw, from_cache, risk = fetch_jd_product(sku)
        if risk:
            skipped += 1
            risk_streak += 1
            print(f"  [jd] {sku} -> 风控页（本轮跳过）连续={risk_streak}")
            if risk_streak >= 4:
                print("  [jd] 连续多次风控，停止本轮采集（已采数据保留，下次续跑）")
                break
            time.sleep(3)
            continue
        risk_streak = 0
        if not info["sku_name"]:
            skipped += 1
            print(f"  [jd] {sku} -> 跳过（无 skuName：非商品页或已下架）")
            time.sleep(0.4)
            continue
        if from_cache:
            cache_hits += 1
        else:
            target.write_bytes(raw)
            new_files += 1
        name = info["sku_name"]
        crop = extract_crop(name)
        rows.append({
            "city": "", "county": "", "market_name": "", "store_name": info["shop_name"] or "",
            "platform": "京东", "crop_raw": crop or "", "crop_standard": crop or "",
            "sku_name": name, "specification": extract_spec(name) or "", "package_size": extract_spec(name) or "",
            "price_original": "", "unit_original": "", "price_per_kg": "",
            "price_level": "ecommerce",
            "observation_date": RUN_DATE, "observation_time": RETRIEVAL, "frequency": "daily",
            "source_type": "ecommerce_platform", "source_name": "京东移动商品页",
            "source_url": f"https://item.m.jd.com/product/{sku}.html", "source_id": "SRC-JD-ITEM",
            "retrieval_time": RETRIEVAL,
            "promotion_flag": "False", "member_price_flag": "False", "derived_flag": "True",
            "quality_grade": "C", "raw_file": f"data/raw/prices/ecommerce/jd/{sku}.html",
            "geo_level": "national", "record_kind": "product_listing_no_price",
            "note": (f"price_level=ecommerce;价格未公开(priceLoginText={info['price_login_text']};"
                     f"掩码价={info['masked_price']});地区/门店需登录或APP;sku={sku};"
                     f"brand={info['brand_name']};venderId={info['vender_id']}"),
            "access_status": "CURRENT_SNAPSHOT_LIMITED",
        })
        print(f"  [jd] {sku} -> {name[:34]!r} 店铺={info['shop_name']!r} 价格={info['price_login_text']!r}")
        time.sleep(0.6)
    print(f"  [jd] 有效商品页 {len(rows)} / 候选 {len(skus)}"
          f"（本次新落盘 {new_files}，复用缓存 {cache_hits}，跳过/风控 {skipped}）")
    return rows


# ---------------------------------------------------------------- 落盘

STAGING_COLUMNS = [
    "city", "county", "market_name", "store_name", "platform",
    "crop_raw", "crop_standard", "sku_name", "specification", "package_size",
    "price_original", "unit_original", "price_per_kg", "price_level",
    "observation_date", "observation_time", "frequency",
    "source_type", "source_name", "source_url", "source_id", "retrieval_time",
    "promotion_flag", "member_price_flag", "derived_flag",
    "quality_grade", "raw_file", "geo_level", "record_kind", "note", "access_status",
]


def write_status_csv(report: list[dict]) -> Path:
    path = RAW / "platform_probe_status.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["platform_key", "platform_label", "price_level", "access_status",
                    "商品", "规格", "价格", "地区", "门店", "probe_url", "title", "note"])
        for e in report:
            first = e["probes"][0] if e["probes"] else {}
            st = e["status"]
            have = ("Y" if st == "ACCESSIBLE_PUBLIC" else
                    ("部分" if st == "CURRENT_SNAPSHOT_LIMITED" else "N"))
            w.writerow([
                e["key"], e["label"], e["level"], st,
                have, have,
                "Y" if st == "ACCESSIBLE_PUBLIC" else ("N(需登录)" if st in (
                    "ACCESS_RESTRICTED", "CURRENT_SNAPSHOT_LIMITED") else "N"),
                "N(需APP)", have if st == "ACCESSIBLE_PUBLIC" else "N(需APP)",
                first.get("url", ""), first.get("title", ""),
                "；".join(f"{p['name']}:{p['status']}" for p in e["probes"]),
            ])
    return path


def write_staging(rows: list[dict]) -> Path:
    path = STAGING / "ecommerce_price_snapshot.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=STAGING_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe-only", action="store_true", help="只做可行性探测，不采集商品页")
    ap.add_argument("--limit", type=int, default=None, help="京东最多采集的 SKU 数")
    args = ap.parse_args()

    report = probe_all()

    rows: list[dict] = []
    if not args.probe_only:
        rows = collect_jd(args.limit)
        if rows:
            # 实测证据：京东移动商品页免登录可达（商品+规格+店铺）→ 校准平台结论
            for e in report:
                if e["key"] == "jd":
                    e["status"] = "CURRENT_SNAPSHOT_LIMITED"
                    e["note"] = (f"移动商品页实测采集 {len(rows)} 条：商品/规格/店铺免登录可见，"
                                 f"价格需登录（priceLoginText=登录查看价格），地区/门店需APP")
                    break

    (RAW / "probe_report.json").write_text(
        json.dumps({"generated_at": RETRIEVAL, "cities": CITIES, "platforms": report},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    status_csv = write_status_csv(report)
    staging = write_staging(rows)

    print("\n" + "=" * 74)
    print("平台可行性结论（未登录状态）")
    print("=" * 74)
    for e in report:
        print(f"  {e['label']:<12} {e['level']:<14} {e['status']}")
    print(f"\n  京东商品快照行数 : {len(rows)}")
    print(f"  原始落盘 : {RAW.relative_to(ROOT)}")
    print(f"  状态表   : {status_csv.relative_to(ROOT)}")
    print(f"  Staging  : {staging.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
