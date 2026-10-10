"""提取沈阳批发市场的日成交量（volume）→ fact_market_supply。

手册§19 的 P1 任务：验证「暴雨 → 采摘/运输受阻 → 市场供应下降 → 农产品价格上涨」。
此前误判为 NOT_PUBLIC，实际沈阳批发接口的 volume 字段就是日成交量：
  - 16,550 条记录全部非零（零售 volume 恒为 0，说明只有批发口径统计）
  - 另有 dayVolumeRatio 字段（日成交量环比）8,448 条有效

单位：接口未提供 volume 的单位字段。从量级看（土豆均值约 283、尖椒约 87）
推断为「吨」，但**官方未标注**，因此 unit_raw 记为「未标注(推断为吨)」，不做换算。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
RAW = ROOT / "data/raw" / "prices" / "shenyang_clz"
MARTS = ROOT / "city_data/reference/marts"
MARTS.mkdir(parents=True, exist_ok=True)


def main() -> None:
    rows = []
    for f in sorted(RAW.glob("*_mt1.json")):      # 仅批发口径有成交量
        m = re.match(r"(20\d\d-\d\d-\d\d)", f.name)
        if not m:
            continue
        d = m.group(1)
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for it in j.get("data") or []:
            try:
                vol = float(it.get("volume"))
            except (TypeError, ValueError):
                continue
            if vol <= 0:
                continue
            try:
                ratio = float(it.get("dayVolumeRatio"))
            except (TypeError, ValueError):
                ratio = None
            rows.append({
                "date": d,
                "city": "沈阳",
                "market": "沈阳市批发市场平均（市本级）",
                "crop": it.get("productName"),
                "supply_volume": vol,
                "unit_raw": "未标注(推断为吨)",
                "supply_volume_ratio_dod": ratio,
                "source_id": "SRC-SY-CLZ",
                "source_name": "沈阳市发展和改革委员会 菜篮子信息发布平台",
                "source_url": "https://fgw.shenyang.gov.cn/wjgz/clzxxfbpt/",
                "raw_file": str(f.relative_to(ROOT)),
                "quality_grade": "A",
                "note": "批发口径日成交量；零售口径 volume 恒为 0（未统计，非真实零成交）",
            })

    df = pd.DataFrame(rows)
    if df.empty:
        print("[WARN] 无成交量数据")
        return
    df.to_parquet(MARTS / "fact_market_supply.parquet", index=False)
    df.to_csv(MARTS / "fact_market_supply.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] fact_market_supply {len(df)} 条")
    print(f"    作物 {df['crop'].nunique()} 种，日期 {df['date'].nunique()} 天")
    print(f"    时间 {df['date'].min()} ~ {df['date'].max()}")
    print()
    print("按品种统计：")
    print(df.groupby("crop")["supply_volume"].agg(["count", "mean", "min", "max"]).round(1).to_string())
    print()
    print("⚠ 单位未在接口中标注，从量级推断为吨，未做换算")


if __name__ == "__main__":
    main()
