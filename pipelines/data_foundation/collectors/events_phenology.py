"""县域物候 / 农时事件（五城非价格数据，P0）采集。

只记录**官方公开文本中确有的**农时信息：春耕/春播/播种进度/水稻插秧/育秧/
生育期（拔节/抽穗/灌浆）/成熟/收获/秋收/开镰/农情/苗情/农业气象。
能落到区县名的一律记 county，并给 geo_level=county；否则 geo_level=city。

禁止编造物候：没有明确日期/进度的文章不入库，只保留搜索证据。

产出：city_data/reference/staging/phenology_events.csv
原始 HTML：data/raw/agronomy/
证据：data/raw/agronomy/search_evidence.csv
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _events_util import (ROOT, article_body, city_from_tag, fetch_article,  # noqa: E402
                          harvest_list, now, write_csv)

TOPIC = "agronomy"

TITLE_KW = re.compile(
    r"春耕|备耕|春播|播种|插秧|育秧|育苗|苗情|苗期|出苗|返青|农情|生育|拔节|抽穗|抽雄|"
    r"扬花|开花|灌浆|成熟|收获|秋收|开镰|收割|农时|农事|墒情|农业气象|旬报|农机|大田|"
    r"粮食作物|水稻|玉米|大豆|谷子|高粱|马铃薯")

COLUMNS = [
    {"site": "辽宁省农业农村厅", "name": "种植业管理", "url": "https://nync.ln.gov.cn/nync/index/ywgl/scgl/zzygl/index.shtml"},
    {"site": "辽宁省农业农村厅", "name": "通知公告", "url": "https://nync.ln.gov.cn/nync/index/tzgg/index.shtml"},
    {"site": "辽宁省农业农村厅", "name": "行业动态", "url": "https://nync.ln.gov.cn/nync/index/nyyw/nyxw/gzdt/index.shtml"},
    {"site": "辽宁省农业农村厅", "name": "中心动态", "url": "https://nync.ln.gov.cn/nync/index/lnsnyfzfwzx/zxdt/index.shtml"},
    {"site": "辽宁省农业农村厅", "name": "农业要闻", "url": "https://nync.ln.gov.cn/nync/index/nyyw/index.shtml"},
    {"site": "辽宁省农业农村厅", "name": "全省农业信息联播", "url": "https://nync.ln.gov.cn/nync/index/nyyw/zsqsnyxxlb/index.shtml", "max_pages": 60},
    {"site": "辽宁省农业农村厅", "name": "各市农业信息联播", "url": "https://nync.ln.gov.cn/nync/index/nyyw/zsqgnyxxlb/index.shtml", "max_pages": 60},
    {"site": "朝阳市人民政府", "name": "部门动态", "url": "https://www.chaoyang.gov.cn/cyszf/ywdt/bmdt/glist.html"},
    {"site": "朝阳市农业农村局", "name": "农业动态", "url": "https://nyncj.chaoyang.gov.cn/cysnyncj/nydt/glist.html"},
    {"site": "朝阳市农业农村局", "name": "本地新闻", "url": "https://nyncj.chaoyang.gov.cn/cysnyncj/nydt/bdxw/glist.html"},
    {"site": "丹东市人民政府", "name": "部门动态", "url": "https://www.dandong.gov.cn/ddszf/xw/bmdt/glist.html"},
    {"site": "铁岭市人民政府", "name": "部门动态", "url": "https://www.tieling.gov.cn/tieling/ywdt/bmdt/index.html"},
    {"site": "锦州市农业农村局", "name": "工作动态", "url": "https://nyncj.jz.gov.cn/gzdt.htm"},
    {"site": "辽宁省粮食和物资储备局", "name": "地市粮食动态", "url": "https://lcj.ln.gov.cn/lswzcb/xwdt/dslsdt/index.shtml"},
]

CITY_OF_COUNTY = {
    "东港市": "丹东", "凤城市": "丹东", "宽甸县": "丹东", "振兴区": "丹东", "元宝区": "丹东", "振安区": "丹东",
    "凌源市": "朝阳", "北票市": "朝阳", "建平县": "朝阳", "喀左县": "朝阳", "朝阳县": "朝阳",
    "龙城区": "朝阳", "双塔区": "朝阳", "建昌县": "朝阳",
    "昌图县": "铁岭", "铁岭县": "铁岭", "开原市": "铁岭", "调兵山市": "铁岭", "西丰县": "铁岭",
    "黑山县": "锦州", "北镇市": "锦州", "义县": "锦州", "凌海市": "锦州",
    "庄河市": "大连", "瓦房店市": "大连", "普兰店区": "大连", "金州区": "大连", "旅顺口区": "大连", "长海县": "大连",
}
CITY5 = ("大连", "丹东", "铁岭", "锦州", "朝阳")
CITY_PAT = re.compile(r"(沈阳|大连|鞍山|抚顺|本溪|丹东|锦州|营口|阜新|辽阳|盘锦|铁岭|朝阳|葫芦岛)")

# 纯技术指南/行政事务类，不构成县域农时事件
NEG_TITLE = re.compile(
    r"技术指南|技术规程|技术指引|保养|检修|使用与调整|手册|标准|操作规程|品种审定|联合体试验|"
    r"培训班|培训|演练|普法|鉴定|评价|演示|消费者权益|3\.15|3·15|执法|检查|调研|会议|"
    r"总结会|小分队|大比武|遴选|座谈|现场会|云课堂|法规|办法|预案|招标|公示|警示教育")
POS_TITLE = re.compile(r"进度|完成|面积|亩|%|已播|已收|开镰|插秧|育秧|播种|收获|春耕|春播|秋收|农情")
# 外省转载（标题形如 [山东]…）→ 剔除；但 [丹东]/[锦州] 等本省市级标签须保留
OTHER_PROV = re.compile(
    r"\[(?!辽宁|沈阳|大连|鞍山|抚顺|本溪|丹东|锦州|营口|阜新|辽阳|盘锦|铁岭|朝阳|葫芦岛)"
    r"[^\]]{2,4}\]")
LIAONING_HINT = re.compile(
    r"辽宁|辽北|辽西|辽南|辽东|沈阳|大连|鞍山|抚顺|本溪|丹东|锦州|营口|阜新|辽阳|盘锦|铁岭|朝阳|葫芦岛|"
    r"铁岭县|昌图|开原|调兵山|西丰|黑山|北镇|义县|凌海|凌源|北票|建平|喀左|朝阳县|"
    r"东港|凤城|宽甸|庄河|瓦房店|普兰店|金州|旅顺|长海")

STAGE_MAP = [
    ("harvest", r"收获|收割|开镰|秋收|采收|测产"),
    ("maturity", r"成熟期|成熟|完熟|腊熟|乳熟|黄熟"),
    ("grain_filling", r"灌浆|鼓粒"),
    ("flowering", r"抽穗|扬花|开花|授粉|吐丝"),
    ("jointing", r"拔节|分蘖|起身|苗期|出苗|苗情"),
    ("transplant", r"插秧|移栽|育秧|抛秧"),
    ("sowing", r"春播|播种|下种|开犁|机播|完成播种"),
    ("land_prep", r"春耕|备耕|整地|耙地|旋耕|秸秆还田"),
]

COUNTY_PAT = re.compile(
    r"(东港市|凤城市|宽甸县|凌源市|北票市|建平县|喀左县|朝阳县|昌图县|铁岭县|"
    r"开原市|调兵山市|西丰县|黑山县|北镇市|义县|凌海市|庄河市|瓦房店市|普兰店区|"
    r"金州区|旅顺口区|长海县|建昌县|龙城区|双塔区|振兴区|元宝区|振安区|"
    r"大石桥市|海城市|新民市|法库县|康平县|台安县|岫岩县|清原县|新宾县)")

CROP_PAT = re.compile(
    r"(水稻|玉米|大豆|花生|小麦|马铃薯|谷子|高粱|杂粮|红薯|地瓜|棉花|"
    r"设施蔬菜|蔬菜|水果|苹果|樱桃|草莓|葡萄|食用菌|中药材)")

PROGRESS_PAT = re.compile(r"(?:进度|完成|已播|已种|已收|已收割|完成率)[^。，,]{0,20}?(\d+(?:\.\d+)?)\s*%")
PROGRESS_PAT2 = re.compile(r"(\d+(?:\.\d+)?)\s*%[^。，,]{0,12}?(?:进度|完成|已播|已收)")
AREA_PAT = re.compile(r"(\d+(?:\.\d+)?)\s*(万亩|万公顷|公顷|亩|千公顷)")
DATE_PAT = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})?\s*日?")


def _stage_of(text: str) -> tuple[str, str]:
    earliest, res = 10 ** 9, ("", "")
    for name, pat in STAGE_MAP:
        m = re.search(pat, text)
        if m and m.start() < earliest:
            earliest, res = m.start(), (name, m.group(0))
    return res


def parse_row(text: str, src: dict) -> dict | None:
    flat = re.sub(r"\s+", "", article_body(text))
    title = src.get("title", "")
    if OTHER_PROV.search(title):
        return None
    if NEG_TITLE.search(title) and not POS_TITLE.search(title):
        return None
    if not (LIAONING_HINT.search(title) or LIAONING_HINT.search(flat[:600])):
        return None
    stage, stage_detail = _stage_of(title)
    if not stage:
        stage, stage_detail = _stage_of(flat)
    if not stage:
        return None
    dm = DATE_PAT.search(flat)
    date = src.get("date", "")
    if not date and dm:
        date = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3) or 1):02d}"
    if not date:
        return None
    crop_m = CROP_PAT.search(title) or CROP_PAT.search(flat)
    prog = PROGRESS_PAT.search(flat) or PROGRESS_PAT2.search(flat)
    area = AREA_PAT.search(flat)
    county_m = COUNTY_PAT.search(flat)
    city = city_from_tag(title)
    if not city and county_m:
        city = CITY_OF_COUNTY.get(county_m.group(1), "")
    if not city:
        cm = CITY_PAT.search(src.get("site", "") or "")
        city = cm.group(1) if cm else ""
    if not city:
        cm = CITY_PAT.search(title) or CITY_PAT.search(flat)
        city = cm.group(1) if cm else ""
    # 必须有明确的农时动作信号，避免纯叙述/综述
    if not (prog or area or re.search(r"完成|进入|开始|过半|全面|陆续|展开|启动|结束|进入|持续推进", flat[:400])):
        return None
    # 仅保留目标五城（大连/丹东/铁岭/锦州/朝阳）的县域/市级农时
    if city not in CITY5:
        return None
    return {
        "date": date,
        "year": date[:4],
        "city": city,
        "county": county_m.group(1) if county_m else src.get("county", ""),
        "geo_level": "county" if county_m else "city",
        "crop": crop_m.group(1) if crop_m else "",
        "stage": stage,
        "stage_detail": stage_detail,
        "progress_pct": prog.group(1) if prog else "",
        "area_value": area.group(1) if area else "",
        "area_unit": area.group(2) if area else "",
        "source_name": src.get("org", ""),
        "source_url": src.get("url", ""),
        "raw_file": src.get("raw_file", ""),
        "quality_grade": src.get("quality", "B"),
        "note": f"原文片段：{flat[:160]}",
    }


def _city_of(site: str, url: str) -> str:
    for c in ("大连", "丹东", "铁岭", "锦州", "朝阳"):
        if c in site or c in url:
            return c
    return ""


def main() -> None:
    evidence, rows = [], []
    seen_urls = set()
    for col in COLUMNS:
        print(f"[列表] {col['name']} {col['url']}")
        try:
            items = harvest_list(col["url"], max_pages=col.get("max_pages", 25))
        except Exception as exc:
            print(f"  [ACCESS_RESTRICTED] {exc}")
            evidence.append({**col, "n_items": 0, "n_hits": 0, "status": "ACCESS_RESTRICTED",
                             "error": str(exc)[:120]})
            continue
        hits = [i for i in items if TITLE_KW.search(i["title"] or "")]
        for i in hits:
            i["site"] = col.get("site", "")
            i["column"] = col.get("name", "")
        evidence.append({**col, "n_items": len(items), "n_hits": len(hits), "status": "ok",
                         "error": ""})
        print(f"  -> {len(items)} 条 / 命中 {len(hits)}")
        for it in hits:
            if it["url"] in seen_urls:
                continue
            seen_urls.add(it["url"])
            try:
                text, rel = fetch_article(it["url"], TOPIC)
            except Exception as exc:
                print(f"  [ACCESS_RESTRICTED] {it['url']}: {exc}")
                evidence.append({"site": it.get("site", ""), "name": it.get("column", ""),
                                 "url": it["url"], "n_items": 0, "n_hits": 1,
                                 "status": "ACCESS_RESTRICTED", "error": str(exc)[:120]})
                continue
            row = parse_row(text, {"city": _city_of(it.get("site", ""), it["url"]),
                                   "date": it.get("date", ""), "url": it["url"],
                                   "org": it.get("site", ""), "site": it.get("site", ""),
                                   "quality": "B", "title": it["title"],
                                   "raw_file": rel})
            if row:
                row["title"] = it["title"]
                rows.append(row)
                print(f"  [ok] {it['title'][:32]} -> {row['stage']}")

    # 去重
    seen, uniq = set(), []
    for r in rows:
        k = (r["source_url"], r["date"], r["stage"], r["county"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    for i, r in enumerate(uniq, 1):
        r["event_id"] = f"PHEN-{i:05d}"

    fields = ["event_id", "date", "year", "city", "county", "geo_level", "crop", "stage",
              "stage_detail", "progress_pct", "area_value", "area_unit", "title",
              "source_name", "source_url", "raw_file", "quality_grade", "note"]
    out = ROOT / "city_data/reference/staging" / "phenology_events.csv"
    write_csv(out, fields, uniq)
    write_csv(ROOT / "data/raw" / TOPIC / "search_evidence.csv",
              ["site", "name", "url", "n_items", "n_hits", "status", "error"], evidence)
    print(f"\n[OK] phenology_events.csv -> {len(uniq)} 条  ({now()})")
    print("  city:", dict(Counter(r["city"] for r in uniq)))
    print("  geo_level:", dict(Counter(r["geo_level"] for r in uniq)))
    print("  year:", dict(Counter(r["year"] for r in uniq)))


if __name__ == "__main__":
    main()
