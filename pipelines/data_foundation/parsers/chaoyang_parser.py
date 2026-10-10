"""解析朝阳「主要菜篮子产品每日价情」HTML 表格 → staging。

结构（已验证）：
  <table>
    <tr><td>名称</td><td>类型</td><td>单位</td><td>全市平均价格</td></tr>
    <tr><td>大米</td><td>标一</td><td>元/500克</td><td>2.90</td></tr>
    ...   （约 31 种商品）
  日期取自正文「时间：YYYY-MM-DD」，缺失时回退到 article_index.json 的 date。

价格层级：朝阳官方表述为"市区主要超市和农贸市场平均价"→ **market_average**，
  按用户规则**不得**标为 wholesale（它不是批发价）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "chaoyang_deep"
STAGING = ROOT / "city_data/reference/staging"
STAGING.mkdir(parents=True, exist_ok=True)


def text_cells(tr: str) -> list[str]:
    tds = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
    out = []
    for x in tds:
        v = re.sub(r"<[^>]+>", "", x)
        v = re.sub(r"&nbsp;|&#160;", " ", v)
        v = re.sub(r"\s+", "", v).strip()
        out.append(v)
    return [x for x in out if x]


def parse_article(html: str) -> list[dict]:
    # 日期
    dm = re.search(r"时间[：:]\s*(20\d\d)[-年](\d{1,2})[-月](\d{1,2})", html)
    date = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}" if dm else None
    if "全市平均价格" not in html:
        return []
    rows = []
    for tb in re.findall(r"<table.*?</table>", html, re.S):
        if "全市平均价格" not in tb:
            continue
        for tr in re.findall(r"<tr.*?</tr>", tb, re.S):
            cells = text_cells(tr)
            if len(cells) < 4:
                continue
            name, spec, unit, price_s = cells[0], cells[1], cells[2], cells[3]
            if name in ("名称", "商品", "品类"):
                continue
            try:
                p = float(price_s.replace(",", ""))
            except ValueError:
                continue
            if p <= 0:
                continue
            rows.append({"name": name, "spec": spec, "unit": unit, "price": p})
        break
    return [{"date": date, **r} for r in rows]


def main() -> None:
    idx_p = RAW / "article_index.json"
    idx = {}
    if idx_p.exists():
        for it in json.loads(idx_p.read_text(encoding="utf-8")):
            idx[it["url"]] = it
    # 反查：html 文件名 = md5(url)[:16]
    url_of = {}
    for u, it in idx.items():
        url_of[u[8:] if False else u] = it

    out = []
    files = sorted(RAW.glob("html/*.html"))
    print(f"待解析 {len(files)} 篇")
    n_with = 0
    for f in files:
        try:
            html = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rows = parse_article(html)
        if not rows:
            continue
        n_with += 1
        # 用索引补日期
        aid = f.stem
        meta = None
        for u, it in idx.items():
            import hashlib
            if hashlib.md5(u.encode()).hexdigest()[:16] == aid:
                meta = it
                break
        fallback_date = meta["date"] if meta else None
        src_url = meta["url"] if meta else ""
        for r in rows:
            d = r["date"] or fallback_date
            if not d:
                continue
            out.append({
                "date": d,
                "city": "朝阳",
                "district": None,
                "geo_level": "city",
                "crop_raw": r["name"],
                "variety": r["spec"],
                "price_type": "market_average",
                "frequency": "daily",
                "price": r["price"],
                "unit_raw": r["unit"],
                "source_id": "SRC-CY-DAILY",
                "source_name": "朝阳市发展和改革委员会 主要菜篮子产品每日价情（市区超市与农贸市场平均价）",
                "source_url": src_url,
                "raw_file": str(f.relative_to(ROOT)),
                "quality_grade": "A",
                "note": "全市平均价格；市区主要超市和农贸市场口径，非批发价",
            })
    print(f"含价格表格的文章 {n_with} 篇，解析记录 {len(out)} 条")
    if not out:
        print("[WARN] 无数据")
        return
    df = pd.DataFrame(out)
    df = df.drop_duplicates(subset=["date", "crop_raw", "variety"])
    df.to_csv(STAGING / "chaoyang_price_daily.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] chaoyang_price_daily.csv {len(df)} 行")
    print(f"    日期 {df['date'].min()} ~ {df['date'].max()}，{df['date'].nunique()} 天，"
          f"{df['crop_raw'].nunique()} 种商品")
    print("    商品:", sorted(df["crop_raw"].unique())[:20])


if __name__ == "__main__":
    main()
