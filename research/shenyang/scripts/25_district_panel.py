"""STEP D6 — 区县年度「天气 × 面积 × 产量 × 单产」生产分析面板。

粒度：年份 × 区县 × 作物（district_yearly_agri_weather_panel）。

合并逻辑：
  · 农业生产三表（面积/产量/单产）来自《沈阳统计年鉴》分区县表，按 (year, district, crop) 对齐；
  · 气象来自 district_weather_yearly（year × district），按 (year, district) 广播到每个作物行；
  · 单产双口径：yield_official（年鉴直接公布）与 yield_calculated（=产量÷面积，仅作质量校验）。

输出字段（对应任务书 §十）：
  身份：year, district, crop
  农业：sown_area(公顷), production(吨), yield_value(公斤/公顷), yield_method
  天气：growing_season_temp_mean, growing_season_precip, hot_days, heavy_rain_days,
        max_1d_precip, max_3d_precip, max_5d_precip, humidity_mean, vpd_mean, et0_sum
  质量：production_source_grade, weather_source, coverage_flag, notes

coverage_flag 取值：
  production_only  — 有生产、无气象（本年气象缺失）
  full             — 生产与气象均有
  weather_only     — 仅气象（该作物本年无生产数据，仅出现在天气侧，不进面板）

产出（data/processed/）：district_yearly_agri_weather_panel.parquet / .csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PATHS, StepTimer, get_logger  # noqa: E402

MOD = "25_district_panel"
LOG = get_logger(MOD)
PROC = PATHS.project["data_processed"]

WEATHER_COLS = ["growing_season_temp_mean", "growing_season_precip", "hot_days",
                "heavy_rain_days", "max_1d_precip", "max_3d_precip", "max_5d_precip",
                "humidity_mean", "vpd_mean", "et0_sum"]


def main() -> None:
    with StepTimer(MOD, LOG):
        log = LOG
        area = pd.read_csv(PROC / "district_crop_area.csv")
        prod = pd.read_csv(PROC / "district_crop_production.csv")
        yld = pd.read_csv(PROC / "district_crop_yield.csv")
        wx = pd.read_csv(PROC / "district_weather_yearly.csv")

        key = ["year", "district", "crop"]
        a = area[key + ["sown_area", "area_unit", "source_grade"]].rename(
            columns={"source_grade": "area_source_grade"})
        p = prod[key + ["production", "production_unit", "source_grade"]].rename(
            columns={"source_grade": "production_source_grade"})
        y = yld[key + ["yield_value", "yield_unit", "yield_method"]]

        df = a.merge(p, on=key, how="outer").merge(y, on=key, how="outer")

        # 早期年份补充（2015-2017，区县年鉴，来源等级 B）：康平县 粮食/油料/蔬菜/水果
        early_p = PROC / "district_early_years.csv"
        if early_p.exists():
            e = pd.read_csv(early_p)
            e_area = (e[e["metric"] == "sown_area"][["year", "district", "crop", "value_std"]]
                      .rename(columns={"value_std": "sown_area"}))
            e_prod = (e[e["metric"] == "production"][["year", "district", "crop", "value_std"]]
                      .rename(columns={"value_std": "production"}))
            e_w = e_area.merge(e_prod, on=key, how="outer")
            e_w["area_unit"], e_w["production_unit"] = "公顷", "吨"
            e_w["area_source_grade"] = "B"
            e_w["production_source_grade"] = "B"
            e_w["early_source"] = "《康平县国民经济统计资料汇编》(区县年鉴)"
            df = pd.concat([df, e_w], ignore_index=True)
            log.info("并入早期年份补充：%d 行（康平县 2015-2017）", len(e_w))

        # 气象按 (year, district) 广播（补充行也一并合并）
        df = df.merge(wx[["year", "district"] + WEATHER_COLS], on=["year", "district"], how="left")

        # 派生：单产复核（产量吨 → 公斤，面积公顷）
        df["yield_calculated"] = np.where(
            df["sown_area"].gt(0) & df["production"].notna(),
            df["production"] * 1000.0 / df["sown_area"], np.nan)
        df["yield_rel_diff"] = np.where(
            df["yield_value"].gt(0),
            (df["yield_calculated"] - df["yield_value"]).abs() / df["yield_value"], np.nan)

        df["coverage_flag"] = np.where(
            df["sown_area"].notna() & df["growing_season_temp_mean"].notna(), "full",
            np.where(df["sown_area"].notna(), "production_only", "weather_only"))
        df["weather_source"] = "open-meteo-era5-reanalysis"
        if "early_source" not in df.columns:
            df["early_source"] = ""
        df["early_source"] = df["early_source"].fillna("")
        df["notes"] = ("生产=《沈阳统计年鉴》分区县农业表(A级，2018-2024)；"
                       "康平县 2015-2017 为区县年鉴(B级，见 early_source)；"
                       "气象=Open-Meteo ERA5 再分析(区县行政中心代表点)；"
                       "单产 official=年鉴公布，calculated=产量/面积（仅校验）")

        df = df.sort_values(["year", "district", "crop"]).reset_index(drop=True)

        out_csv = PROC / "district_yearly_agri_weather_panel.csv"
        df.to_csv(out_csv, index=False, encoding="utf-8-sig")
        pq = PATHS.artifacts["district_yearly_panel"]
        df.to_parquet(pq, index=False)
        log.info("已写 %s：%d 行 × %d 列", pq.name, len(df), df.shape[1])
        log.info("年份 %s；区县 %d；作物 %d",
                 sorted(df["year"].unique()), df["district"].nunique(), df["crop"].nunique())
        log.info("coverage_flag：%s", df["coverage_flag"].value_counts().to_dict())
        log.info("单产复核 |相对差| 中位数 %.3f，>5%% 的行 %d / %d",
                 float(np.nanmedian(df["yield_rel_diff"])),
                 int((df["yield_rel_diff"] > 0.05).sum()), int(df["yield_rel_diff"].notna().sum()))


if __name__ == "__main__":
    main()
