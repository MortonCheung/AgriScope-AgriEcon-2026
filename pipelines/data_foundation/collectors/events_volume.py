"""成交量 / 供应量（五城非价格数据，P0）采集。

口径红线：官方只发布「某批发市场（或若干市场合计）日均上市量」时，一律记
geo_level=market、volume_type=inflow，**不得冒充城市总上市量**。
省级口径（如"全省重点批发市场当日交易量"）记 geo_level=province。

同义词检索：交易量/上市量/进场量/到货量/供应量/吞吐量/日均交易/电子结算。

产出：city_data/reference/staging/volume_observations.csv
原始 HTML：data/raw/volume_supply/
证据（含未命中/受限）：data/raw/volume_supply/search_evidence.csv
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _events_util import (ROOT, dl_gov_list, fetch_article, harvest_list, now,  # noqa: E402
                          run_curated, write_csv)

TOPIC = "volume_supply"

VOL_WORDS = (r"上市量|上市蔬菜|上市蔬菜量|上市量|交易量|成交量|进货量|进场量|到货量|"
             r"供应量|销售量|吞吐量|日均交易量|日均交易额|日均销量|日均上市|日上市量|"
             r"日均进场|日进场量|进货|上市")
UNIT_WORDS = r"吨|万斤|公斤|斤|头|万头|车次|辆次|万公斤"

TITLE_KW = re.compile(
    r"上市量|交易量|成交量|供应量|吞吐量|进场量|到货量|日均交易|电子结算|"
    r"保供|供应|上市|货源|购销|投放|调运|成交量|蔬菜市场|批发市场|菜篮")

# 栏目清单：省级 + 五城市（大连/丹东/铁岭/锦州/朝阳）
COLUMNS = [
    {"site": "辽宁省农业农村厅", "name": "通知公告", "url": "https://nync.ln.gov.cn/nync/index/tzgg/index.shtml"},
    {"site": "辽宁省农业农村厅", "name": "种植业管理", "url": "https://nync.ln.gov.cn/nync/index/ywgl/scgl/zzygl/index.shtml"},
    {"site": "辽宁省农业农村厅", "name": "行业动态", "url": "https://nync.ln.gov.cn/nync/index/nyyw/nyxw/gzdt/index.shtml"},
    {"site": "大连市人民政府", "name": "民生热点", "url": "https://www.dl.gov.cn/col/col1190/index.html"},
    {"site": "大连市人民政府", "name": "百姓日常", "url": "https://www.dl.gov.cn/col/col1437/index.html"},
    {"site": "大连市商务局", "name": "商务动态", "url": "https://www.dl.gov.cn/col/col1932/index.html"},
    {"site": "朝阳市人民政府", "name": "部门动态", "url": "https://www.chaoyang.gov.cn/cyszf/ywdt/bmdt/glist.html"},
    {"site": "丹东市人民政府", "name": "部门动态", "url": "https://www.dandong.gov.cn/ddszf/xw/bmdt/glist.html"},
    {"site": "铁岭市人民政府", "name": "部门动态", "url": "https://www.tieling.gov.cn/tieling/ywdt/bmdt/index.html"},
    {"site": "锦州市农业农村局", "name": "工作动态", "url": "https://nyncj.jz.gov.cn/gzdt.htm"},
    {"site": "锦州市商务局", "name": "商务动态", "url": "https://sswj.jz.gov.cn/swdt1.htm"},
    {"site": "锦州市政府", "name": "菜篮子信息发布平台", "url": "https://www.jz.gov.cn/ztzl/clzxxfbpt.htm"},
]

CURATED = [
    {"url": "https://www.dl.gov.cn/art/2026/5/9/art_1437_2511253.html", "city": "大连",
     "date": "2026-05-09", "tag": "大连-五一假期供应", "quality": "A",
     "org": "大连市人民政府"},
    {"url": "https://zfxxgk.dl.gov.cn/art/2026/2/13/art_1190_2500005.html", "city": "大连",
     "date": "2026-02-13", "tag": "大连-春节保供", "quality": "A",
     "org": "大连市人民政府"},
    {"url": "https://boc.dl.gov.cn/art/2025/9/29/art_1932_2464952.html", "city": "大连",
     "date": "2025-09-29", "tag": "大连-双节市场供应", "quality": "A",
     "org": "大连市商务局"},
    {"url": "http://newpaper.cynews.com.cn/cyrm/epaper/content/202603/19/c87327.html",
     "city": "朝阳", "date": "2026-03-19", "tag": "朝阳日报-五间房镇番茄", "quality": "B",
     "org": "朝阳日报"},
]

MARKET_PAT = re.compile(
    r"(双兴商品城批发市场|双兴商品城|南关岭果菜批发市场|大连果菜批发市场|"
    r"大连现代农业产业中心农产品交易市场|金发地|三里桥|凌西农副产品物流园|"
    r"北镇窟窿台蔬菜批发市场|窟窿台|八里堡蔬菜批发市场|四官营子蔬菜批发市场|"
    r"范杖子特种蔬菜批发市场|五间房镇庄头蔬菜批发市场|庄头蔬菜批发市场|"
    r"朝阳果菜批发市场|铁岭县农产品批发市场|北票蔬菜批发市场|"
    r"双兴市场|南关岭市场|果菜批发市场|农产品批发市场|蔬菜批发市场)")

COUNTY_PAT = re.compile(
    r"(东港市|凤城市|宽甸县|凌源市|北票市|建平县|喀左县|昌图县|铁岭县|开原市|"
    r"调兵山市|西丰县|黑山县|北镇市|义县|凌海市|庄河市|瓦房店市|普兰店区|金州区|"
    r"旅顺口区|长海县|朝阳县|建昌县|龙城区|双塔区|振兴区|元宝区|振安区)")


def classify(sent: str, verb: str) -> tuple[str, str, str]:
    crop, unit = "蔬菜", "吨"
    if re.search(r"白条猪|生猪|猪肉", sent):
        crop, unit = "猪肉", ("头" if "头" in sent else "吨")
    elif re.search(r"鸡蛋|蛋", sent) and "蔬菜" not in sent:
        crop, unit = "鸡蛋", "吨"
    elif re.search(r"水果", sent) and "蔬菜" not in sent:
        crop = "水果"
    if "库存" in verb or "储备" in verb[:4]:
        return crop, unit, "stock"
    if re.search(r"交易量|成交量|销量|销售量|吞吐量", verb):
        return crop, unit, "turnover"
    return crop, unit, "inflow"


def scope_of(sent: str) -> str:
    if "全省" in sent or "省商务厅" in sent or "省农业农村厅" in sent:
        return "province"
    return "market"


def extract(text: str, src: dict) -> list[dict]:
    rows = []
    city = src.get("city", "")
    org = src.get("org", "")
    flat = re.sub(r"\s+", "", text or "")
    for sent in re.split(r"[。；;\n]", flat):
        if not re.search(VOL_WORDS, sent):
            continue
        for m in re.finditer(
                r"(日均|每日|当日|每天|今天|本周|周均|全年|累计|今年)?[^，,]{0,40}?"
                r"(" + VOL_WORDS + r")[^0-9]{0,12}?(\d+(?:\.\d+)?)\s*(" + UNIT_WORDS + r")", sent):
            verb, num, unit = m.group(2), float(m.group(3)), m.group(4)
            if unit in ("车次", "辆次") or num <= 0:
                continue
            markets = MARKET_PAT.findall(sent)
            market_name = "、".join(dict.fromkeys(markets)) if markets else ""
            scope = scope_of(sent)
            crop, unit_std, vtype = classify(sent, verb)
            if vtype == "stock":
                continue
            county_m = COUNTY_PAT.search(sent)
            rows.append({
                "date": src.get("date", ""),
                "city": "辽宁省" if scope == "province" else (city or ""),
                "county": county_m.group(1) if county_m else _county_fallback(market_name),
                "market_name": market_name,
                "crop": crop,
                "volume": num,
                "volume_unit": unit_std,
                "volume_type": vtype,
                "geo_level": scope,
                "source_id": "",
                "source_name": org,
                "source_url": src.get("url", ""),
                "raw_file": src.get("raw_file", ""),
                "quality_grade": src.get("quality", "B"),
                "note": f"原文片段：{sent[:140]}",
            })
    return dedup(rows)


def _county_fallback(market_name: str) -> str:
    for c in ("东港市", "凌源市", "北票市", "昌图县", "铁岭县", "宽甸县", "振安区", "黑山县"):
        if c in market_name:
            return c
    return ""


def dedup(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        key = (r["source_url"], r["market_name"], r["volume"], r["volume_type"], r["city"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def crawl_dalian_listing() -> list[dict]:
    items = []
    for col in ("1190", "1437", "1932"):
        try:
            items.extend(dl_gov_list(col, max_pages=40))
        except Exception as exc:
            print(f"  [ACCESS_RESTRICTED] 大连栏目 {col}: {exc}")
    return items


CIF_BLOCKS = [("24511242", "生活必需品动态"), ("24511241", "消费市场监测")]


def collect_dalian_cif() -> list[dict]:
    """大连商务预报（cif.mofcom.gov.cn）——含"日均蔬菜上市量 X 吨"的真实周报。"""
    import urllib.request
    from _events_util import get, save_raw, text_of
    rows, ev = [], []
    for blockid, name in CIF_BLOCKS:
        url = ("https://cif.mofcom.gov.cn/newsite/content/content/front/"
               f"listPage?blockid={blockid}")
        try:
            html = get(url)
        except Exception as exc:
            print(f"  [ACCESS_RESTRICTED] cif {name}: {exc}")
            ev.append({"site": "大连商务预报", "name": name, "url": url, "n_items": 0,
                       "n_hits": 0, "status": "ACCESS_RESTRICTED", "error": str(exc)[:120]})
            continue
        items = re.findall(
            r'<a[^>]*href="(/newsite/html/dalian/html/\d+/[^"]+\.html)"[^>]*>(.*?)</a>', html, re.S)
        dates = re.findall(r"(\d{4}-\d{2}-\d{2})\s*\d{2}:\d{2}:\d{2}", html)
        items = [(h, re.sub(r"<[^>]+>", "", t).strip()) for h, t in items]
        ev.append({"site": "大连商务预报", "name": name, "url": url, "n_items": len(items),
                   "n_hits": len(items), "status": "ok", "error": ""})
        print(f"  cif {name}: {len(items)} 条")
        for i, (href, title) in enumerate(items):
            full = "https://cif.mofcom.gov.cn" + href
            d = dates[i] if i < len(dates) else ""
            try:
                art = get(full, referer=url)
            except Exception as exc:
                print(f"  [ACCESS_RESTRICTED] {full}: {exc}")
                ev.append({"site": "大连商务预报", "name": name, "url": full, "n_items": 0,
                           "n_hits": 1, "status": "ACCESS_RESTRICTED", "error": str(exc)[:120]})
                continue
            rel = save_raw(art, TOPIC, full)
            body = text_of(art)
            got = extract(body, {"city": "大连", "date": d, "url": full,
                                 "org": "大连市商务局（商务预报）", "quality": "A",
                                 "raw_file": rel})
            if got:
                got[0]["market_name"] = "大连市内主要批发市场（合计）"
                print(f"    [ok] {title[:30]} -> {len(got)} 条")
            rows.extend(got)
    return rows, ev


def main() -> None:
    rows = run_curated(CURATED, TOPIC, extract)

    print("\n[栏目列表扫描]")
    evidence = []
    hits, allitems = [], []
    kw = TITLE_KW
    for col in COLUMNS:
        try:
            items = harvest_list(col["url"], max_pages=25)
        except Exception as exc:
            print(f"  [ACCESS_RESTRICTED] {col['url']}: {exc}")
            evidence.append({**col, "n_items": 0, "n_hits": 0, "status": "ACCESS_RESTRICTED",
                             "error": str(exc)})
            continue
        allitems.extend(items)
        col_hits = [i for i in items if kw.search(i["title"] or "")]
        for i in col_hits:
            i["site"] = col.get("site", "")
            i["column"] = col.get("name", "")
        hits.extend(col_hits)
        evidence.append({**col, "n_items": len(items), "n_hits": len(col_hits),
                         "status": "ok", "error": ""})
        print(f"  {col['name']}: {len(items)} 条 / 命中 {len(col_hits)}")

    print(f"\n[抓取命中文章] 共 {len(hits)} 条")
    fetched = 0
    for it in hits:
        try:
            text, rel = fetch_article(it["url"], TOPIC)
        except Exception as exc:
            print(f"  [ACCESS_RESTRICTED] {it['url']}: {exc}")
            evidence.append({"site": it.get("site", ""), "name": it.get("column", ""),
                             "url": it["url"], "n_items": 0, "n_hits": 1,
                             "status": "ACCESS_RESTRICTED", "error": str(exc)[:120]})
            continue
        fetched += 1
        base = re.search(r"/([^/]+)\.html$|/(\d{4})/", it["url"])
        city = _city_of(it.get("site", ""), it["url"])
        got = extract(text, {"city": city, "date": it.get("date", ""), "url": it["url"],
                             "org": it.get("site", ""), "quality": "B", "raw_file": rel})
        rows.extend(got)
        if got:
            print(f"  [ok] {it['title'][:34]} -> {len(got)} 条")
    rows = dedup(rows)

    # 大连政务网列表二次扫描（huilan 专用接口）
    print("\n[大连政务网 列表枚举]")
    listing = crawl_dalian_listing()
    dhits = [i for i in listing if kw.search(i["title"])]
    print(f"  列表 {len(listing)} 条，命中 {len(dhits)} 条")
    for it in dhits:
        try:
            text, rel = fetch_article(it["url"], TOPIC)
        except Exception as exc:
            print(f"  [ACCESS_RESTRICTED] {it['url']}: {exc}")
            continue
        got = extract(text, {"city": "大连", "date": it["date"], "url": it["url"],
                             "org": "大连市人民政府", "quality": "A", "raw_file": rel})
        rows.extend(got)
    rows = dedup(rows)

    # 大连商务预报（cif.mofcom.gov.cn）：含"日均蔬菜上市量 X 吨"
    print("\n[大连商务预报 cif.mofcom.gov.cn]")
    cif_rows, cif_ev = collect_dalian_cif()
    rows.extend(cif_rows)
    evidence.extend(cif_ev)
    rows = dedup(rows)

    FIVE = {"大连", "丹东", "铁岭", "锦州", "朝阳"}
    rows = [r for r in rows if r["geo_level"] == "province" or r["city"] in FIVE]

    fields = ["date", "city", "county", "market_name", "crop", "volume", "volume_unit",
              "volume_type", "geo_level", "source_id", "source_name", "source_url",
              "raw_file", "quality_grade", "note"]
    out = ROOT / "city_data/reference/staging" / "volume_observations.csv"
    write_csv(out, fields, rows)
    write_csv(ROOT / "data/raw" / TOPIC / "search_evidence.csv",
              ["site", "name", "url", "n_items", "n_hits", "status", "error"], evidence)
    print(f"\n[OK] volume_observations.csv -> {len(rows)} 条  ({now()})")
    print("  city:", dict(Counter(r["city"] for r in rows)))
    print("  geo_level:", dict(Counter(r["geo_level"] for r in rows)))
    print("  volume_type:", dict(Counter(r["volume_type"] for r in rows)))


def _city_of(site: str, url: str) -> str:
    for c in ("大连", "丹东", "铁岭", "锦州", "朝阳"):
        if c in site or c in url:
            return c
    return ""


if __name__ == "__main__":
    main()
