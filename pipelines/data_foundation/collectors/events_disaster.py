"""官方真实农业灾害事件（五城非价格数据，P0）采集。

与 derived_weather_events（气象阈值算法事件）**严格分开**：本表只放官方通报的真实灾情。
硬红线：原文写「全省/我省 XX 万亩」→ spatial_level=province、city 留空，
**绝不把省级灾损分摊到市**；只有原文明确指向某市/某县时才填 city/county。

产出：city_data/reference/marts/fact_disaster_event_observed.csv
原始 HTML：data/raw/disaster/
证据：data/raw/disaster/search_evidence.csv
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _events_util import (ROOT, article_body, city_from_tag, fetch_article,  # noqa: E402
                          harvest_list, now, write_csv)

TOPIC = "disaster"

TITLE_KW = re.compile(
    r"暴雨|洪涝|洪水|汛情|台风|干旱|旱情|冰雹|大风|寒潮|低温|霜冻|冻害|雪灾|内涝|"
    r"受灾|成灾|绝收|灾情|抗灾|减灾|救灾|排涝|防汛|抢险|农田积水|农作物受灾|"
    r"强降雨|强对流|灾害|倒伏|减产|大棚受灾|设施受损|防灾减灾")

COLUMNS = [
    {"site": "辽宁省水利厅", "name": "汛情快报", "url": "https://slt.ln.gov.cn/slt/xwzx/fxdt/xqkb/index.shtml"},
    {"site": "辽宁省水利厅", "name": "防汛动态", "url": "https://slt.ln.gov.cn/slt/xwzx/fxdt/index.shtml"},
    {"site": "辽宁省水利厅", "name": "监测预警", "url": "https://slt.ln.gov.cn/slt/xwzx/fxdt/jcyj/index.shtml"},
    {"site": "辽宁省农业农村厅", "name": "通知公告", "url": "https://nync.ln.gov.cn/nync/index/tzgg/index.shtml"},
    {"site": "辽宁省农业农村厅", "name": "种植业管理", "url": "https://nync.ln.gov.cn/nync/index/ywgl/scgl/zzygl/index.shtml"},
    {"site": "辽宁省农业农村厅", "name": "行业动态", "url": "https://nync.ln.gov.cn/nync/index/nyyw/nyxw/gzdt/index.shtml"},
    {"site": "辽宁省农业农村厅", "name": "全省农业信息联播", "url": "https://nync.ln.gov.cn/nync/index/nyyw/zsqsnyxxlb/index.shtml", "max_pages": 60},
    {"site": "辽宁省农业农村厅", "name": "各市农业信息联播", "url": "https://nync.ln.gov.cn/nync/index/nyyw/zsqgnyxxlb/index.shtml", "max_pages": 60},
    {"site": "辽宁省应急管理厅", "name": "应急管理要闻", "url": "https://yjgl.ln.gov.cn/yjglyw/index.shtml"},
    {"site": "辽宁省应急管理厅", "name": "工作动态", "url": "https://yjgl.ln.gov.cn/gzdt/index.shtml"},
    {"site": "朝阳市人民政府", "name": "部门动态", "url": "https://www.chaoyang.gov.cn/cyszf/ywdt/bmdt/glist.html"},
    {"site": "朝阳市农业农村局", "name": "农业动态", "url": "https://nyncj.chaoyang.gov.cn/cysnyncj/nydt/glist.html"},
    {"site": "丹东市人民政府", "name": "部门动态", "url": "https://www.dandong.gov.cn/ddszf/xw/bmdt/glist.html"},
    {"site": "铁岭市人民政府", "name": "部门动态", "url": "https://www.tieling.gov.cn/tieling/ywdt/bmdt/index.html"},
    {"site": "锦州市应急管理局", "name": "应急动态", "url": "https://yjj.jz.gov.cn/gzdt.htm"},
    {"site": "锦州市农业农村局", "name": "工作动态", "url": "https://nyncj.jz.gov.cn/gzdt.htm"},
    {"site": "建平县人民政府", "name": "灾情核定信息", "url": "https://lnjp.gov.cn/jpxzf/26gly/jzly/zhjz/zqhdxx/glist.html"},
    {"site": "北票市人民政府", "name": "灾情核定信息", "url": "https://www.bp.gov.cn/bpszf/26gly/jzly/zhjz/zqhdxx/glist.html"},
]

CITY_PAT = re.compile(r"(沈阳|大连|鞍山|抚顺|本溪|丹东|锦州|营口|阜新|辽阳|盘锦|铁岭|朝阳|葫芦岛)")
COUNTY_PAT = re.compile(
    r"(东港市|凤城市|宽甸县|凌源市|北票市|建平县|喀左县|朝阳县|昌图县|铁岭县|"
    r"开原市|调兵山市|西丰县|黑山县|北镇市|义县|凌海市|庄河市|瓦房店市|普兰店区|"
    r"金州区|旅顺口区|长海县|建昌县|龙城区|双塔区|振兴区|元宝区|振安区|"
    r"大石桥市|海城市|新民市|法库县|康平县|台安县|岫岩县|沈北新区)")
CROP_PAT = re.compile(r"(水稻|玉米|大豆|花生|小麦|马铃薯|谷子|高粱|蔬菜|水果|设施农业|"
                      r"温室大棚|畜禽|生猪|肉牛|家禽|水产)")

CITY_OF_COUNTY = {
    "东港市": "丹东", "凤城市": "丹东", "宽甸县": "丹东", "振兴区": "丹东", "元宝区": "丹东", "振安区": "丹东",
    "凌源市": "朝阳", "北票市": "朝阳", "建平县": "朝阳", "喀左县": "朝阳", "朝阳县": "朝阳",
    "龙城区": "朝阳", "双塔区": "朝阳", "建昌县": "葫芦岛",
    "昌图县": "铁岭", "铁岭县": "铁岭", "开原市": "铁岭", "调兵山市": "铁岭", "西丰县": "铁岭",
    "黑山县": "锦州", "北镇市": "锦州", "义县": "锦州", "凌海市": "锦州",
    "庄河市": "大连", "瓦房店市": "大连", "普兰店区": "大连", "金州区": "大连", "旅顺口区": "大连", "长海县": "大连",
    "新民市": "沈阳", "法库县": "沈阳", "康平县": "沈阳", "沈北新区": "沈阳",
    "大石桥市": "营口", "海城市": "鞍山", "台安县": "鞍山", "岫岩县": "鞍山",
}


def _crop_of(text: str) -> str:
    hits = list(dict.fromkeys(CROP_PAT.findall(text)))
    return "、".join(hits[:4])

TYPE_MAP = [
    ("typhoon", r"台风"),
    ("rainstorm_flood", r"暴雨|洪涝|洪水|内涝|汛情|防汛|防洪|抢险|救灾|强降雨|强降水|农田积水|渍涝|淹水|受淹|水淹"),
    ("drought", r"干旱|旱情|抗旱"),
    ("hail", r"冰雹|风雹"),
    ("cold_frost", r"低温|霜冻|寒潮|冷害|冷冻|大雪|暴雪"),
    ("lodging", r"倒伏"),
    ("pest_disease", r"病虫害|病害|虫害"),
    ("snow", r"雪灾"),
]

# 演练/培训/会议/预案类属"准备工作"，不是已发生的灾害事件 → 除非含明确灾情
NEG_KW = re.compile(r"演练|培训|座谈|部署会|视频会|工作会议|预案|印发|实施方案|检查|调研|"
                    r"总结会|调度会议|通知|提示|技术手册|指南|救助|冬春|款物|慰问|"
                    r"备荒|种子储备|储备任务|推荐|公示|遴选|招标|流程|图上|示意图|"
                    r"备汛|安排部署|防御工作|物资保障|工作落实")
OBS_KW = re.compile(r"受灾|成灾|绝收|灾情|洪涝|汛情|洪水|内涝|预警|转移|排涝|积水|倒塌|因灾|抢险|救灾|溃口|决口|灾损|倒伏|大棚受灾|受淹")
# 无论是否含"灾情"字样，一律不视为已发生灾害事件（流程图/制度/预案/演练等）
HARD_NEG = re.compile(r"工作流程|流程图|示意图|上报工作|管理制度|实施办法|应急预案|预案|演练|桌面推演")

AREA_RE = re.compile(r"(?:农作物)?受灾(?:面积)?(?:共计|合计|约|达|为|共)?(\d+(?:\.\d+)?)\s*(万亩|万公顷|千公顷|公顷|亩)")
DAMAGE_RE = re.compile(r"成灾(?:面积)?(?:共计|合计|约|达|为|共)?(\d+(?:\.\d+)?)\s*(万亩|万公顷|千公顷|公顷|亩)")
FAIL_RE = re.compile(r"绝收(?:面积)?(?:共计|合计|约|达|为|共)?(\d+(?:\.\d+)?)\s*(万亩|万公顷|千公顷|公顷|亩)")
FAIL_RE2 = re.compile(r"(\d+(?:\.\d+)?)\s*(万亩|万公顷|千公顷|公顷|亩)(?:的)?(?:农作物)?绝收")
DRAIN_RE = re.compile(r"排(?:空|除)?(?:农田)?(?:积水|涝水)(?:约|达|为|共)?(\d+(?:\.\d+)?)\s*(万亩|亩|万立方米|立方米)")
EVAC_RE = re.compile(r"转移(?:群众|人口|人员|安置|避险)?(?:约|达|为|共)?(\d+(?:\.\d+)?)\s*(万)?人")
ECON_RE = re.compile(r"直接经济损失(?:约|达|为|共|合计|共计)?(?:约)?(\d+(?:\.\d+)?)\s*(万元|亿元)")


def _scope(sent: str) -> tuple[str, str, str]:
    """返回 (spatial_level, city, county)。省级口径优先，绝不把省级灾损摊到单一市。

    关键：若灾情句同时点名多个市县（省级通报常见），只能记为 province。
    """
    if re.search(r"全省|我省|辽宁全省", sent):
        return "province", "", ""
    counties = list(dict.fromkeys(COUNTY_PAT.findall(sent)))
    cities = list(dict.fromkeys(CITY_PAT.findall(sent)))
    if len(counties) >= 2 or len(cities) >= 2:
        return "province", "", ""
    if len(counties) == 1:
        city = CITY_OF_COUNTY.get(counties[0], "")
        return "county", city or (cities[0] if cities else ""), counties[0]
    if len(cities) == 1:
        return "city", cities[0], ""
    return "unknown", "", ""


def _first(rx: re.Pattern, text: str) -> tuple[str, str]:
    m = rx.search(text)
    if not m:
        return "", ""
    return m.group(1), (m.group(2) if m.lastindex and m.lastindex >= 2 else "")


def classify_type(title: str, text: str) -> str:
    for name, pat in TYPE_MAP:
        if re.search(pat, title or ""):
            return name
    for name, pat in TYPE_MAP:
        if re.search(pat, text or ""):
            return name
    return ""


def parse_event(text: str, src: dict) -> dict | None:
    flat = re.sub(r"\s+", "", article_body(text))
    title = src.get("title", "")
    if HARD_NEG.search(title):
        return None
    if NEG_KW.search(title) and not re.search(r"受灾|灾情|成灾|绝收|洪涝|汛情|转移", title):
        return None
    if not OBS_KW.search(title) and not OBS_KW.search(flat[:1500]):
        return None
    etype = classify_type(title, flat)
    if not etype:
        return None
    date = src.get("date", "")
    if not date:
        return None
    # 受灾面积句所在范围
    scope_sent = ""
    for sent in re.split(r"[。；;\n]", flat):
        if re.search(r"受灾|成灾|绝收|排.{0,3}积水|转移", sent):
            scope_sent = sent
            break
    level, city, county = _scope(scope_sent or flat)
    tag_city = city_from_tag(title)
    if tag_city and level != "province":
        # 省级机关栏目转载的市级农业新闻（标题形如 [丹东]…）→ 记到市，绝不摊到省
        level = "county" if county else "city"
        city = city or tag_city
    if level == "unknown" and not city:
        # 县级政府「灾情核定信息」等：正文未点名，但发布主体即受灾县域
        site = (src.get("site", "") or "") + (src.get("org", "") or "")
        sm = COUNTY_PAT.search(site)
        if sm and "辽宁省" not in site[:6]:
            level, county = "county", sm.group(1)
            city = CITY_OF_COUNTY.get(sm.group(1), "")
        else:
            cm2 = CITY_PAT.search(site)
            if cm2:
                level, city = "city", cm2.group(1)
    if level == "unknown" and "辽宁省" in (src.get("org", "") or ""):
        # 省级机关的"通报/汛情"未点名市县时，属省级口径
        level = "province"
    aff_v, aff_u = _first(AREA_RE, flat)
    dmg_v, _ = _first(DAMAGE_RE, flat)
    fail_v, _ = _first(FAIL_RE, flat)
    if not fail_v:
        fail_v, _ = _first(FAIL_RE2, flat)
    drain_v, drain_u = _first(DRAIN_RE, flat)
    evac = EVAC_RE.search(flat)
    econ = ECON_RE.search(flat)
    return {
        "event_type": etype,
        "start_date": date,
        "end_date": date,
        "year": date[:4],
        "province": "辽宁省",
        "city": city if level in ("city", "county") else "",
        "county": county,
        "spatial_level": level,
        "affected_area_value": aff_v,
        "affected_area_unit": aff_u,
        "damaged_area_value": dmg_v,
        "crop_failure_area_value": fail_v,
        "drainage_area_value": drain_v,
        "drainage_area_unit": drain_u,
        "evacuated_persons": (evac.group(1) + "0000" if evac and evac.group(2) else (evac.group(1) if evac else "")),
        "deaths": "",
        "economic_loss": (f"{econ.group(1)}{econ.group(2)}" if econ else ""),
        "crop": _crop_of(flat),
        "official_description": flat[:500],
        "source_name": src.get("org", ""),
        "source_url": src.get("url", ""),
        "raw_file": src.get("raw_file", ""),
        "quality_grade": src.get("quality", "A"),
        "data_type": "official_reported",
        "title": src.get("title", ""),
    }


CURATED = [
    {"event_name": "2026年7月中旬辽宁持续强降雨洪涝灾害",
     "event_type": "rainstorm_flood", "start_date": "2026-07-13", "end_date": "2026-07-17",
     "spatial_level": "province", "city": "", "county": "",
     "affected_area_value": "290", "affected_area_unit": "万亩",
     "drainage_area_value": "53.27", "drainage_area_unit": "万亩",
     "evacuated_persons": "432089", "crop": "玉米、水稻",
     "official_description": ("省农业农村厅统计，截至2026-07-15，本轮持续降雨全省农作物受影响面积约290万亩；"
                              "全省已完成沟渠疏浚2035千米，排空农田积水53.27万亩；截至7月17日6时全省转移432089人"
                              "（沈阳81360、抚顺269437、辽阳20957、铁岭18077）。省级口径，未分摊到市。"),
     "title": "我省农业领域积极开展抗灾减损",
     "source_name": "辽宁省人民政府 / 农业农村部信息网 / 人民网辽宁",
     "source_url": "https://www.ln.gov.cn/web/ywdt/jrln/tpxw/2026071709015153267/index.shtml",
     "raw_file": "data/raw/disaster/official_2026/official_agricultural_disaster_events.json",
     "quality_grade": "A"},
]


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
            ev = parse_event(text, {"date": it.get("date", ""), "url": it["url"],
                                    "org": it.get("site", ""), "site": it.get("site", ""),
                                    "quality": "A", "raw_file": rel, "title": it["title"]})
            if ev:
                ev["event_name"] = it["title"]
                rows.append(ev)
                print(f"  [ok] {it['title'][:30]} -> {ev['event_type']}/{ev['spatial_level']}")

    seen, uniq = set(), []
    for r in rows + CURATED:
        k = (r.get("source_url", ""), r["event_type"], r["spatial_level"], r["city"], r["county"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    FIVE = {"大连", "丹东", "铁岭", "锦州", "朝阳"}
    uniq = [r for r in uniq if r["spatial_level"] == "province" or r["city"] in FIVE]
    for i, r in enumerate(uniq, 1):
        r["event_id"] = f"DIS-{i:05d}"
        r.setdefault("title", r.get("event_name", ""))
        r.setdefault("crop", "")
        r.setdefault("data_type", "official_reported")
    ts = datetime.now().isoformat(timespec="seconds")
    for r in uniq:
        r["fetched_at"] = ts
        r["year"] = (r["start_date"] or "")[:4]

    fields = ["event_id", "event_name", "event_type", "start_date", "end_date", "year",
              "province", "city", "county", "spatial_level", "affected_area_value",
              "affected_area_unit", "damaged_area_value", "crop_failure_area_value",
              "drainage_area_value", "drainage_area_unit", "evacuated_persons", "deaths",
              "economic_loss", "crop", "title", "official_description", "source_name",
              "source_url", "raw_file", "quality_grade", "data_type", "fetched_at"]
    out = ROOT / "city_data/reference/marts" / "fact_disaster_event_observed.csv"
    write_csv(out, fields, uniq)
    write_csv(ROOT / "data/raw" / TOPIC / "search_evidence.csv",
              ["site", "name", "url", "n_items", "n_hits", "status", "error"], evidence)
    print(f"\n[OK] fact_disaster_event_observed.csv -> {len(uniq)} 条  ({now()})")
    print("  spatial_level:", dict(Counter(r["spatial_level"] for r in uniq)))
    print("  event_type:", dict(Counter(r["event_type"] for r in uniq)))
    print("  city:", dict(Counter(r["city"] for r in uniq)))


if __name__ == "__main__":
    main()
