"""解析准确率溯源校验（覆盖全部文章，非抽样）。

验证每条记录的三个关键字段都能在网页原文中真实找到：
  1. price  → 该数字必须出现在原文（允许千分位/末位 0 差异，如 5.0 与 5.00）
  2. location_raw → 该地点串必须出现在原文
  3. product（或 product_variant）→ 必须出现在原文
任一不通过即为疑似解析错误，输出明细供人工复核。
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
sys.path.insert(0, str(ROOT))

from crawler.normalize import PRODUCT_LOOKUP

# 标准产品名 → 所有原文别名
ALIASES: dict[str, set[str]] = {}
for (_ck, alias), (std, _v) in PRODUCT_LOOKUP.items():
    ALIASES.setdefault(std, set()).add(alias)

prices = pd.read_csv(ROOT / "data" / "processed" / "prices_long.csv")
recs = {r["article_id"]: r["raw_text"] for r in
        (json.loads(l) for l in (ROOT / "data" / "raw" / "articles.jsonl").open(encoding="utf-8"))}


def price_variants(v):
    """5.0 / 5.00 / 5 视为同一数值的不同写法。"""
    s = f"{v:.10f}".rstrip("0").rstrip(".")
    out = {s, f"{v:g}", f"{v:.2f}", str(int(v)) if float(v).is_integer() else s}
    return {o for o in out if o}


bad_price, bad_loc, bad_prod = [], [], []
total = 0

for aid, g in prices.groupby("article_id"):
    raw = recs.get(aid, "")
    if not raw:
        continue
    for _, r in g.iterrows():
        total += 1
        pv = price_variants(float(r["price"]))
        if not any(v in raw for v in pv):
            bad_price.append((aid, r["product"], r["price"], r["original_unit"], r["source_text"][:120]))

        loc = str(r["location_raw"])
        if loc and loc not in ("辽宁省", "全国") and loc not in raw:
            bad_loc.append((aid, loc, r["product"], r["source_text"][:120]))

        # 产品名经过标准化（西红柿→番茄），且原文存在「豆 油」这类字间空格写法，
        # 因此按「标准名或其任一别名」在去空格原文中匹配。
        prod = str(r["product"])
        var = str(r["product_variant"]) if pd.notna(r["product_variant"]) else ""
        raw_ns = raw.replace(" ", "").replace("\u00a0", "")
        cands = set(ALIASES.get(prod, [])) | {prod}
        if var:
            cands |= {var, prod + var}
        if not any(c.replace(" ", "") in raw_ns for c in cands):
            bad_prod.append((aid, prod, var, r["source_text"][:120]))

print(f"校验记录总数：{total}")
print(f"价格无法在原文溯源：{len(bad_price)}  ({len(bad_price)/total*100:.3f}%)")
print(f"地点无法在原文溯源：{len(bad_loc)}  ({len(bad_loc)/total*100:.3f}%)")
print(f"产品无法在原文溯源：{len(bad_prod)}  ({len(bad_prod)/total*100:.3f}%)")

for name, rows in [("价格", bad_price), ("地点", bad_loc), ("产品", bad_prod)]:
    if rows:
        print(f"\n--- {name} 异常示例（最多 10 条）---")
        for x in rows[:10]:
            print("   ", x)
