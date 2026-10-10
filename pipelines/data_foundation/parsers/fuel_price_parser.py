"""解析辽宁省成品油调价公告 PDF → 油价表与有效期序列（手册第 21 节）。

规则：
- 只提取公告原文中的数字，不做任何换算或估算；
- 生效时间取公告原文「自 YYYY 年 M 月 D 日 24 时起执行」；
- 生成 valid_from / valid_to 阶梯序列（一次调价 → 下次调价前保持）——
  这是**官方价格有效期**转换，不是插值，手册明确允许。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "macro" / "fuel"
MARTS = ROOT / "city_data/reference/marts"
CURATED = ROOT / "city_data/reference/curated"
for d in (MARTS, CURATED):
    d.mkdir(parents=True, exist_ok=True)

EFFECT_RE = re.compile(r"自\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*24\s*时起执行")
# 行式价格：「92 号车用汽油 10595 10913」
ROW_RE = re.compile(r"(\d{2})\s*号车用汽油\s+(\d+)\s+(\d+)")
ROW95_RE = re.compile(r"(95)\s*号车用汽油\s+(\d+)\s+(\d+)")
DIESEL_RE = re.compile(r"柴油标准品\s+(\d+)\s+(\d+)")


def parse_pdf(path: Path) -> dict | None:
    try:
        txt = "".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    except Exception:
        return None
    txt = re.sub(r"[ \u3000]", " ", txt)
    rec = {"file": path.name}

    m = EFFECT_RE.search(txt)
    if m:
        rec["effective_date"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    for pat, key in [(ROW_RE, "gasoline_92"), (ROW95_RE, "gasoline_95")]:
        mm = pat.search(txt)
        if mm:
            rec[f"{key}_wholesale"] = float(mm.group(2))
            rec[f"{key}_retail"] = float(mm.group(3))

    mm = DIESEL_RE.search(txt)
    if mm:
        rec["diesel_0_wholesale"] = float(mm.group(1))
        rec["diesel_0_retail"] = float(mm.group(2))

    rec["unit"] = "元/吨"
    rec["source_url"] = "https://fgw.ln.gov.cn/ 辽宁省成品油价格调整公告"
    rec["source"] = "辽宁省发展和改革委员会"
    rec["raw_file"] = str(path.relative_to(ROOT))
    return rec


def main() -> None:
    rows = []
    for pdf in sorted(RAW.glob("*.pdf")):
        r = parse_pdf(pdf)
        if r:
            rows.append(r)
            print(f"[OK] {pdf.name} -> {r.get('effective_date')} "
                  f"92#零售={r.get('gasoline_92_retail')} 0#柴油零售={r.get('diesel_0_retail')}")
    if not rows:
        print("[WARN] 未解析到油价")
        return

    df = pd.DataFrame(rows).dropna(subset=["effective_date"]).sort_values("effective_date")
    # 有效期阶梯：当前公告生效 → 下一公告生效前一日
    df["valid_from"] = df["effective_date"]
    nxt = pd.to_datetime(df["effective_date"]).shift(-1) - pd.Timedelta(days=1)
    df["valid_to"] = nxt.dt.strftime("%Y-%m-%d")
    df["price_type"] = "official_max_retail_wholesale"
    df["note"] = "公告为最高批发/零售价；有效期阶梯来自公告生效时间，非插值"

    df.to_parquet(MARTS / "fact_fuel_price.parquet", index=False)
    df.to_csv(MARTS / "fact_fuel_price.csv", index=False, encoding="utf-8-sig")
    print(f"\n[OK] fact_fuel_price {len(df)} 条")
    print(df[["effective_date", "valid_from", "valid_to",
              "gasoline_92_retail", "gasoline_95_retail", "diesel_0_retail"]].to_string(index=False))

    # 登记覆盖情况
    cov = {
        "table": "fact_fuel_price",
        "rows": int(len(df)),
        "date_min": str(df["effective_date"].min()),
        "date_max": str(df["effective_date"].max()),
        "note": "仅公开近期公告（栏目仅保留最近若干期），历史调价公告未公开",
        "coverage_limitation": "2021-01-01~2026-06 的调价公告在发改委网站未见公开条目",
    }
    (CURATED / "fuel_price_coverage.json").write_text(
        json.dumps(cov, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[OK] fuel_price_coverage.json")


if __name__ == "__main__":
    main()
