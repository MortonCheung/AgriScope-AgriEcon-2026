#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step8-11：由 03_clean 生成 04_marts 数据集。
- REAL_WORLD_TIMELINE_2026.csv   统一时间轴（天气→预警→降雨→河道→积水→物候→受灾→响应→排涝→农技→恢复）
- corn_annual_baseline.csv       沈北玉米年度生产基线（含趋势/年际/异常）
- rainfall_event_features.csv    暴雨事件特征（多时间尺度降水量与雨强）
"""
import os

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(BASE, "03_clean")
MARTS = os.path.join(BASE, "04_marts")
os.makedirs(MARTS, exist_ok=True)

EVENT_START = pd.Timestamp("2026-07-12")
EVENT_PEAK = pd.Timestamp("2026-07-13")


# ---------------------------------------------------------------- 暴雨特征
def build_rainfall_features():
    h = pd.read_parquet(os.path.join(CLEAN, "weather", "pnb_hourly.parquet"))
    h = h.set_index("time").sort_index()
    pr = h["precipitation"].astype(float)

    daily = pr.resample("D").sum().rename("precip_mm")
    df = daily.to_frame()
    df["precip_3d"] = df["precip_mm"].rolling(3, min_periods=1).sum()
    df["precip_7d"] = df["precip_mm"].rolling(7, min_periods=1).sum()
    df["precip_14d"] = df["precip_mm"].rolling(14, min_periods=1).sum()
    # 逐日最大滑动雨强
    for w, name in [(1, "max_1h"), (3, "max_3h"), (6, "max_6h"), (24, "max_24h")]:
        df[name] = pr.rolling(w, min_periods=1).sum().resample("D").max()
    # 前一日累计（前期湿润）
    df["precip_prev_1d"] = df["precip_mm"].shift(1)
    df["precip_prev_7d"] = df["precip_mm"].shift(1).rolling(7, min_periods=1).sum()
    df["precip_prev_14d"] = df["precip_mm"].shift(1).rolling(14, min_periods=1).sum()
    df["rain_day"] = (df["precip_mm"] >= 0.1).astype(int)
    df["heavy_rain_50"] = (df["precip_mm"] >= 50).astype(int)
    df["rainstorm_25"] = (df["precip_mm"] >= 25).astype(int)
    df = df.reset_index().rename(columns={"time": "date"})
    df["source_id"] = "SRC-OM-ERA5-HOURLY"
    df["data_nature"] = "reanalysis_era5_gridcell"

    # 只导出研究窗口
    win = df[(df["date"] >= "2026-06-15") & (df["date"] <= "2026-08-15")].copy()
    win.to_csv(os.path.join(MARTS, "rainfall_event_features.csv"), index=False, encoding="utf-8-sig")

    # 事件汇总
    full = df.copy()
    ev = full[(full["date"] >= EVENT_START) & (full["date"] <= pd.Timestamp("2026-07-15"))]
    d13 = full[full["date"] == pd.Timestamp("2026-07-13")].iloc[0]
    imax1h = full["max_1h"].idxmax()
    summary = {
        "event_peak_day": "2026-07-13",
        "event_2day_precip_0713_0714_mm": float(
            full.loc[full["date"].isin([pd.Timestamp("2026-07-13"), pd.Timestamp("2026-07-14")]),
                     "precip_mm"].sum()),
        "jul13_precip_mm": float(d13["precip_mm"]),
        "jul14_precip_mm": float(full.loc[full["date"] == pd.Timestamp("2026-07-14"), "precip_mm"].iloc[0]),
        "event_max_1h_mm": float(ev["max_1h"].max()),
        "event_max_3h_mm": float(ev["max_3h"].max()),
        "event_max_6h_mm": float(ev["max_6h"].max()),
        "event_max_24h_mm": float(ev["max_24h"].max()),
        "prev7d_before_0713_mm": float(d13["precip_prev_7d"]),
        "prev14d_before_0713_mm": float(d13["precip_prev_14d"]),
        "series_alltime_max_1h_mm": float(full["max_1h"].max()),
        "series_alltime_max_1h_date": str(full.loc[imax1h, "date"].date()),
        "series_max_daily_mm": float(full["precip_mm"].max()),
        "series_max_daily_date": str(full.loc[full["precip_mm"].idxmax(), "date"].date()),
    }
    pd.Series(summary).to_frame("value").to_csv(
        os.path.join(MARTS, "rainfall_event_summary.csv"), encoding="utf-8-sig")
    print("[marts] rainfall_event_features rows=", len(win), "| summary:", summary)
    return full


# ---------------------------------------------------------------- 玉米基线
def build_corn_baseline():
    c = pd.read_csv(os.path.join(CLEAN, "agriculture", "corn_annual_pnb.csv"))
    c = c.sort_values("year").reset_index(drop=True)
    c["corn_area_kha"] = c["corn_area_ha"] / 1000.0
    c["corn_production_wan_t"] = c["corn_production_t"] / 1e4
    c["yoy_yield_pct"] = c["corn_yield_kg_ha"].pct_change() * 100
    c["yoy_area_pct"] = c["corn_area_ha"].pct_change() * 100
    c["yoy_prod_pct"] = c["corn_production_t"].pct_change() * 100
    # 线性趋势（2018-2025）与去趋势异常
    sub = c.dropna(subset=["corn_yield_kg_ha"])
    if len(sub) >= 3:
        k, b = np.polyfit(sub["year"], sub["corn_yield_kg_ha"], 1)
        c["yield_trend_kg_ha"] = k * c["year"] + b
        c["yield_detrend_kg_ha"] = c["corn_yield_kg_ha"] - c["yield_trend_kg_ha"]
        c["yield_detrend_pct"] = c["yield_detrend_kg_ha"] / c["yield_trend_kg_ha"] * 100
        c["yield_trend_slope_kg_ha_per_yr"] = k
    c["yield_rank_desc"] = c["corn_yield_kg_ha"].rank(ascending=False, method="min")
    c.to_csv(os.path.join(MARTS, "corn_annual_baseline.csv"), index=False, encoding="utf-8-sig")
    print("[marts] corn_annual_baseline rows=", len(c))


# ---------------------------------------------------------------- 现实时间轴
def build_timeline(full_feat):
    rows = []

    def add(dt, layer, event, detail, value=None, unit=None, ev="official", src="", conf="high"):
        rows.append(dict(datetime=dt, layer=layer, event=event, detail=detail,
                         value=value, unit=unit, evidence_type=ev, source_id=src, confidence=conf))

    # --- 天气（逐小时再分析）
    f = full_feat[(full_feat["date"] >= "2026-07-01") & (full_feat["date"] <= "2026-07-26")]
    for _, r in f.iterrows():
        add(str(r["date"].date()), "天气(日降水/再分析)", "日降水量",
            f"ERA5网格点日降水 {r['precip_mm']:.1f}mm；前7日累计 {r['precip_prev_7d']:.1f}mm；"
            f"日最大1h {r['max_1h']:.1f}mm",
            round(float(r["precip_mm"]), 1), "mm", "reanalysis", "SRC-OM-ERA5-HOURLY", "medium")

    # --- 预警/响应
    add("2026-07-12T20:00", "气象预警", "强降雨过程开始（官方）",
        "受台风巴威外围云系+东北冷涡+副高影响，7-12 20时起全省强降雨持续52小时", None, None,
        "官方专报", "SRC-LN-MET-2026-0716", "high")
    add("2026-07-13T09:10", "政府响应", "沈阳防汛红色预警/最高一级响应",
        "市防指发布防汛红色预警，全市防汛应急响应升至最高一级；13部门联勤指挥", None, None,
        "官方", "SRC-SY-GOV-2026-0714", "high")
    add("2026-07-14", "政府响应", "继续执行紧急避险措施",
        "全市中小学/幼儿园停课、工地停工、景区夜市停业、机关事业单位居家办公", None, None,
        "官方", "SRC-SY-GOV-2026-0714", "high")

    # --- 降雨发展（官方口径）
    add("2026-07-13", "降雨发展", "13日0-17时全市雨情",
        "全地区平均降水129.5mm；城区平均234.7mm；浑南/于洪/辽中部分点位小时雨强超70mm", 129.5, "mm",
        "官方", "SRC-SY-GOV-2026-0714", "high")
    add("2026-07-13T00:00", "降雨发展", "沈阳城区13日0时-14日16时累计346.8mm",
        "达特大暴雨量级；和平区工农桥6h最大291.4mm、12h最大332.6mm，均为1951年以来最高值", 346.8, "mm",
        "官方专报", "SRC-LN-MET-2026-0716", "high")
    add("2026-07-12T20:00", "降雨发展", "沈北新区国家站52h累计超常年7月总量",
        "沈阳、苏家屯、沈北新区等11个国家站52小时累计降雨量超过常年平均7月降雨总量", None, None,
        "官方专报", "SRC-LN-MET-2026-0716", "high")
    add("2026-08-24", "降雨发展", "沈北兴隆台街道办最大小时雨强97.1mm（对照）",
        "8月24日6-16时全省最大小时降雨量出现在沈北兴隆台街道办", 97.1, "mm/h",
        "官方", "SRC-LN-SLT-QKB", "high")

    # --- 河道/排水
    add("2026-07-13", "河道/排水", "蒲河1957年以来第一大洪水",
        "蒲河水位暴涨；浑河1951年以来第二大洪水；棋盘山水库建库以来首次超设计水位", None, None,
        "官方", "SRC-SY-GOV-2026-0714", "high")
    add("2026-07-14", "河道/排水", "蒲河主干低空监测",
        "无人机对蒲河主干全线33.2公里动态监测，12架次巡航，道路积水点9处", 33.2, "km",
        "官方", "SRC-SY-GOV-2026-0715-PUHE", "high")

    # --- 农田积水/受灾
    add("2026-07-14T00:00", "农田积水", "兴隆台街道万亩农田凌晨受淹",
        "7月14日凌晨兴隆台街道万亩农田受淹；101国道沿线高标准农田涉及大营子/孟家台/石佛一/石佛二等村",
        1.0, "万亩", "官方综述", "SRC-LN-GOV-2026-0717", "medium")
    add("2026-07-14", "农田积水", "新城子街道八间房村内涝",
        "排水站南侧水田区积水最深超1米，8000余亩农田受淹，水稻临抽穗、玉米处生长关键期",
        8000, "亩", "权威媒体", "SRC-SYD-2026-0814", "medium")
    add("2026-07-15", "农业受灾", "省级灾情统计（全省口径）",
        "截至7-15全省农作物受影响面积约290万亩；沟渠疏浚2035千米；排空农田积水53.27万亩",
        290, "万亩", "官方", "SRC-LN-GOV-2026-0717", "high")

    # --- 人员转移（沈北）
    add("2026-07-13T00:00", "政府响应", "马刚街道群众转移安置",
        "全街235户423名涉险群众全部安全妥善安置", 423, "人", "官方", "SRC-NSY-GOV-2026-0715", "high")
    add("2026-07-14", "政府响应", "虎石台街道撤离",
        "累计撤离受灾群众50余名；帮扶老弱病残孕120人次；古城宜家小区内涝疏散60余人", 50, "余人",
        "官方", "SRC-NSY-GOV-2026-0714", "high")

    # --- 排涝干预
    add("2026-07-14", "排涝措施", "八间房村启动排涝（村-区对接）",
        "7-14村支书对接区农业农村局紧急协调排水设备", None, None, "权威媒体", "SRC-SYD-2026-0814", "medium")
    add("2026-07-15", "排涝措施", "八间房村增援大功率排涝设备",
        "两台大功率泵车+一台50泵+三组8寸管+一台应急排水车到位；共12台8寸泵同时作业，排入左小河→辽河",
        12, "台", "权威媒体", "SRC-SYD-2026-0814", "medium")
    add("2026-07-15", "排涝措施", "兴隆台街道新民村清障疏渠抢排积水",
        "多部门联动清障疏渠、抢排积水（省级通报明确记载的时间锚点）", None, None,
        "官方", "SRC-LN-GOV-2026-0717", "high")
    add("2026-07-18", "排涝措施", "八间房村田间积水基本排净",
        "7-18下午田间积水基本排净；7-25全程紧盯后续安全与生产恢复", None, None,
        "权威媒体", "SRC-SYD-2026-0814", "medium")

    # --- 农技措施/恢复
    add("2026-07-17", "农业技术措施", "兴隆台街道3村雨后巡查",
        "市乡村振兴中心核查：排水系统通畅、无积水洼地、无涝灾隐患；玉米水稻长势均匀、苗情稳健；未发现高发病虫害",
        None, None, "官方", "SRC-SY-RURAL-2026-0721", "high")
    add("2026-07-25", "灾情恢复", "排涝区生产恢复跟踪",
        "八间房村持续跟踪后续安全及生产恢复至7-25", None, None, "权威媒体", "SRC-SYD-2026-0814", "medium")
    add("2026-09-02", "灾情恢复", "辉山街道救灾款物使用",
        "红十字救灾捐款52749元拨付用于受灾安置", 52749, "元", "官方", "SRC-NSY-GOV-2026-0902", "high")

    # --- 物候标注
    ph = pd.read_csv(os.path.join(CLEAN, "phenology", "corn_phenology_2026.csv"))
    for _, r in ph.iterrows():
        add(r["start"], "玉米物候", f"{r['stage']}（区间 {r['start']}~{r['end']}）",
            r["evidence"], None, None, "文献/官方技术", r["source_id"], "medium")

    df = pd.DataFrame(rows)
    df = df.sort_values("datetime").reset_index(drop=True)
    df.to_csv(os.path.join(MARTS, "REAL_WORLD_TIMELINE_2026.csv"), index=False, encoding="utf-8-sig")
    print("[marts] REAL_WORLD_TIMELINE_2026 rows=", len(df))


if __name__ == "__main__":
    full = build_rainfall_features()
    build_corn_baseline()
    build_timeline(full)
    print("=== build_marts done ===")
