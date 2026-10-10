#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Package C —— 玉米高频市场数据（价格 / 成交量）

【本轮实际可得性（诚实记录）】
1. **辽宁省玉米周度产地收购价**：来自姊妹项目 `liaoning-agri-risk` 已采集的
   辽宁省农业农村厅「粮油周报」（`02_staging/lnnync_grain_weekly.csv`），
   109 周，2024-07-10 ~ 2026-09-17，official_statistic，直接引入并保留完整血缘。
2. **区县级极值**（county_extremum_high/low）：**不是连续序列**，是「全省最高/最低地区」锚定观测，
   单独输出并显著标注，**禁止**与连续价格序列拼接。
3. **沈北新区玉米价格**：公开渠道**未找到** → 记 BLOCKED。
4. **日度价格**：农业农村部批发市场价格系统（pfsc.agri.cn）为 SPA，
   `/api/priceQuotationController/pageList` 返回 404（需进一步解 JS bundle）→ 本轮记 PARTIAL/BLOCKED。
5. **成交量/收购量/上市量**：公开渠道未获得 → 记 BLOCKED。

【价格类型纪律（用户明确要求）】
farmgate / purchase / wholesale / retail / market_monitoring **绝不混接成同一条曲线**，
本表用 price_type 严格分列，并额外输出一张分类型的透视说明。

输出：
  03_clean/market/corn_price_weekly.csv
  03_clean/market/corn_price_by_type.csv
  03_clean/market/MARKET_BLOCKED.md
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "03_clean" / "market"
OUT.mkdir(parents=True, exist_ok=True)
SISTER = Path("/Users/morton_cheung/Desktop/比赛/大数据分析")

STD_COLS = ["date", "commodity", "price", "unit", "price_type", "market_name",
            "location", "location_level", "source_id", "source_name",
            "data_nature", "quality", "note"]


def load_provincial() -> pd.DataFrame:
    src = SISTER / "data/research" / "reference" / "staging" / "lnnync_grain_weekly.csv"
    if not src.exists():
        print(f"[WARN] 未找到姊妹项目数据 {src}")
        return pd.DataFrame()
    d = pd.read_csv(src)
    corn = d[d["crop"].astype(str).str.contains("玉米", na=False)].copy()
    if corn.empty:
        return corn

    def map_row(r):
        kind = r["record_kind"]
        if kind == "province_farm_gate":
            return pd.Series({
                "date": r["date"], "commodity": "玉米", "price": r["price"],
                "unit": r.get("unit_raw", "元/公斤"),
                "price_type": "farmgate",
                "market_name": "辽宁省省级汇总",
                "location": "辽宁省", "location_level": "province",
                "source_id": r.get("source_id", "SRC-LN-NYNC-LY-WEEKLY"),
                "source_name": r.get("source_name", "辽宁省农业农村厅 粮油周报"),
                "data_nature": "official_statistic",
                "quality": r.get("quality_grade", "A"),
                "note": "省级产地收购均价（全省汇总）",
            })
        # county extremum —— 极值锚定，非连续
        hi = kind.endswith("high")
        return pd.Series({
            "date": r["date"], "commodity": "玉米", "price": r["price"],
            "unit": r.get("unit_raw", "元/公斤"),
            "price_type": "farmgate_extremum",
            "market_name": f"全省最高地区" if hi else "全省最低地区",
            "location": r.get("city") or "辽宁省",
            "location_level": "county_extremum",
            "source_id": r.get("source_id", "SRC-LN-NYNC-LY-WEEKLY"),
            "source_name": r.get("source_name", "辽宁省农业农村厅 粮油周报"),
            "data_nature": "official_statistic_extremum",
            "quality": "C",
            "note": ("⚠️极值锚定观测（全省最高/最低地区），**非连续价格序列**，"
                     "禁止与 farmgate 连续序列拼接"),
        })

    out = corn.apply(map_row, axis=1)
    return out[STD_COLS]


def main() -> None:
    prov = load_provincial()
    if prov.empty:
        print("[FAIL] 无省级玉米价格")
        return
    prov = prov.sort_values(["date", "price_type"]).reset_index(drop=True)
    prov.to_csv(OUT / "corn_price_weekly.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] corn_price_weekly.csv {len(prov)} 行")
    print(f"     日期 {prov.date.min()} ~ {prov.date.max()}")
    print(prov.groupby("price_type").agg(
        n=("price", "size"), start=("date", "min"), end=("date", "max"),
        mean=("price", "mean"), unit=("unit", "first")).round(3).to_string())

    # 分类型透视（明确禁止混接）
    cont = prov[prov.price_type == "farmgate"].copy()
    if len(cont):
        cont["year"] = cont["date"].str[:4]
        piv = cont.pivot_table(index="year", values="price", aggfunc=["count", "mean", "min", "max"])
        piv.columns = ["n_weeks", "mean", "min", "max"]
        piv = piv.round(4)
        piv.to_csv(OUT / "corn_price_by_type.csv", encoding="utf-8-sig")
        print("\n=== 省级玉米产地收购价（元/公斤）年度统计 ===")
        print(piv.to_string())

    # 2026 事件窗口
    w = cont[(cont.date >= "2026-06-15") & (cont.date <= "2026-08-31")]
    print(f"\n=== 2026 事件窗口（6-15~8-31）省级玉米周价 {len(w)} 周 ===")
    print(w[["date", "price", "quality"]].to_string(index=False) if len(w) else "  无")

    # BLOCKED 记录
    blk = """# 玉米市场数据 —— 本轮未获取项（BLOCKED / PARTIAL）

| 数据项 | 状态 | 原因 | 已尝试方法 | 人工获取建议 | 替代方案 |
|---|---|---|---|---|---|
| 沈北新区玉米价格 | **BLOCKED** | 区级无公开高频价格发布 | 检索区/市政府门户、农业农村部门 | 向沈北新区农业农村局申请 | 用沈阳市/辽宁省级，明确标注空间层级 |
| 日度玉米价格 | **PARTIAL/BLOCKED** | pfsc.agri.cn 为 SPA，`/api/priceQuotationController/pageList` 返回 404 | 直连 API 猜测路径 | 抓包其前端 JS bundle 找真实接口 | 用周度省级序列（已获取） |
| 成交量 / 收购量 / 上市量 | **BLOCKED** | 无公开高频量数据 | 检索粮食局、粮食和物资储备局 | 国家粮食和物资储备局辽宁局 / 收购进度公告 | 用价格+产量替代，标注为 proxy |
| 农业保险（玉米） | 未获取（Package E 处理） | — | — | — | — |

## 已取得
- 辽宁省玉米**周度产地收购价** 109 周（2024-07-10 ~ 2026-09-17），official_statistic，A 级
- 辽宁省玉米区县级**极值** 218 条（2024-2026），标注为 extremum，C 级，**不可作连续序列**

## 使用红线
- 不得把 `farmgate_extremum` 与 `farmgate` 混为一条曲线
- 不得把辽宁省级价格称为沈北新区价格
"""
    (OUT / "MARKET_BLOCKED.md").write_text(blk, encoding="utf-8")
    print(f"\n[OK] {OUT/'MARKET_BLOCKED.md'}")


if __name__ == "__main__":
    main()
