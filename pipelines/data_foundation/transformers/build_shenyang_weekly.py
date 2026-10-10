"""把沈阳日度价格聚合为 ISO 周序列，并写入建模主表 city_crop_week_panel。

规则（手册§14）：
- 只有真实价格存在才写真实价格；缺周的 price_mean 为 NaN，绝不插值
- 价格类型分开：建模主序列优先 wholesale（批发），retail 单独保留
- 年度生产数据保持年度属性，标记 production_year，不伪装成周度产量
- 周口径与天气完全一致（ISO 周 周一→周日）
"""
from __future__ import annotations
from pathlib import Path

import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
MARTS = ROOT / "city_data/reference/marts"

p = pd.read_parquet(MARTS / "fact_price_city.parquet")
p = p[p["date"].astype(str).str.match(r"^\d{4}-\d{2}-\d{2}$")].copy()
p["dt"] = pd.to_datetime(p["date"])
iso = p["dt"].dt.isocalendar()
p["iso_year"] = iso.year.astype(int)
p["iso_week"] = iso.week.astype(int)
p["week_start"] = (p["dt"] - pd.to_timedelta(p["dt"].dt.weekday, unit="D")).dt.date
p["week_end"] = p["week_start"].apply(lambda d: d + pd.Timedelta(days=6))

sy = p[p["city"] == "沈阳"]
if sy.empty:
    raise SystemExit("无沈阳价格数据")

g = sy.groupby(["crop_raw", "price_type", "iso_year", "iso_week", "week_start", "week_end"])
wk = g.agg(
    price_mean=("price_per_kg", "mean"),
    price_median=("price_per_kg", "median"),
    price_min=("price_per_kg", "min"),
    price_max=("price_per_kg", "max"),
    price_std=("price_per_kg", "std"),
    price_observation_days=("date", "nunique"),
).reset_index()

wk["city"] = "沈阳"
wk = wk.rename(columns={"crop_raw": "crop"})
wk["price_source_level"] = "city"
wk["price_geo_level"] = "city"
print(f"[OK] 沈阳周价序列 {len(wk)} 行")
print(wk.groupby("price_type").size().to_string())
print("\n覆盖：")
for t, s in wk.groupby("price_type"):
    print(f"  {t}: {s['week_start'].min()} ~ {s['week_start'].max()}，"
          f"{s['week_start'].nunique()} 周，{s['crop'].nunique()} 种作物")

# 优先批发价作为主序列
main = wk[wk["price_type"] == "wholesale"].copy()
main = main.sort_values(["crop", "week_start"])

# 与主表合并：把沈阳真实价格写入 city_crop_week_panel
panel_p = MARTS / "city_crop_week_panel.parquet"
if panel_p.exists():
    cp = pd.read_parquet(panel_p)
    # 去掉旧的沈阳占位行（原来农产品价格为空）
    before = len(cp)
    cp = cp[~((cp["city"] == "沈阳") & (cp["price_source_level"] == "unavailable"))]
    cols = ["city", "crop", "iso_year", "iso_week", "week_start", "week_end", "price_mean",
            "price_median", "price_min", "price_max", "price_std", "price_observation_days",
            "price_source_level"]
    add = main[cols].copy()
    add["price_wow_pct"] = main.groupby("crop")["price_mean"].pct_change() * 100
    cp = pd.concat([cp, add], ignore_index=True)
    cp.to_parquet(panel_p, index=False)
    cp.to_csv(MARTS / "city_crop_week_panel.csv", index=False, encoding="utf-8-sig")
    print(f"\n[OK] city_crop_week_panel 更新：{before} -> {len(cp)} 行（注入沈阳真实批发周价）")
    n_real = int((cp["price_source_level"] == "city").sum())
    print(f"    其中城市级真实价格行：{n_real}")

wk.to_parquet(MARTS / "fact_shenyang_price_weekly.parquet", index=False)
wk.to_csv(MARTS / "fact_shenyang_price_weekly.csv", index=False, encoding="utf-8-sig")
print("[OK] fact_shenyang_price_weekly 已保存")
