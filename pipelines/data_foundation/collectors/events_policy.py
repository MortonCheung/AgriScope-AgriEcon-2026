"""政策事件（五城非价格数据，P0）采集。

覆盖：保供稳价 / 菜篮子 / 价格补贴 / 应急调运 / 储备投放 / 平价菜 / 绿色通道。

产出：city_data/reference/marts/fact_policy_event.csv
原始 HTML：data/raw/policies/
证据：data/raw/policies/search_evidence.csv
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _events_util import (ROOT, article_body, city_from_tag, dl_gov_list,  # noqa: E402
                          fetch_article, harvest_list, now, write_csv)

TOPIC = "policy"

TITLE_KW = re.compile(
    r"保供|稳价|菜篮子|价格补贴|临时补贴|应急调运|调运|储备|投放|平价菜|平价|"
    r"绿色通道|市场供应|保障供应|货源|生活必需品|粮油|肉菜|蔬菜|春节|节日|"
    r"价格监测|价格调控|应急预案|供应保障|救灾资金|农业保险|保险|理赔")

COLUMNS = [
    {"site": "辽宁省发展和改革委员会", "name": "政策", "url": "https://fgw.ln.gov.cn/fgw/zc/index.shtml"},
    {"site": "辽宁省发展和改革委员会", "name": "通知公告", "url": "https://fgw.ln.gov.cn/fgw/index/tzgg/index.shtml"},
    {"site": "辽宁省商务厅", "name": "商务动态", "url": "https://swt.ln.gov.cn/swt/swdt/index.shtml"},
    {"site": "辽宁省商务厅", "name": "通知公告", "url": "https://swt.ln.gov.cn/swt/tzgg/index.shtml"},
    {"site": "辽宁省商务厅", "name": "政策文件", "url": "https://swt.ln.gov.cn/swt/zwgk/zcyjd/zcwj5/index.shtml"},
    {"site": "辽宁省粮食和物资储备局", "name": "省局动态", "url": "https://lcj.ln.gov.cn/lswzcb/xwdt/sjdt/index.shtml"},
    {"site": "辽宁省粮食和物资储备局", "name": "通知公告", "url": "https://lcj.ln.gov.cn/lswzcb/xwdt39/zhyw/index.shtml"},
    {"site": "辽宁省农业农村厅", "name": "通知公告", "url": "https://nync.ln.gov.cn/nync/index/tzgg/index.shtml"},
    {"site": "辽宁省农业农村厅", "name": "全省农业信息联播", "url": "https://nync.ln.gov.cn/nync/index/nyyw/zsqsnyxxlb/index.shtml", "max_pages": 60},
    {"site": "辽宁省农业农村厅", "name": "各市农业信息联播", "url": "https://nync.ln.gov.cn/nync/index/nyyw/zsqgnyxxlb/index.shtml", "max_pages": 60},
    {"site": "锦州市商务局", "name": "商务动态", "url": "https://sswj.jz.gov.cn/swdt1.htm"},
    {"site": "锦州市商务局", "name": "政策法规", "url": "https://sswj.jz.gov.cn/zcfg.htm"},
    {"site": "锦州市农业农村局", "name": "通知公告", "url": "https://nyncj.jz.gov.cn/tzgg.htm"},
    {"site": "锦州市政府", "name": "菜篮子信息发布平台", "url": "https://www.jz.gov.cn/ztzl/clzxxfbpt.htm"},
    {"site": "朝阳市人民政府", "name": "部门动态", "url": "https://www.chaoyang.gov.cn/cyszf/ywdt/bmdt/glist.html"},
    {"site": "朝阳市农业农村局", "name": "农业动态", "url": "https://nyncj.chaoyang.gov.cn/cysnyncj/nydt/glist.html"},
    {"site": "朝阳市农业农村局", "name": "本地新闻", "url": "https://nyncj.chaoyang.gov.cn/cysnyncj/nydt/bdxw/glist.html"},
    {"site": "丹东市人民政府", "name": "部门动态", "url": "https://www.dandong.gov.cn/ddszf/xw/bmdt/glist.html"},
    {"site": "铁岭市人民政府", "name": "部门动态", "url": "https://www.tieling.gov.cn/tieling/ywdt/bmdt/index.html"},
]

TYPE_MAP = [
    ("agriculture_insurance", r"农业保险|政策性.{0,6}保险|种植业.{0,6}保险|养殖.{0,4}保险|设施农业.{0,4}保险|农险|理赔"),
    ("disaster_relief", r"救灾资金|救灾|救济|灾后恢复"),
    ("price_subsidy", r"价格补贴|临时补贴|价格临时补贴|补贴"),
    ("reserve_release", r"储备投放|投放储备|储备肉|储备菜|冻猪肉|储备粮投放|投放中央|投放市场|轮换投放"),
    ("emergency_transport", r"应急调运|调运|绿色通道|运输保障|运力保障|调拨"),
    ("price_stabilization", r"保供稳价|稳价|稳定价格|平价菜|平价销售|平价|限价|价格调控"),
    ("vegetable_basket", r"菜篮子"),
    ("market_supply", r"市场供应|保障供应|保供|货源|生活必需品"),
]

# 机构名中的"储备"/"物资"等词会污染分类 → 先剔除
ORG_NOISE = re.compile(r"粮食和物资储备局|粮食和储备局|物资储备局|发展和改革委员会|发展改革委")
# 政策事件必须命中下述核心词之一
CORE_KW = re.compile(
    r"保供|稳价|菜篮|价格补贴|临时补贴|应急调运|调运|储备投放|投放储备|储备肉|储备菜|"
    r"冻猪肉|平价菜|平价销售|平价|绿色通道|市场供应|保障供应|生活必需品|货源|限价|价格调控|"
    r"救灾资金|农业保险|农险|理赔|救济")

CITY_PAT = re.compile(r"(沈阳|大连|鞍山|抚顺|本溪|丹东|锦州|营口|阜新|辽阳|盘锦|铁岭|朝阳|葫芦岛)")
COUNTY_PAT = re.compile(r"(东港市|凤城市|宽甸县|凌源市|北票市|建平县|朝阳县|昌图县|铁岭县|"
                        r"开原市|黑山县|北镇市|义县|凌海市|庄河市|瓦房店市|普兰店区)")
DATE_PAT = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")


def classify(text: str) -> str:
    for name, pat in TYPE_MAP:
        if re.search(pat, text):
            return name
    return ""


def parse_policy(text: str, src: dict) -> dict | None:
    flat = re.sub(r"\s+", "", article_body(text))
    title = src.get("title", "")
    clean_title = ORG_NOISE.sub("", title)
    clean_head = ORG_NOISE.sub("", flat[:400])
    if not (CORE_KW.search(clean_title) or CORE_KW.search(clean_head)):
        return None
    ptype = classify(clean_title) or classify(clean_head)
    if not ptype:
        return None
    date = src.get("date", "")
    if not date:
        dm = DATE_PAT.search(flat[:600])
        if dm:
            date = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"
    if not date:
        return None
    tag_city = city_from_tag(title)
    if tag_city:
        # 省级机关栏目转载的市级新闻（标题形如 [丹东]…）→ 记城市级，不复制成省级
        level, city = "city", tag_city
    else:
        level = "province" if src.get("site", "").startswith("辽宁省") else "city"
        city = ""
        if level == "city":
            cm = CITY_PAT.search(src.get("site", "") or "") or CITY_PAT.search(title)
            city = cm.group(1) if cm else ""
    county_m = COUNTY_PAT.search(flat[:400])
    return {
        "policy_date": date,
        "year": date[:4],
        "policy_type": ptype,
        "level": level,
        "city": city,
        "county": county_m.group(1) if county_m else "",
        "issuing_org": src.get("org", ""),
        "title": title,
        "summary": flat[:220],
        "source_name": src.get("org", ""),
        "source_url": src.get("url", ""),
        "raw_file": src.get("raw_file", ""),
        "quality_grade": src.get("quality", "A"),
    }


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
            p = parse_policy(text, {"date": it.get("date", ""), "url": it["url"],
                                    "org": it.get("site", ""), "quality": "A",
                                    "raw_file": rel, "title": it["title"],
                                    "site": it.get("site", "")})
            if p:
                rows.append(p)
                print(f"  [ok] {it['title'][:30]} -> {p['policy_type']}")

    # 大连政务网
    print("\n[大连政务网 列表枚举]")
    try:
        dlist = dl_gov_list("1190") + dl_gov_list("1932")
    except Exception as exc:
        dlist = []
        print(f"  [ACCESS_RESTRICTED] {exc}")
    for it in [i for i in dlist if TITLE_KW.search(i["title"])]:
        if it["url"] in seen_urls:
            continue
        seen_urls.add(it["url"])
        try:
            text, rel = fetch_article(it["url"], TOPIC)
        except Exception as exc:
            continue
        p = parse_policy(text, {"date": it["date"], "url": it["url"], "org": "大连市人民政府",
                                "quality": "A", "raw_file": rel, "title": it["title"],
                                "site": "大连市人民政府"})
        if p:
            rows.append(p)

    seen, uniq = set(), []
    for r in rows:
        k = (r["source_url"], r["policy_type"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    FIVE = {"大连", "丹东", "铁岭", "锦州", "朝阳"}
    uniq = [r for r in uniq if r["level"] == "province" or r["city"] in FIVE]
    for i, r in enumerate(uniq, 1):
        r["event_id"] = f"POL-{i:05d}"

    fields = ["event_id", "policy_date", "year", "policy_type", "level", "city", "county",
              "issuing_org", "title", "summary", "source_name", "source_url", "raw_file",
              "quality_grade"]
    out = ROOT / "city_data/reference/marts" / "fact_policy_event.csv"
    write_csv(out, fields, uniq)
    write_csv(ROOT / "data/raw" / TOPIC / "search_evidence.csv",
              ["site", "name", "url", "n_items", "n_hits", "status", "error"], evidence)
    print(f"\n[OK] fact_policy_event.csv -> {len(uniq)} 条  ({now()})")
    print("  policy_type:", dict(Counter(r["policy_type"] for r in uniq)))
    print("  level:", dict(Counter(r["level"] for r in uniq)))
    print("  city:", dict(Counter(r["city"] for r in uniq)))


if __name__ == "__main__":
    main()
