"""病虫害文章结构化（手册第 15 节）。

只做确定性提取：从标题/正文匹配作物名与病虫害名、严重度词、区域描述。
文章只写「辽西北局部」这类区域时保存到 region_raw，**不映射到具体城市**。
缺失字段一律留空。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "pests"
MARTS = ROOT / "city_data/reference/marts"
MARTS.mkdir(parents=True, exist_ok=True)

CROPS = ["玉米", "水稻", "大豆", "花生", "小麦", "蔬菜", "苹果", "梨", "葡萄", "马铃薯", "谷子", "高粱"]
PESTS = ["草地贪夜蛾", "粘虫", "玉米螟", "稻瘟病", "稻飞虱", "二化螟", "蝗虫", "蚜虫",
         "红蜘蛛", "棉铃虫", "锈病", "白粉病", "赤霉病", "叶斑病", "纹枯病", "蓟马",
         "盲蝽", "菜青虫", "小菜蛾", "夜蛾"]
SEVERITY_WORDS = {"大发生": 3, "严重": 3, "偏重": 2, "中等": 2, "偏轻": 1, "轻": 1, "零星": 1}
REGIONS = ["辽西北", "辽西", "辽北", "辽南", "辽东", "辽中", "辽河平原", "全省", "沈阳", "大连",
           "鞍山", "抚顺", "本溪", "丹东", "锦州", "营口", "阜新", "辽阳", "盘锦", "铁岭",
           "朝阳", "葫芦岛"]
CITIES = ["沈阳", "铁岭", "朝阳", "锦州", "丹东", "大连"]


def extract(rec: dict) -> dict:
    title = rec.get("title", "") or ""
    text = (title + "\n" + (rec.get("raw_text", "") or ""))[:6000]
    crops = [c for c in CROPS if c in text]
    pests = [p for p in PESTS if p in text]
    sev = None
    for w, v in SEVERITY_WORDS.items():
        if w in text:
            sev = max(sev or 0, v)
    regs = [r for r in REGIONS if r in text]
    cities_hit = [c for c in CITIES if c in text]
    return {
        "article_id": rec.get("article_id"),
        "publication_date": rec.get("list_date") or "",
        "title": title,
        "site": rec.get("site"),
        "column": rec.get("column"),
        "crop": "|".join(crops) if crops else "",
        "pest_or_disease": "|".join(pests) if pests else "",
        "severity": sev,
        "region_raw": "|".join(regs) if regs else "",
        "city_mentioned": "|".join(cities_hit) if cities_hit else "",
        "city": "",          # 不自动映射：多数报道为区域级描述
        "district": "",
        "affected_area": None,   # 原文多为定性描述，未给出可结构化面积
        "predicted_area": None,
        "source": rec.get("site", "") + " " + (rec.get("url", "") or ""),
        "source_url": rec.get("url", ""),
    }


def main() -> None:
    src = RAW / "pest_articles.jsonl"
    if not src.exists():
        print("[WARN] 无病虫害文章")
        return
    rows = [extract(json.loads(l)) for l in src.open(encoding="utf-8") if l.strip()]
    df = pd.DataFrame(rows)
    df["data_type"] = "text_extracted"
    df.to_parquet(MARTS / "fact_pest_events.parquet", index=False)
    df.to_csv(MARTS / "fact_pest_events.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] fact_pest_events {len(df)} 行")
    print("   含病虫害名:", int((df['pest_or_disease'] != '').sum()))
    print("   含作物名:", int((df['crop'] != '').sum()))
    print("   区域描述样例:", df['region_raw'].value_counts().head(5).to_dict())


if __name__ == "__main__":
    main()
