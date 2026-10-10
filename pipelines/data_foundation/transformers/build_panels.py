"""构建最终建模数据集。

关键设计（严守「不把省级价格当市级价格」的红线）：

1. 城市级真实连续价格序列目前只有**农资投入品**（六城市逐市报价，数据源 F）。
   粮油/蔬菜/水果的**城市级日/周价格不可得**（农业农村部 priceQuotation 接口需鉴权、
   商务部源不可达、省发改委价格监测栏目为空），因此：
   - city_crop_week_panel 中农产品 crop 的价格字段**留空并标记 unavailable**，绝不填充省级值；
   - 农产品价格-天气建模走独立的 **province_crop_week_panel**（省级真实连续序列）。
2. 价格周与天气周统一 ISO 周（周一→周日）。
3. 滞后/滚动特征一律使用 shift(1) 之后的过去窗口，杜绝未来数据泄漏。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "AgriScope").is_dir() and (p / "data").is_dir())
CURATED = ROOT / "city_data/reference/curated"
MARTS = ROOT / "city_data/reference/marts"
META = ROOT / "data/raw/metadata"
REPORTS = ROOT / "city_data/reference/reports"
for d in (CURATED, MARTS, META, REPORTS):
    d.mkdir(parents=True, exist_ok=True)

TARGET_CITIES = ["沈阳", "铁岭", "朝阳", "锦州", "丹东", "大连"]
INPUT_MAP = {"尿素": "urea", "复合肥": "compound_fertilizer",
             "磷酸二铵": "diammonium_phosphate", "豆粕": "soybean_meal"}


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    wx = pd.read_parquet(MARTS / "fact_weather_weekly.parquet")
    prov = pd.read_parquet(CURATED / "province_price_weekly.parquet")
    ic = pd.read_parquet(MARTS / "fact_input_cost_weekly.parquet")
    prod = pd.read_parquet(MARTS / "fact_production_yearly.parquet")
    return wx, prov, ic, prod


# ---------------- 1. fact_price_weekly ----------------
def build_price_weekly(prov: pd.DataFrame, ic: pd.DataFrame) -> pd.DataFrame:
    a = prov[prov["record_type"] == "province_avg"].copy()
    a["geo_level"] = "province"
    a["city"] = None
    a["crop"] = a["crop"]
    a = a.rename(columns={"category_key": "source_category"})
    pa = a[["city", "geo_level", "crop", "product_variant", "source_category",
            "iso_year", "iso_week", "week_start", "week_end",
            "price_mean", "price_min", "price_max", "observations", "original_unit"]].copy()
    pa["price_median"] = np.nan
    pa["price_std"] = np.nan
    pa["market_count"] = np.nan
    pa["source_count"] = 1
    pa["price_type"] = "province_avg"

    b = ic.copy()
    b["geo_level"] = "city"
    b["crop"] = b["input_name"]
    b["product_variant"] = None
    b["source_category"] = "agri_input"
    b["price_mean"] = b["price"]
    b["price_median"] = np.nan
    b["price_std"] = np.nan
    b["price_min"] = b["price_min"]
    b["price_max"] = b["price_max"]
    b["market_count"] = np.nan
    b["source_count"] = 1
    b["price_type"] = "city_quote"
    b["original_unit"] = b["unit"]
    b["iso_year"] = b["iso_year"].astype("Int64")
    b["iso_week"] = b["iso_week"].astype("Int64")
    pb = b[["city", "geo_level", "crop", "product_variant", "source_category",
            "iso_year", "iso_week", "week_start", "week_end",
            "price_mean", "price_median", "price_min", "price_max", "price_std",
            "observations", "original_unit", "market_count", "source_count", "price_type"]]

    out = pd.concat([pa, pb], ignore_index=True)
    out = out.sort_values(["geo_level", "city", "crop", "week_start"])
    out["price_wow_pct"] = out.groupby(["geo_level", "city", "crop"], dropna=False)["price_mean"].pct_change() * 100
    return out


# ---------------- 2. 周天气（城市）----------------
def city_weather(wx: pd.DataFrame) -> pd.DataFrame:
    return wx[wx["city"] != "沈北新区"].copy()


# ---------------- 3. city_crop_week_panel ----------------
def build_city_panel(wx: pd.DataFrame, ic: pd.DataFrame, prod: pd.DataFrame,
                     prov: pd.DataFrame, crops: pd.DataFrame) -> pd.DataFrame:
    cw = city_weather(wx)
    cat_map = dict(zip(crops["crop"], crops["category"]))

    # 城市级真实价格序列：仅农资
    ic2 = ic.copy()
    ic2["crop"] = ic2["input_name"]

    # 农产品作物清单（省级有连续序列）
    agri_crops = crops[(~crops["category"].isin(["agricultural_input"]))]["crop"].tolist()

    frames = []
    # (a) 农资：真实城市价格
    for city in TARGET_CITIES:
        w = cw[cw["city"] == city].copy()
        sub = ic2[ic2["city"] == city]
        for crop in sub["crop"].unique():
            s = sub[sub["crop"] == crop][["week_start", "price"]].rename(columns={"price": "price_mean"})
            s["price_source_level"] = "city"
            m = w.merge(s, on="week_start", how="left")
            m["city"] = city
            m["crop"] = crop
            frames.append(m)

    # (b) 农产品：城市天气齐全，但城市级价格不可得 → 价格留空并标记
    for city in TARGET_CITIES:
        w = cw[cw["city"] == city].copy()
        for crop in agri_crops:
            m = w.copy()
            m["city"] = city
            m["crop"] = crop
            m["price_mean"] = np.nan
            m["price_source_level"] = "unavailable"
            frames.append(m)

    panel = pd.concat(frames, ignore_index=True)
    panel["crop_category"] = panel["crop"].map(cat_map)

    # 省级基准价格（明确标注为省级，不冒充城市价）
    pv = prov[prov["record_type"] == "province_avg"].groupby(
        ["crop", "week_start"])["price_mean"].mean().reset_index()
    pv = pv.rename(columns={"price_mean": "liaoning_avg_price", "crop": "crop"})
    panel = panel.merge(pv, on=["crop", "week_start"], how="left")
    # 只有农产品才有省级基准；农资的省级基准用全省均值另行计算
    panel["city_vs_province_price_gap"] = np.where(
        panel["price_source_level"] == "city",
        panel["price_mean"] - panel["liaoning_avg_price"], np.nan)

    # 农资成本列
    for inp, col in [("urea", "urea_price"), ("compound_fertilizer", "compound_fertilizer_price")]:
        s = ic2[ic2["input_name"] == inp][["city", "week_start", "price"]].rename(columns={"price": col})
        panel = panel.merge(s, on=["city", "week_start"], how="left")

    # 年度生产数据（按年对齐）
    if not prod.empty:
        pr = prod.copy()
        pr["crop"] = pr["crop"]
        panel = panel.merge(
            pr[["year", "city", "crop", "planting_area", "production", "yield_per_area"]],
            left_on=["city", "crop"], right_on=["city", "crop"], how="left")
        panel["panel_year"] = pd.to_datetime(panel["week_start"]).dt.year
        panel = panel[(panel["year"].isna()) | (panel["year"] == panel["panel_year"])]
        panel = panel.rename(columns={"planting_area": "planting_area",
                                      "production": "annual_production",
                                      "yield_per_area": "annual_yield"})
        panel = panel.drop(columns=["year", "panel_year"], errors="ignore")

    panel = panel.sort_values(["city", "crop", "week_start"]).reset_index(drop=True)
    return panel


# ---------------- 4. 滞后与滚动特征 ----------------
def add_lags(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    df = df.sort_values(group_cols + ["week_start"]).copy()
    g = df.groupby(group_cols, dropna=False)

    for lag in (1, 2, 4):
        df[f"price_lag_{lag}w"] = g["price_mean"].shift(lag)
        df[f"rain_lag_{lag}w"] = g["precip_sum"].shift(lag)
        df[f"temp_lag_{lag}w"] = g["temp_mean"].shift(lag)
    # 滚动窗口：先 shift(1) 排除当周，再取过去 4/8 周
    s_price = g["price_mean"].shift(1)
    s_rain = g["precip_sum"].shift(1)
    df["price_4w_mean"] = s_price.rolling(4, min_periods=2).mean()
    df["price_8w_mean"] = s_price.rolling(8, min_periods=3).mean()
    df["rain_4w_sum"] = s_rain.rolling(4, min_periods=2).sum()
    df["rain_8w_sum"] = s_rain.rolling(8, min_periods=3).sum()
    return df


# ---------------- 5. 省级作物周面板（农产品建模主力）----------------
def build_province_panel(wx: pd.DataFrame, prov: pd.DataFrame, crops: pd.DataFrame) -> pd.DataFrame:
    """辽宁省农产品（粮油/蔬菜/水果）× 周：省级真实价格 + 六城市平均天气。"""
    pv = prov[prov["record_type"] == "province_avg"].copy()
    # 必须 dropna=False：大多数记录没有品种变体，默认 groupby 会整行丢弃它们
    # （曾因此丢失约 90% 的省级序列）。
    pv = pv.groupby(["crop", "product_variant", "week_start", "week_end"], dropna=False).agg(
        price_mean=("price_mean", "mean"),
        observations=("observations", "sum")).reset_index()

    # 省级天气 = 六城市均值（与目标城市集合一致，避免混入非目标城市）
    cw = city_weather(wx)
    pw = cw.groupby(["week_start", "week_end"]).agg(
        temp_mean=("temp_mean", "mean"), temp_max=("temp_max", "max"),
        temp_min=("temp_min", "min"), precip_sum=("precip_sum", "mean"),
        precip_max_daily=("precip_max_daily", "max"),
        rain_days=("rain_days", "mean"),
        heavy_rain_25mm_days=("heavy_rain_25mm_days", "max"),
        rainstorm_50mm_days=("rainstorm_50mm_days", "max"),
        hot_35c_days=("hot_35c_days", "max"),
        humidity_mean=("humidity_mean", "mean"),
        wind_max=("wind_max", "max"),
        sunshine_sum=("sunshine_sum", "mean"),
        temp_anomaly=("temp_anomaly", "mean"),
        precip_anomaly=("precip_anomaly", "mean"),
    ).reset_index()

    out = pv.merge(pw, on=["week_start", "week_end"], how="left")
    cat_map = dict(zip(crops["crop"], crops["category"]))
    out["crop_category"] = out["crop"].map(cat_map)
    out["city"] = "辽宁省"
    out = out.sort_values(["crop", "week_start"])
    g = out.groupby(["crop", "product_variant"], dropna=False)
    out["price_wow_pct"] = g["price_mean"].pct_change() * 100
    for lag in (1, 2, 4):
        out[f"price_lag_{lag}w"] = g["price_mean"].shift(lag)
        out[f"rain_lag_{lag}w"] = g["precip_sum"].shift(lag)
        out[f"temp_lag_{lag}w"] = g["temp_mean"].shift(lag)
    sp = g["price_mean"].shift(1)
    sr = g["precip_sum"].shift(1)
    out["price_4w_mean"] = sp.rolling(4, min_periods=2).mean()
    out["price_8w_mean"] = sp.rolling(8, min_periods=3).mean()
    out["rain_4w_sum"] = sr.rolling(4, min_periods=2).sum()
    out["rain_8w_sum"] = sr.rolling(8, min_periods=3).sum()
    return out


# ---------------- 6. 年度面板 ----------------
def build_year_panel(wx: pd.DataFrame, prod: pd.DataFrame, prov: pd.DataFrame) -> pd.DataFrame:
    if prod.empty:
        return pd.DataFrame()
    daily = pd.read_parquet(MARTS / "fact_weather_daily.parquet")
    daily = daily[daily["city"] != "沈北新区"].copy()
    daily["year"] = pd.to_datetime(daily["date"]).dt.year
    wy = daily.groupby(["city", "year"]).agg(
        annual_precip=("precip", "sum"),
        annual_temp=("temp_mean", "mean"),
        heat_days=("temp_max", lambda s: int((s >= 35).sum())),
        rainstorm_days=("precip", lambda s: int((s >= 50).sum())),
        freezing_days=("temp_min", lambda s: int((s <= 0).sum())),
    ).reset_index()
    # 生长季（5-9月）降水
    gs = daily[pd.to_datetime(daily["date"]).dt.month.isin([5, 6, 7, 8, 9])]
    gsp = gs.groupby(["city", "year"])["precip"].sum().reset_index(
        name="growth_season_precip")
    wy = wy.merge(gsp, on=["city", "year"], how="left")
    out = prod.merge(wy, left_on=["city", "year"], right_on=["city", "year"], how="left")
    return out


def main() -> None:
    wx, prov, ic, prod = load_inputs()
    crops = pd.read_csv(META / "crops.csv")

    # fact_price_weekly
    pw = build_price_weekly(prov, ic)
    pw.to_parquet(MARTS / "fact_price_weekly.parquet", index=False)
    pw.to_csv(MARTS / "fact_price_weekly.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] fact_price_weekly {len(pw)} 行")

    # city_crop_week_panel
    cp = build_city_panel(wx, ic, prod, prov, crops)
    cp = add_lags(cp, ["city", "crop"])
    keep = ["city", "crop", "crop_category", "iso_year", "iso_week", "week_start", "week_end",
            "price_mean", "price_source_level", "price_wow_pct",
            "temp_mean", "temp_max", "temp_min", "precip_sum", "precip_max_daily",
            "rain_days", "heavy_rain_25mm_days", "rainstorm_50mm_days",
            "longest_consecutive_rain_days", "hot_35c_days", "freezing_days",
            "humidity_mean", "wind_mean", "wind_max", "sunshine_sum",
            "temp_anomaly", "precip_anomaly", "weather_source", "station_count",
            "urea_price", "compound_fertilizer_price",
            "liaoning_avg_price", "city_vs_province_price_gap",
            "planting_area", "annual_production", "annual_yield",
            "price_lag_1w", "price_lag_2w", "price_lag_4w",
            "rain_lag_1w", "rain_lag_2w", "rain_lag_4w",
            "temp_lag_1w", "temp_lag_2w", "temp_lag_4w",
            "rain_4w_sum", "rain_8w_sum", "price_4w_mean", "price_8w_mean"]
    for c in keep:
        if c not in cp.columns:
            cp[c] = np.nan
    cp = cp[keep]
    cp.to_parquet(MARTS / "city_crop_week_panel.parquet", index=False)
    cp.to_csv(MARTS / "city_crop_week_panel.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] city_crop_week_panel {len(cp)} 行")
    print("   有真实城市价格的:", int((cp["price_source_level"] == "city").sum()))
    print("   价格不可得(留空):", int((cp["price_source_level"] == "unavailable").sum()))

    # province_crop_week_panel
    pp = build_province_panel(wx, prov, crops)
    pp.to_parquet(MARTS / "province_crop_week_panel.parquet", index=False)
    pp.to_csv(MARTS / "province_crop_week_panel.csv", index=False, encoding="utf-8-sig")
    print(f"[OK] province_crop_week_panel {len(pp)} 行")

    # 年度面板
    yp = build_year_panel(wx, prod, prov)
    if not yp.empty:
        yp.to_parquet(MARTS / "city_crop_year_panel.parquet", index=False)
        yp.to_csv(MARTS / "city_crop_year_panel.csv", index=False, encoding="utf-8-sig")
        print(f"[OK] city_crop_year_panel {len(yp)} 行")


if __name__ == "__main__":
    main()
