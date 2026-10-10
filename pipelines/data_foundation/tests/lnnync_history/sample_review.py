"""人工抽样验收辅助脚本：输出「网页原文段落」与「CSV 解析结果」的对照，供逐条核对。"""
import json
import random
import sys
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
sys.path.insert(0, str(ROOT))

prices = pd.read_csv(ROOT / "data" / "processed" / "prices_long.csv")
arts = pd.read_csv(ROOT / "data" / "processed" / "articles.csv")
recs = {r["article_id"]: r for r in (json.loads(l) for l in (ROOT / "data" / "raw" / "articles.jsonl").open(encoding="utf-8"))}

random.seed(20260921)


def pick(cat_key, when="latest"):
    sub = arts[arts["category_key"] == cat_key].sort_values("publication_date")
    return sub.iloc[-1] if when == "latest" else sub.iloc[0]


samples = []
# 强制样本：每类最新 + 最老
for ck in ["grain_oil", "vegetable", "fruit", "agri_input"]:
    samples.append((pick(ck, "latest"), "最新"))
    samples.append((pick(ck, "oldest"), "最老"))
# 随机补充（含不同年份、含市/县级数据）
for ck, n in [("grain_oil", 3), ("vegetable", 3), ("fruit", 3), ("agri_input", 1)]:
    sub = arts[arts["category_key"] == ck]
    for _, r in sub.sample(min(n, len(sub))).iterrows():
        samples.append((r, "随机"))

print(f"抽样文章数：{len(samples)}\n")
for a, tag in samples:
    aid = a["article_id"]
    print("=" * 100)
    print(f"[{tag}] {a['category']} | {a['publication_date']} | 第{a['week']}周 | {a['title']}")
    print(f"  周期 {a['period_start']} ~ {a['period_end']} | {aid}")
    print("  --- 原文 ---")
    raw = recs[aid]["raw_text"]
    for ln in raw.split("\n"):
        if ln.strip() and ("【" in ln or "本周" in ln or "上周" in ln):
            print("   ", ln[:260])
    print("  --- 解析结果 ---")
    sub = prices[prices["article_id"] == aid]
    for _, r in sub.iterrows():
        print(f"    {str(r['product']):8s} {str(r['product_variant'] or '-'):6s} {r['record_type']:13s} "
              f"{r['price']:>9} {r['original_unit']:7s} | {str(r['location_raw']):16s} "
              f"{r['geo_level']:8s} city={str(r['city'] or '-'):5s} county={str(r['county'] or '-'):10s} "
              f"mom={r['mom_change_pct']} yoy={r['yoy_change_pct']}")
    print()
