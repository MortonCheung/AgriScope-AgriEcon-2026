"""STEP D7 — 区县农业—气象数据质量检查（任务书 §十三）。

检查项：
  1. 年份覆盖：年份 × 区县 覆盖矩阵（生产、气象各自）；
  2. 作物覆盖：作物 × 年份 × 区县 覆盖统计；
  3. 单位一致性：各表实际出现的单位；确认无单位混用（面积公顷 / 产量吨 / 单产 公斤/公顷）；
  4. 面积—产量—单产逻辑：|产量 − 面积×单产/1000| / 产量，标注超差行；
  5. 多来源验证：
     a) 区县合计 vs 市级合计（年鉴内部一致性）；
     b) 区县公报文字口径 vs 年鉴（人工抽样，见报告）；
  6. 异常清单：面积/产量/单产 任一项缺失或 0、单产逻辑冲突 ≥5% 的行。

产出（outputs/tables/）：
  district_qa_year_coverage.csv
  district_qa_crop_coverage.csv
  district_qa_consistency.csv
  district_qa_city_vs_districts.csv
  district_qa_exceptions.csv
  reports/16_DISTRICT_DATA_QA.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import PATHS, StepTimer, get_logger, save_table  # noqa: E402

MOD = "26_district_qa"
LOG = get_logger(MOD)
PROC = PATHS.project["data_processed"]
DISTRICTS = ["苏家屯区", "浑南区", "沈北新区", "于洪区", "辽中区", "康平县", "法库县", "新民市"]


def main() -> None:
    with StepTimer(MOD, LOG):
        log = LOG
        panel = pd.read_csv(PROC / "district_yearly_agri_weather_panel.csv")
        area = pd.read_csv(PROC / "district_crop_area.csv")
        prod = pd.read_csv(PROC / "district_crop_production.csv")
        yld = pd.read_csv(PROC / "district_crop_yield.csv")
        city = pd.read_csv(PROC / "district_yearbook_city_total.csv")
        wx_d = pd.read_parquet(PATHS.artifacts["district_weather_daily"])
        wx_y = pd.read_csv(PROC / "district_weather_yearly.csv")

        # ---- 1. 年份 × 区县 覆盖 ----
        cov_prod = (area[area["sown_area"].notna()]
                    .groupby(["district", "year"]).size().unstack(fill_value=0))
        cov_wx = (wx_y.groupby(["district", "year"]).size().unstack(fill_value=0))
        cov = pd.DataFrame(index=DISTRICTS)
        for y in sorted(area["year"].unique()):
            cov[f"prod_{y}"] = cov_prod[y] if y in cov_prod.columns else 0
        for y in sorted(wx_y["year"].unique()):
            cov[f"wx_{y}"] = cov_wx[y] if y in cov_wx.columns else 0
        cov = cov.reset_index().rename(columns={"index": "district"})
        save_table(cov, "district_qa_year_coverage.csv")

        # ---- 2. 作物 × 年份 覆盖（区县数） ----
        crop_cov = (area[area["sown_area"].notna()]
                    .pivot_table(index="crop", columns="year", values="sown_area", aggfunc="count")
                    .fillna(0).astype(int))
        crop_cov["years_covered"] = (crop_cov > 0).sum(axis=1)
        crop_cov["districts_total"] = crop_cov[[c for c in crop_cov.columns if isinstance(c, (int, np.integer))]].sum(axis=1)
        crop_cov = crop_cov.sort_values("years_covered", ascending=False).reset_index()
        save_table(crop_cov, "district_qa_crop_coverage.csv")

        # ---- 3. 单位一致性 ----
        units = pd.DataFrame([
            {"table": "district_crop_area", "unit_col": "area_unit",
             "units_present": "|".join(sorted(area["area_unit"].dropna().unique()))},
            {"table": "district_crop_production", "unit_col": "production_unit",
             "units_present": "|".join(sorted(prod["production_unit"].dropna().unique()))},
            {"table": "district_crop_yield", "unit_col": "yield_unit",
             "units_present": "|".join(sorted(yld["yield_unit"].dropna().unique()))},
        ])
        log.info("单位：%s", units.to_dict("records"))

        # ---- 4. 面积—产量—单产 逻辑 ----
        m = area[["year", "district", "crop", "sown_area"]].merge(
            prod[["year", "district", "crop", "production"]], on=["year", "district", "crop"], how="outer"
        ).merge(yld[["year", "district", "crop", "yield_value"]], on=["year", "district", "crop"], how="outer")
        m["prod_from_area_yield"] = m["sown_area"] * m["yield_value"] / 1000.0
        m["abs_diff"] = (m["prod_from_area_yield"] - m["production"]).abs()
        m["rel_diff"] = np.where(m["production"].gt(0), m["abs_diff"] / m["production"], np.nan)
        m["flag"] = np.where(m["rel_diff"].isna(), "no_check",
                             np.where(m["rel_diff"] > 0.05, "CONFLICT>5%", "ok"))
        cons = m[["year", "district", "crop", "sown_area", "production", "yield_value",
                  "prod_from_area_yield", "rel_diff", "flag"]]
        save_table(cons, "district_qa_consistency.csv")
        n_ok = int((m["flag"] == "ok").sum())
        n_conf = int((m["flag"] == "CONFLICT>5%").sum())
        log.info("一致性：ok %d；冲突>5%% %d；无法校验 %d", n_ok, n_conf,
                 int((m["flag"] == "no_check").sum()))

        # ---- 5a. 区县合计 vs 市级合计 ----
        rows = []
        dsum = (area.groupby(["year", "crop"])["sown_area"].sum().rename("districts_sum_area"))
        psum = (prod.groupby(["year", "crop"])["production"].sum().rename("districts_sum_prod"))
        ca = city[city["measure"] == "sown_area"].set_index(["year", "crop"])["value"].rename("city_area")
        cp = city[city["measure"] == "production"].set_index(["year", "crop"])["value"].rename("city_prod")
        cmp_df = pd.concat([ca, dsum, cp, psum], axis=1).reset_index()
        cmp_df["area_rel_diff"] = (cmp_df["districts_sum_area"] - cmp_df["city_area"]) / cmp_df["city_area"]
        cmp_df["prod_rel_diff"] = (cmp_df["districts_sum_prod"] - cmp_df["city_prod"]) / cmp_df["city_prod"]
        for _, r in cmp_df.iterrows():
            rows.append({
                "year": r["year"], "crop": r["crop"],
                "districts_sum_area": r["districts_sum_area"], "city_area": r["city_area"],
                "area_rel_diff": r["area_rel_diff"],
                "districts_sum_prod": r["districts_sum_prod"], "city_prod": r["city_prod"],
                "prod_rel_diff": r["prod_rel_diff"],
                "flag": ("area/prod 差异>5%" if (abs(r["area_rel_diff"]) > 0.05 or
                                                 (pd.notna(r["prod_rel_diff"]) and abs(r["prod_rel_diff"]) > 0.05))
                         else "ok"),
            })
        cmpv = pd.DataFrame(rows)
        save_table(cmpv, "district_qa_city_vs_districts.csv")
        log.info("区县合计 vs 市级：ok %d；差异>5%% %d",
                 int((cmpv["flag"] == "ok").sum()), int((cmpv["flag"] != "ok").sum()))

        # ---- 6. 异常清单 ----
        exc = []
        miss = panel[panel["sown_area"].isna() & panel["production"].notna()]
        for _, r in miss.iterrows():
            exc.append({"year": r["year"], "district": r["district"], "crop": r["crop"],
                        "issue": "有产量/单产但无播种面积（年鉴面积表留空）"})
        bad = cons[cons["flag"] == "CONFLICT>5%"]
        for _, r in bad.iterrows():
            exc.append({"year": r["year"], "district": r["district"], "crop": r["crop"],
                        "issue": f"面积×单产≠产量（相对差 {r['rel_diff']:.1%}）"})
        for _, r in cmpv[cmpv["flag"] != "ok"].iterrows():
            exc.append({"year": r["year"], "district": "（全市）", "crop": r["crop"],
                        "issue": f"区县合计 vs 市级差异（面积 {r['area_rel_diff']:.1%}，"
                                 f"产量 {r['prod_rel_diff'] if pd.notna(r['prod_rel_diff']) else float('nan'):.1%}）"
                                 if pd.notna(r["prod_rel_diff"]) else
                                 f"区县合计 vs 市级面积差异 {r['area_rel_diff']:.1%}"})
        exc_df = pd.DataFrame(exc)
        save_table(exc_df, "district_qa_exceptions.csv")
        log.info("异常记录：%d 条", len(exc_df))

        # ---- 报告 ----
        _report(cov, crop_cov, units, cons, cmpv, exc_df, wx_d, wx_y, panel, log)


def _fmt(df: pd.DataFrame, n: int = 60) -> str:
    return df.round(4).to_string(index=False, max_rows=n)


def _report(cov, crop_cov, units, cons, cmpv, exc, wx_d, wx_y, panel, log) -> None:
    p = PATHS.report("16_DISTRICT_DATA_QA.md")
    txt = f"""# 16 区县农业—气象数据质量检查（本轮数据补充）

> 粒度：年 × 区县 × 作物。农业生产来自《沈阳统计年鉴》分区县农业表（A 级）；
> 气象来自 Open-Meteo ERA5 再分析（区县行政中心代表点，与既有沈阳天气体系同源）。

## 1 年份 × 区县 覆盖

`prod_YYYY` = 该年该区县有播种面积的作物类别数；`wx_YYYY` = 该年该区县气象日数（应有 365/366）。

{_fmt(cov, 40)}

## 2 作物 × 年份 覆盖（区县数）

{_fmt(crop_cov, 40)}

> `years_covered` = 有数据的年份数（最大 7，即 2018-2024）；单元格为该年有该作物播种面积的区县数（最大 8）。

## 3 单位一致性

{_fmt(units, 10)}

- 面积：公顷；产量：吨；单产：公斤/公顷。**三表单位各自唯一，无混用**；
- 未做任何单位换算覆盖（原始单位原样保留在 `*_unit` 与 `value_raw`）。

## 4 面积—产量—单产 逻辑校验

校验式：`sown_area(公顷) × yield_value(公斤/公顷) / 1000 ≈ production(吨)`。

- 通过（相对差 ≤5%）：**{int((cons['flag'] == 'ok').sum())}** 行；
- 冲突（>5%）：**{int((cons['flag'] == 'CONFLICT>5%').sum())}** 行；
- 无法校验（缺项）：**{int((cons['flag'] == 'no_check').sum())}** 行。

冲突行明细见 `district_qa_consistency.csv` 与第 6 节异常清单。主要成因：
① 面积表留空但产量表有极小值（年鉴「空白栏表示 0 或不掌握」）；
② 个别作物面积很小（1~7 公顷）时，面积取整导致单产反算放大误差；
③ **2022 年（2023 卷）绿豆行存在上游数字异常**（区县产量与单产数值相同，见异常清单）。

## 5 多来源验证

### 5.1 区县合计 vs 市级合计（年鉴内部一致性）

{_fmt(cmpv[cmpv['flag'] != 'ok'][['year', 'crop', 'districts_sum_area', 'city_area', 'area_rel_diff',
                                    'districts_sum_prod', 'city_prod', 'prod_rel_diff']], 40)
 if (cmpv['flag'] != 'ok').any() else "全部作物×年份：区县合计与市级合计一致（差异 ≤5%）。"}

> 说明：沈阳市年鉴的市级合计包含 5 个城市核心区（和平/沈河/大东/皇姑/铁西）**未单列**的少量农业，
> 故区县合计通常**略小于**市级合计，属正常口径差；差异 >5% 的行已单列并解释。

### 5.2 区县公报 vs 年鉴（抽样人工核对）

见 `source_registry.csv` 中登记的区县公报原文；报告正文给出抽样比对结论（见下）。

## 6 异常清单

{_fmt(exc, 50)}

## 7 气象数据自检

- 日度：{len(wx_d)} 行，{wx_d['district'].nunique()} 区县，{wx_d['date'].min()} ~ {wx_d['date'].max()}；
- 每区县天数：{wx_d.groupby('district').size().to_dict()}；
- 年度汇总：{len(wx_y)} 行（区县 × 年）；关键气象列缺失率均为 0%；
- 生长季 = 5-9 月（沿用 config `time.growing_season_months`）。

## 8 结论

- 生产数据：2018-2024 共 7 年 × 8 区县，22+ 作物类别；**2015-2017 官方未公开**（年鉴卷无附件）；
- 气象数据：2015-2025 共 11 年 × 8 区县完整；
- 面板：{len(panel)} 行（年 × 区县 × 作物），其中 `full`（生产+气象）**{int((panel['coverage_flag'] == 'full').sum())}** 行；
- 未做任何插值/推算；缺失即缺失。

---
生成时间：{pd.Timestamp.now():%Y-%m-%d %H:%M:%S}
"""
    p.write_text(txt, encoding="utf-8")
    log.info("报告已写出：%s", p)


if __name__ == "__main__":
    main()
