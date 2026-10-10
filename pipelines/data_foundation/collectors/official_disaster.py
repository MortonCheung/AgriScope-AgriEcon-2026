"""官方真实农业灾情事件采集（P0-4）。

与 derived_weather_events（算法阈值事件）严格分开，本表只放**官方通报的真实灾情**。

来源（均为政府/官方媒体转载政府信息）：
  辽宁省政府        https://www.ln.gov.cn/web/ywdt/jrln/tpxw/2026071709015153267/index.shtml
  农业农村部信息网  https://www.agri.cn/zx/xxlb/ln/202607/t20260716_8854266.htm
  人民网辽宁        https://ln.people.com.cn/n2/2026/0717/c378320-41642085.html

关键原则（手册§56）：原文写「全省290万亩」就记 province=辽宁、city 留空，
**绝不分摊到六城市**；能定位到区县的才填 district。
"""
from __future__ import annotations

import hashlib
import json
import re
import ssl
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "disaster" / "official_2026"
RAW.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

SOURCES = [
    ("辽宁省人民政府", "我省农业领域积极开展抗灾减损",
     "https://www.ln.gov.cn/web/ywdt/jrln/tpxw/2026071709015153267/index.shtml"),
    ("农业农村部信息网（沈阳日报）", "闻汛而动守沃土 向雨而行护丰收",
     "https://www.agri.cn/zx/xxlb/ln/202607/t20260716_8854266.htm"),
    ("人民网辽宁", "巡堤查险、农田排涝 辽宁全力推进灾后恢复工作",
     "https://ln.people.com.cn/n2/2026/0717/c378320-41642085.html"),
]


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        raw = r.read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def text_of(html: str) -> str:
    b = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S)
    b = re.sub(r"<[^>]+>", "", b)
    b = re.sub(r"&nbsp;|&#160;", " ", b)
    return re.sub(r"\s+", " ", b).strip()


def main() -> None:
    docs = []
    for org, title, url in SOURCES:
        aid = hashlib.md5(url.encode()).hexdigest()[:16]
        out = RAW / f"{aid}.html"
        if not out.exists():
            try:
                out.write_text(get(url), encoding="utf-8")
            except Exception as exc:
                print(f"[FAIL] {url}: {exc}")
                continue
            time.sleep(0.8)
        txt = text_of(out.read_text(encoding="utf-8"))
        docs.append({"org": org, "title": title, "url": url,
                     "article_id": aid, "raw_file": str(out.relative_to(ROOT)),
                     "text": txt,
                     "fetched_at": datetime.now().isoformat(timespec="seconds")})
        print(f"[OK] {org} | {len(txt)} 字 -> {out.name}")

    with (RAW / "official_disaster_docs.json").open("w", encoding="utf-8") as fh:
        json.dump(docs, fh, ensure_ascii=False, indent=1)
    print(f"[OK] 保存 {len(docs)} 篇官方灾情文档")

    # ---- 结构化：2026年7月辽宁特大暴雨（台风"巴威"残余环流）----
    ev = {
        "event_id": "OAD-2026-07-LN-FLOOD",
        "event_name": "2026年7月中旬辽宁持续强降雨洪涝灾害",
        "start_date": "2026-07-13",
        "end_date": "2026-07-17",
        "province": "辽宁省",
        "city": None,             # 灾情统计为全省口径 → 按手册§56 不分摊到城市
        "district": None,
        "event_type": "暴雨洪涝",
        "trigger": "台风残余环流持续强降雨",
        # 省级口径（原文：省农业农村厅统计，截至7月15日）
        "affected_area_total_mu": 2900000,
        "affected_area_note": "全省农作物受影响面积约290万亩（省农业农村厅，截至2026-07-15）",
        "drainage_area_mu": 532700,
        "drainage_note": "排空农田积水53.27万亩（截至2026-07-15）",
        "ditch_dredging_km": 2035,
        "pumped_water_m3": 392000,
        "pumped_note": "累计抽排水39.2万立方米",
        "evacuated_persons": 432089,
        "evacuated_by_city": {"沈阳": 81360, "抚顺": 269437, "辽阳": 20957, "铁岭": 18077},
        "rainfall_total_mm": None,   # 官方未给出全省统一累计值 → 留空
        "max_hourly_rainfall": None,
        "max_temperature": None,
        "crop": "玉米、水稻（主要粮食作物，正值生长关键期）",
        "damaged_area": None,       # 官方未单列成灾面积 → 留空，禁止推测
        "crop_failure_area": None,
        "production_loss": None,
        "economic_loss": None,      # 官方通报中未见可核实的经济损失总额 → 留空
        "other_impact": "设施农业过水；畜牧业牲畜死亡、圈舍损毁；渔业养殖受灾（官方定性描述，无量化面积）",
        "measures": "沟渠疏浚、农田排涝、转移群众、专家技术指导、死亡畜禽无害化处理、圈舍消毒",
        "official_description": (
            "省农业农村厅统计，截至7月15日，本轮持续降雨全省农作物受影响面积约290万亩；"
            "全省已完成沟渠疏浚2035千米，排空农田积水53.27万亩。玉米、水稻正值生长关键期，"
            "持续强降雨导致低洼农田渍涝。截至17日6时全省转移432089人（沈阳81360、抚顺269437、"
            "辽阳20957、铁岭18077）。"),
        "focus_case": {
            "district": "沈北新区",
            "city_belongs_to": "沈阳",
            "detail": ("沈阳市沈北新区兴隆台街道新民村多部门联动清障疏渠、抢排积水；"
                       "7月14日凌晨兴隆台街道万亩农田受淹；十二家子村通州路段农田受淹、路面塌陷；"
                       "101国道沿线高标准农田涉及大营子村、孟家台村、石佛一村、石佛二村；"
                       "蒲河水位暴涨，蒲河大集、道义片区道路积水严重，沿河农户连夜转移"),
            "note": "沈北新区为沈阳市辖区，不作独立城市参与面板分析"
        },
        "source_names": [d["org"] for d in docs],
        "source_urls": [d["url"] for d in docs],
        "raw_files": [d["raw_file"] for d in docs],
        "quality_grade": "A",
        "fetch_time": datetime.now().isoformat(timespec="seconds"),
    }
    (RAW / "official_agricultural_disaster_events.json").write_text(
        json.dumps([ev], ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n[OK] official_agricultural_disaster_events 1 条（2026-07 辽宁暴雨）")
    print(f"    受灾总面积: {ev['affected_area_total_mu']} 亩（省级，city=null）")
    print(f"    排空积水: {ev['drainage_area_mu']} 亩")
    print(f"    转移人数: {ev['evacuated_persons']}")


if __name__ == "__main__":
    main()
