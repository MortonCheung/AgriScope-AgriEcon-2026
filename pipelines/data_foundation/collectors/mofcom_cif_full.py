"""商务部「商务预报 / 生活必需品 / 百家日报」全量采集（cif.mofcom.gov.cn）。

子命令：
  probe   探测辽宁各市商务预报子站是否存在（index + listPage 计数）
  sites   枚举地方子站栏目文章（大连/辽宁/朝阳…）并下载原始 HTML
  nodes   枚举国家级栏目（国内月报/市场扫描/信息精选）中的辽宁城市文章并下载
  baijia  百家日报：枚举辽宁市场 × 品种，回溯日度历史价格（FusionCharts XML）
  parse   解析已下载原始 HTML → city_data/reference/staging/mofcom_prices.csv / mofcom_volumes.csv
  all     依次执行 probe→sites→nodes→baijia→parse

产出：
  data/raw/prices/mofcom/<slug>/html/<hash>.html     文章原始字节（不转码）
  data/raw/prices/mofcom/baijia/html/<cid>__<eid>__<yyyy>.html
  data/raw/prices/mofcom/*.json                      探测/清单/报告
  city_data/reference/staging/mofcom_prices.csv                     结构化历史价格
  city_data/reference/staging/mofcom_volumes.csv                    成交量/上市量观测

口径红线：
  - 只走公开页面/公开接口，不绕过登录/验证码；受限一律记 ACCESS_RESTRICTED
  - 数据缺失即留空，不插值、不编造
  - 市场级数据一律 geo_level=market，不冒充城市口径
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "mofcom"
STAGING = ROOT / "city_data/reference/staging"
STAGING.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
BASE = "https://cif.mofcom.gov.cn"
SLEEP = 0.4

# --- 目标城市 / 子站 ---------------------------------------------------------
# slug 经实测：仅 dalian / liaoning / chaoyang 等存在；其余返回 404（记 NOT_FOUND）
CANDIDATE_SLUGS = ["dalian", "dandong", "tieling", "jinzhou", "chaoyang", "shenyang",
                   "anshan", "benxi", "fushun", "yingkou", "fuxin", "liaoyang",
                   "panjin", "huludao", "beipiao", "kaiyuan", "dengta"]

CITY_SITES = [
    {"city": "大连", "slug": "dalian",
     "blocks": {"24511242": "生活必需品动态", "24511241": "消费市场监测",
                "24511240": "市场运行信息"}},
    {"city": "辽宁省", "slug": "liaoning", "blocks": {"493865": "运行工作信息"}},
    {"city": "朝阳", "slug": "chaoyang", "blocks": {"538252": "监测分析"}},
]

# 国家级栏目 nodeId（moreReport 分页接口）
NODE_SCAN = {10360: "国内月报", 10402: "市场扫描", 10400: "信息精选"}
NODE_MAX_PAGES = {10360: 130, 10402: 300, 10400: 60}

TARGET_CITIES = ["大连", "丹东", "铁岭", "锦州", "朝阳",
                 "沈阳", "鞍山", "抚顺", "本溪", "营口", "阜新", "辽阳", "盘锦", "葫芦岛"]

# 百家日报：辽宁市场 enterid → 归属
BAIJIA_MARKETS = {
    "3885": {"city": "大连", "county": "", "market": "大连双兴商品城有限公司"},
    "43186": {"city": "沈阳", "county": "", "market": "沈阳盛发蔬菜批发市场"},
    "3775": {"city": "锦州", "county": "北镇市", "market": "北镇市窟窿台翠龙蔬菜服务公司"},
}
BAIJIA_YEARS = list(range(2013, 2027))


# --- HTTP -------------------------------------------------------------------
def _ctx() -> ssl.SSLContext:
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    try:
        c.set_ciphers("DEFAULT@SECLEVEL=1")
    except Exception:
        pass
    return c


def decode(raw: bytes) -> str:
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def http_get_bytes(url: str, referer: str | None = None, tries: int = 4) -> bytes:
    last = None
    for a in range(tries):
        try:
            hdr = {"User-Agent": UA, "Accept": "*/*"}
            if referer:
                hdr["Referer"] = referer
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=40, context=_ctx()) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500:
                raise
            last = exc
            time.sleep(1.5 + 1.5 * a)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 + 1.5 * a)
    raise last


def http_post(url: str, data: dict, referer: str | None = None, tries: int = 4) -> bytes:
    last = None
    for a in range(tries):
        try:
            hdr = {"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"}
            if referer:
                hdr["Referer"] = referer
            req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(),
                                         headers=hdr)
            with urllib.request.urlopen(req, timeout=40, context=_ctx()) as r:
                return r.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 + 1.5 * a)
    raise last


def save_html(slug: str, sub: str, url: str, raw: bytes) -> str:
    d = RAW / slug / sub
    d.mkdir(parents=True, exist_ok=True)
    fn = hashlib.md5(url.encode()).hexdigest()[:16] + ".html"
    f = d / fn
    if not f.exists():
        f.write_bytes(raw)
    return str(f.relative_to(ROOT))


def text_of(html: str) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", "\n", t)
    t = re.sub(r"&nbsp;|&#160;|&ldquo;|&rdquo;", " ", t)
    return t


# --- probe ------------------------------------------------------------------
def cmd_probe() -> None:
    rep = {"candidate_slugs": [], "listpage_counts": []}
    for slug in CANDIDATE_SLUGS:
        item = {"slug": slug}
        for path in (f"/site/html/{slug}/", f"/newsite/html/{slug}/index.html"):
            url = BASE + path
            try:
                raw = http_get_bytes(url)
                html = decode(raw)
                item[path] = {"status": 200, "bytes": len(raw),
                              "title": (re.search(r"<title>(.*?)</title>", html, re.S) or ["", ""])[1].strip()}
            except Exception as exc:  # noqa: BLE001
                item[path] = {"status": "ERR", "error": str(exc)[:100]}
            time.sleep(SLEEP)
        rep["candidate_slugs"].append(item)
        print(f"  [{slug}] {item.get(f'/site/html/{slug}/', {}).get('status')}")
    for site in CITY_SITES:
        for bid, name in site["blocks"].items():
            url = (f"{BASE}/newsite/content/content/front/listPage"
                   f"?current=1&size=20&blockid={bid}")
            try:
                html = decode(http_get_bytes(url, referer=f"{BASE}/site/html/{site['slug']}/"))
                cnt = re.search(r"count:\s*(\d+)", html)
                rep["listpage_counts"].append({"city": site["city"], "slug": site["slug"],
                                               "blockid": bid, "name": name,
                                               "count": int(cnt.group(1)) if cnt else None})
                print(f"  [{site['city']} {name}] blockid={bid} count={cnt.group(1) if cnt else '?'}")
            except Exception as exc:  # noqa: BLE001
                rep["listpage_counts"].append({"city": site["city"], "blockid": bid,
                                               "status": "ACCESS_RESTRICTED", "error": str(exc)[:100]})
                print(f"  [ACCESS_RESTRICTED] {site['city']} blockid={bid}: {exc}")
            time.sleep(SLEEP)
    (RAW / "probe_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    print(f"[OK] -> {RAW / 'probe_report.json'}")


# --- 地方子站文章 ------------------------------------------------------------
ART_RE = re.compile(r'href="(/newsite/html/([a-z]+)/html/(\d+)/\d{4}/\d{1,2}/\d{1,2}/\d+\.html)"')


def cmd_sites() -> None:
    manifest = {}
    for site in CITY_SITES:
        slug, city = site["slug"], site["city"]
        urls, metas = [], []
        idx_url = f"{BASE}/site/html/{slug}/"
        try:
            idx_raw = http_get_bytes(idx_url)
            save_html(slug, "listpage", idx_url, idx_raw)
        except Exception as exc:  # noqa: BLE001
            print(f"  [ACCESS_RESTRICTED] {slug} index: {exc}")
        for bid, name in site["blocks"].items():
            page, total_pages = 1, 1
            while page <= total_pages:
                url = (f"{BASE}/newsite/content/content/front/listPage"
                       f"?current={page}&size=20&blockid={bid}")
                try:
                    raw = http_get_bytes(url, referer=idx_url)
                except Exception as exc:  # noqa: BLE001
                    print(f"  [ACCESS_RESTRICTED] {city} {name} p{page}: {exc}")
                    break
                html = decode(raw)
                save_html(slug, "listpage", url, raw)
                cnt = re.search(r"count:\s*(\d+)", html)
                if cnt and page == 1:
                    total_pages = max(1, math.ceil(int(cnt.group(1)) / 20))
                for m in ART_RE.finditer(html):
                    urls.append(BASE + m.group(1))
                if page == 1:
                    print(f"  [{city} {name}] blockid={bid} 总页数={total_pages} "
                          f"count={cnt.group(1) if cnt else '?'}")
                page += 1
                time.sleep(SLEEP)
        seen, uniq = set(), []
        for u in urls:
            if u not in seen:
                seen.add(u); uniq.append(u)
        saved = 0
        for u in uniq:
            try:
                raw = http_get_bytes(u, referer=idx_url)
                rel = save_html(slug, "html", u, raw)
                metas.append({"url": u, "file": rel})
                saved += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  [ACCESS_RESTRICTED] {u}: {exc}")
            time.sleep(SLEEP)
        manifest[slug] = {"city": city, "articles": metas}
        print(f"  [OK] {city}: 去重 {len(uniq)} 篇，下载 {saved}")
    (RAW / "sites_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                             encoding="utf-8")
    print(f"[OK] -> {RAW / 'sites_manifest.json'}")


# --- 国家级栏目（辽宁城市）---------------------------------------------------
def cmd_nodes() -> None:
    hits, evidence = [], []
    for nid, maxpg in NODE_MAX_PAGES.items():
        if nid not in NODE_SCAN:
            continue
        for pg in range(1, maxpg + 1):
            try:
                j = json.loads(decode(http_post(
                    f"{BASE}/cif/moreReport.fhtml",
                    {"nodeId": str(nid), "pageNo": pg, "pageSize": 50, "random": 0.2},
                    referer=f"{BASE}/cif/listIndex.fhtml?nodeid={nid}")))
            except Exception as exc:  # noqa: BLE001
                evidence.append({"node": NODE_SCAN[nid], "page": pg,
                                 "status": "ACCESS_RESTRICTED", "error": str(exc)[:100]})
                print(f"  [ACCESS_RESTRICTED] node {nid} p{pg}: {exc}")
                break
            res = j.get("result", [])
            if not res:
                print(f"  node {NODE_SCAN[nid]} 结束于第 {pg} 页")
                break
            for it in res:
                kw = it.get("keyword") or ""
                ti = it.get("title") or ""
                src = it.get("source") or ""
                if ("辽宁" in kw or "辽宁" in src
                        or any(c in ti for c in TARGET_CITIES)):
                    hits.append({"node": NODE_SCAN[nid], "date": it.get("publishDate"),
                                 "title": ti, "keyword": kw, "source": src,
                                 "relpath": it.get("relpath"), "id": it.get("id")})
            if pg % 25 == 0:
                ds = [i.get("publishDate") for i in res if i.get("publishDate")]
                print(f"  node {NODE_SCAN[nid]} p{pg} .. {min(ds) if ds else '?'}")
            time.sleep(SLEEP)
    # 去重 + 下载
    seen, uniq = set(), []
    for h in hits:
        key = h["relpath"] or h["id"]
        if key in seen:
            continue
        seen.add(key); uniq.append(h)
    saved = 0
    for h in uniq:
        rel = (h["relpath"] or "").lstrip("/")
        url = f"{BASE}/cif/html/{rel}"
        h["url"] = url
        try:
            raw = http_get_bytes(url)
            h["raw_file"] = save_html("national", "html", url, raw)
            saved += 1
        except Exception as exc:  # noqa: BLE001
            h["raw_file"] = ""
            evidence.append({"url": url, "status": "ACCESS_RESTRICTED", "error": str(exc)[:100]})
            print(f"  [ACCESS_RESTRICTED] {url}: {exc}")
        time.sleep(SLEEP)
    (RAW / "national_liaoning_articles.json").write_text(
        json.dumps(uniq, ensure_ascii=False, indent=1), encoding="utf-8")
    (RAW / "national_evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[OK] 国家级辽宁文章 {len(uniq)} 篇（下载 {saved}）")


# --- 百家日报 ---------------------------------------------------------------
def _baijia_commodities() -> list[tuple[str, str]]:
    html = decode(http_get_bytes(f"{BASE}/cif/seach.fhtml?commdityid=170120"))
    out, seen = [], set()
    for m in re.finditer(r'href="/cif/seach\.fhtml\?commdityid=(\d+)"[^>]*>([^<]+)<', html):
        cid, nm = m.group(1), m.group(2).strip()
        if cid not in seen:
            seen.add(cid); out.append((cid, nm))
    return out


def _baijia_markets(comms: list[tuple[str, str]]) -> dict:
    found = {}
    for cid, nm in comms:
        if cid in ("130011", "130021", "130031"):
            continue
        try:
            html = decode(http_get_bytes(f"{BASE}/cif/seach.fhtml?commdityid={cid}"))
        except Exception as exc:  # noqa: BLE001
            print(f"  [ACCESS_RESTRICTED] 百家日报 {nm}: {exc}")
            continue
        tb = re.findall(r"<table.*?</table>", html, re.S | re.I)
        if not tb:
            continue
        for tr in re.findall(r"<tr.*?</tr>", tb[0], re.S | re.I):
            cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip()
                     for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
            if not cells or cells[0] != "辽宁省":
                continue
            eid = re.search(r"enterid=(\d+)", tr)
            if eid:
                found.setdefault(eid.group(1), {"market": cells[1], "commodities": {}})
                found[eid.group(1)]["commodities"][cid] = nm
        time.sleep(SLEEP)
    return found


def _parse_chart(html: str) -> list[tuple[str, float]]:
    m = re.search(r'var xml="(.*?)";', html, re.S)
    if not m:
        return []
    return [(d, float(v)) for d, v in
            re.findall(r"name='([^']+)'\s+value='\s*([0-9.]+)\s*'", m.group(1))]


def cmd_baijia() -> None:
    comms = _baijia_commodities()
    (RAW / "baijia_commodities.json").write_text(json.dumps(comms, ensure_ascii=False, indent=1),
                                                 encoding="utf-8")
    print(f"  品种 {len(comms)} 个")
    markets = _baijia_markets(comms)
    # 合并配置中的名称（enterid 归属）
    for eid, info in markets.items():
        cfg = BAIJIA_MARKETS.get(eid, {})
        info.update({k: cfg.get(k, "") for k in ("city", "county")})
        info.setdefault("market", cfg.get("market", info["market"]))
    (RAW / "baijia_markets.json").write_text(json.dumps(markets, ensure_ascii=False, indent=1),
                                             encoding="utf-8")
    print(f"  辽宁市场 {len(markets)} 个: "
          f"{[(e, v['market']) for e, v in markets.items()]}")
    saved = 0
    for eid, info in markets.items():
        for cid, nm in info["commodities"].items():
            for y in BAIJIA_YEARS:
                url = f"{BASE}/cif/seachline.fhtml"
                try:
                    raw = http_post(url, {"enterid": eid, "commdityid": cid,
                                          "Bdate": f"{y}-01-01", "Edate": f"{y}-12-31"},
                                    referer=f"{BASE}/cif/seach.fhtml?commdityid={cid}")
                except Exception as exc:  # noqa: BLE001
                    print(f"  [ACCESS_RESTRICTED] {eid}/{cid}/{y}: {exc}")
                    continue
                pts = _parse_chart(decode(raw))
                if not pts:
                    time.sleep(SLEEP)
                    continue
                d = RAW / "baijia" / "html"
                d.mkdir(parents=True, exist_ok=True)
                (d / f"{cid}__{eid}__{y}.html").write_bytes(raw)
                saved += 1
                time.sleep(SLEEP)
        print(f"  [{info['market']}] 品种 {len(info['commodities'])} 完成")
    print(f"[OK] 百家日报原始 HTML 片段 {saved} 个 -> {RAW / 'baijia'}")


# --- 解析 -------------------------------------------------------------------
DL_CROPS = set("""青椒 芸豆 黄瓜 茄子 西红柿 芹菜 韭菜 菠菜 蒜苔 甘蓝 大白菜 青萝卜 土豆
圆葱 油菜 尖椒 冬瓜 茭瓜 菜花 胡萝卜 白萝卜 生菜 小白菜 油麦菜 南瓜 豆角 香菜 茼蒿
苦瓜 丝瓜 西葫芦 山药 莲藕 生姜 大蒜 大葱 蒜苗 甘蓝 西兰花 空心菜""".split())

P_FIELDS = ["date", "city", "district", "geo_level", "market_name", "crop_raw", "variety",
            "price_type", "frequency", "price", "unit_raw", "price_per_kg", "source_id",
            "source_name", "source_url", "raw_file", "quality_grade", "note"]
V_FIELDS = ["date", "city", "county", "market_name", "crop", "volume", "volume_unit",
            "volume_type", "geo_level", "source_id", "source_name", "source_url",
            "raw_file", "quality_grade", "note"]

VOL_PAT = re.compile(r"(日均蔬菜上市量|日均上市蔬菜|日均蔬菜交易量|蔬菜日均上市量|日均上市量|"
                     r"日均交易量|日均成交量|上市量|成交量|交易量|供应量)"
                     r"[^0-9。；]{0,15}?([0-9]+(?:\.[0-9]+)?)\s*(吨|万公斤|公斤|万斤|斤)")


def parse_dalian_article(path: Path, url: str, slug: str) -> tuple[list, list]:
    t = decode(path.read_bytes())
    prices, vols = [], []
    if "批发价格" not in t:
        # 仍尝试抽上市量
        pass
    dm = re.search(r"统计表（(\d{1,2})月(\d{1,2})日）", t)
    ym = re.search(r"发布时间：\s*(20\d\d)", t)
    date = ""
    if dm and ym:
        date = f"{ym.group(1)}-{int(dm.group(1)):02d}-{int(dm.group(2)):02d}"
    elif ym:
        date = ym.group(1)
    body = text_of(t)
    lines = [x.strip() for x in body.split("\n") if x.strip()]
    joined = "\n".join(lines)
    mk = re.search(r"序号\s*品种\s*([\u4e00-\u9fa5]{2,8})\s*([\u4e00-\u9fa5]{2,8})", joined)
    mk1, mk2 = (mk.group(1), mk.group(2)) if mk else ("双兴", "南关岭")
    i = 0
    while i < len(lines):
        if (re.fullmatch(r"\d{1,3}", lines[i]) and i + 1 < len(lines)
                and lines[i + 1] in DL_CROPS):
            name = lines[i + 1]
            nums = lines[i + 2:i + 7]
            for idx, mname in ((0, mk1), (1, mk2)):
                if idx >= len(nums):
                    continue
                try:
                    v = float(nums[idx])
                except ValueError:
                    continue
                if v <= 0:
                    continue
                prices.append({
                    "date": date, "city": "大连", "district": "",
                    "geo_level": "market", "market_name": mname, "crop_raw": name,
                    "variety": "", "price_type": "wholesale", "frequency": "weekly",
                    "price": v, "unit_raw": "元/公斤", "price_per_kg": v,
                    "source_id": "SRC-MOFCOM-CIF-DL",
                    "source_name": "商务部 大连商务预报（大连市商务局）",
                    "source_url": url, "raw_file": str(path.relative_to(ROOT)),
                    "quality_grade": "A",
                    "note": "蔬菜批发价格汇总统计表（双兴/南关岭，元/公斤）"})
            i += 7
        else:
            i += 1
    # 上市量
    for m in VOL_PAT.finditer(re.sub(r"\s+", "", body)):
        verb, num, unit = m.group(1), float(m.group(2)), m.group(3)
        unit_std = {"万公斤": "吨", "万斤": "吨", "斤": "吨", "公斤": "吨"}.get(unit, unit)
        if unit == "万公斤":
            num *= 10
        elif unit == "万斤":
            num *= 5
        elif unit == "公斤":
            num /= 1000
        elif unit == "斤":
            num /= 2000
        vols.append({
            "date": date, "city": "大连", "county": "",
            "market_name": "大连市内主要批发市场（合计）", "crop": "蔬菜",
            "volume": num, "volume_unit": unit_std,
            "volume_type": "turnover" if "交易" in verb else "inflow",
            "geo_level": "market", "source_id": "SRC-MOFCOM-CIF-DL",
            "source_name": "商务部 大连商务预报（大连市商务局）",
            "source_url": url, "raw_file": str(path.relative_to(ROOT)),
            "quality_grade": "A", "note": f"原文片段：{m.group(0)[:80]}"})
    return prices, vols


JP_SECTION = re.compile(r"(粮食|桶装食用油|食用油|肉类|猪肉|禽蛋|鸡蛋|蔬菜|水果|水产品|副食品)")
NUM = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(元/公斤|元/升|元/500克)")


def parse_monthly_article(path: Path, url: str, city: str, source: str) -> list:
    """国内月报·城市生活必需品月分析：抽取'XX均价X元/公斤'文本级价格。"""
    t = decode(path.read_bytes())
    dm = re.search(r"(\d{4})年(\d{1,2})月份", t)
    date = f"{dm.group(1)}-{int(dm.group(2)):02d}" if dm else ""
    rows = []
    body = text_of(t)
    for m in NUM.finditer(body):
        seg = body[max(0, m.start() - 40):m.start()]
        sm = re.search(r"([\u4e00-\u9fa5]{2,6})(零售均价|平均价格|均价|价格)$", seg)
        item = sm.group(1) if sm else ""
        if not item:
            continue
        rows.append({
            "date": date, "city": city, "district": "", "geo_level": "city",
            "market_name": "全市", "crop_raw": item, "variety": "",
            "price_type": "retail" if "零售" in seg else "avg",
            "frequency": "monthly", "price": float(m.group(1)),
            "unit_raw": m.group(2), "price_per_kg": float(m.group(1)) if "公斤" in m.group(2) else "",
            "source_id": "SRC-MOFCOM-CIF-JZ",
            "source_name": source, "source_url": url,
            "raw_file": str(path.relative_to(ROOT)), "quality_grade": "B",
            "note": f"月分析文本抽取：{seg[-30:]}{m.group(0)}"})
    return rows


def cmd_parse() -> None:
    prices, vols = [], []
    # 大连/辽宁/朝阳 子站文章
    sites = json.loads((RAW / "sites_manifest.json").read_text(encoding="utf-8")) \
        if (RAW / "sites_manifest.json").exists() else {}
    for slug, info in sites.items():
        for a in info["articles"]:
            f = ROOT / a["file"]
            if not f.exists():
                continue
            if slug == "dalian":
                p, v = parse_dalian_article(f, a["url"], slug)
                prices += p; vols += v
            else:
                p, v = parse_dalian_article(f, a["url"], slug)
                prices += p; vols += v
    # 国家级·辽宁城市月报
    nat = json.loads((RAW / "national_liaoning_articles.json").read_text(encoding="utf-8")) \
        if (RAW / "national_liaoning_articles.json").exists() else []
    for h in nat:
        f = ROOT / h["raw_file"] if h.get("raw_file") else None
        if not f or not f.exists():
            continue
        city = next((c for c in TARGET_CITIES if c in (h.get("title") or "")), "")
        if not city:
            continue
        prices += parse_monthly_article(f, h["url"], city, h.get("source") or "商务部商务预报")
    # 百家日报
    bdir = RAW / "baijia" / "html"
    if bdir.exists():
        markets = json.loads((RAW / "baijia_markets.json").read_text(encoding="utf-8"))
        comms = dict(json.loads((RAW / "baijia_commodities.json").read_text(encoding="utf-8")))
        for f in sorted(bdir.glob("*.html")):
            cid, eid, y = f.stem.split("__")
            info = markets.get(eid, {})
            for d, v in _parse_chart(decode(f.read_bytes())):
                prices.append({
                    "date": d, "city": info.get("city", ""),
                    "district": info.get("county", ""), "geo_level": "market",
                    "market_name": info.get("market", ""), "crop_raw": comms.get(cid, cid),
                    "variety": "", "price_type": "wholesale", "frequency": "daily",
                    "price": v, "unit_raw": "元/公斤", "price_per_kg": v,
                    "source_id": "SRC-MOFCOM-CIF-BAIJIA",
                    "source_name": "商务部商务预报·百家日报",
                    "source_url": f"{BASE}/cif/seachline.fhtml?enterid={eid}&commdityid={cid}",
                    "raw_file": str(f.relative_to(ROOT)), "quality_grade": "A",
                    "note": f"百家日报日度批发价（{info.get('market','')}）"})
    pdf = pd.DataFrame(prices, columns=P_FIELDS).drop_duplicates(
        subset=["date", "market_name", "crop_raw", "price_type"])
    pdf.to_csv(STAGING / "mofcom_prices.csv", index=False, encoding="utf-8-sig")
    vdf = pd.DataFrame(vols, columns=V_FIELDS).drop_duplicates(
        subset=["date", "market_name", "crop", "volume", "volume_type"])
    vdf.to_csv(STAGING / "mofcom_volumes.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] mofcom_prices.csv {len(pdf)} 行")
    if len(pdf):
        print(f"     日期 {pdf['date'].min()} ~ {pdf['date'].max()}")
        print(f"     城市 {sorted(pdf['city'].unique())}")
        print(f"     市场 {sorted(pdf['market_name'].unique())}")
        print(f"     品种 {pdf['crop_raw'].nunique()} 种")
    print(f"[OK] mofcom_volumes.csv {len(vdf)} 行")


CMDS = {"probe": cmd_probe, "sites": cmd_sites, "nodes": cmd_nodes,
        "baijia": cmd_baijia, "parse": cmd_parse}


def main() -> None:
    args = sys.argv[1:] or ["all"]
    for a in args:
        if a == "all":
            for c in ["probe", "sites", "nodes", "baijia", "parse"]:
                print(f"\n===== {c} =====")
                CMDS[c]()
        elif a in CMDS:
            print(f"\n===== {a} =====")
            CMDS[a]()
        else:
            print(f"unknown command: {a}")


if __name__ == "__main__":
    main()
