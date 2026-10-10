"""解析商务部「大连商务预报」蔬菜批发价格表 → staging。

关键事实（踩过坑）：
  该页价格数据**不在 <table> 标签内**，而是**纯文本逐行排列**：
      序号 / 品种 / 市场1价格 / 市场2价格 / 周对比1 / 周对比2 / 涨幅%
      1 / 青椒 / 3.00 / 3.30 / 3.50 / 3.15 / -10.00%
  必须按行解析；用 <table> 解析会得到 0 条。

口径：
  - 前两个市场列（通常「双兴」「南关岭」）→ geo_level=market，各自成记录
  - 单位 元/公斤 → price_type=wholesale
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "dalian_mofcom"
STAGING = ROOT / "city_data/reference/staging"
STAGING.mkdir(parents=True, exist_ok=True)

CROPS = set("""青椒 芸豆 黄瓜 茄子 西红柿 芹菜 韭菜 菠菜 蒜苔 甘蓝 大白菜 青萝卜 土豆
圆葱 油菜 尖椒 冬瓜 茭瓜 菜花 胡萝卜 白萝卜 生菜 小白菜 油麦菜 南瓜 豆角
香菜 茼蒿 苦瓜 丝瓜 西葫芦 山药 莲藕 生姜 大蒜""".split())


def main() -> None:
    rows = []
    files = sorted(RAW.glob("html/*.html"))
    print(f"待解析 {len(files)} 篇")
    parsed = 0
    for f in files:
        t = f.read_text(encoding="utf-8", errors="replace")
        if "批发价格" not in t:
            continue
        dm = re.search(r"统计表（(\d{1,2})月(\d{1,2})日）", t)
        ym = re.search(r"发布时间：\s*(20\d\d)", t)
        if not (dm and ym):
            continue
        date = f"{ym.group(1)}-{int(dm.group(1)):02d}-{int(dm.group(2)):02d}"

        body = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", t, flags=re.S)
        body = re.sub(r"<[^>]+>", "\n", body)
        body = re.sub(r"&nbsp;|&#160;", " ", body)
        lines = [x.strip() for x in body.split("\n") if x.strip()]
        joined = "\n".join(lines)

        mk = re.search(r"序号\s*品种\s*([\u4e00-\u9fa5]{2,8})\s*([\u4e00-\u9fa5]{2,8})", joined)
        mk1 = mk.group(1) if mk else "双兴"
        mk2 = mk.group(2) if mk else "南关岭"

        got = False
        i = 0
        while i < len(lines):
            if (re.fullmatch(r"\d{1,3}", lines[i]) and i + 1 < len(lines)
                    and lines[i + 1] in CROPS):
                name = lines[i + 1]
                nums = lines[i + 2:i + 7]
                for idx, mname in ((0, mk1), (1, mk2)):
                    if idx >= len(nums):
                        continue
                    try:
                        v = float(nums[idx])
                    except ValueError:
                        continue
                    if v <= 0:
                        continue
                    rows.append({
                        "date": date, "city": "大连", "district": None,
                        "geo_level": "market", "market_name": mname,
                        "crop_raw": name, "variety": "",
                        "price_type": "wholesale", "frequency": "weekly",
                        "price": v, "unit_raw": "元/公斤", "price_per_kg": v,
                        "source_id": "SRC-DL-MOFCOM",
                        "source_name": "商务部 大连商务预报（大连市商务局）",
                        "source_url": "", "raw_file": str(f.relative_to(ROOT)),
                        "quality_grade": "A",
                        "note": "批发市场逐品种批发价（源为文本行式排版，非HTML表格）",
                    })
                    got = True
                i += 7
            else:
                i += 1
        if got:
            parsed += 1

    if not rows:
        print("[WARN] 无解析结果")
        return
    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["date", "market_name", "crop_raw"])
    df.to_csv(STAGING / "dalian_mofcom_price.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] 含价格表文章 {parsed} 篇，解析 {len(df)} 条")
    print(f"    日期 {df['date'].min()} ~ {df['date'].max()}")
    print(f"    市场 {sorted(df['market_name'].unique())}")
    print(f"    品种 {df['crop_raw'].nunique()} 种")


if __name__ == "__main__":
    main()
