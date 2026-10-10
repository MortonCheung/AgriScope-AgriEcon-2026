#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step8：由 02_raw 生成 03_clean 标准数据层。
原则：不插值、不补造、不省代市；每条记录带 source_id 与质量等级。
"""
import json
import os

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "02_raw")
CLEAN = os.path.join(BASE, "03_clean")
LOG = os.path.join(BASE, "logs", "build_clean.log")
os.makedirs(os.path.dirname(LOG), exist_ok=True)
_logf = open(LOG, "a", encoding="utf-8")


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    _logf.write(s + "\n")


# ---------------------------------------------------------------- 农业
def build_agriculture():
    out_dir = os.path.join(CLEAN, "agriculture")
    os.makedirs(out_dir, exist_ok=True)

    # 来源A：沈阳统计年鉴 分区县（2018-2024，A级）
    yr = os.path.join(RAW, "agriculture")
    a = pd.read_csv(os.path.join(yr, "shenyang_yearbook_district_crop_area.csv"))
    p = pd.read_csv(os.path.join(yr, "shenyang_yearbook_district_crop_production.csv"))
    y = pd.read_csv(os.path.join(yr, "shenyang_yearbook_district_crop_yield.csv"))
    a = a[(a.district == "沈北新区") & (a.crop == "玉米")][["year", "sown_area", "area_unit"]]
    p = p[(p.district == "沈北新区") & (p.crop == "玉米")][["year", "production", "production_unit"]]
    y = y[(y.district == "沈北新区") & (y.crop == "玉米")][["year", "yield_value", "yield_unit", "yield_method"]]
    m = a.merge(p, on="year", how="outer").merge(y, on="year", how="outer")
    m = m.rename(columns={"sown_area": "corn_area_ha", "production": "corn_production_t",
                          "yield_value": "corn_yield_kg_ha"})
    m["area_src"] = "SRC-SY-YB-DISTRICT"
    m["prod_src"] = "SRC-SY-YB-DISTRICT"
    m["yield_src"] = "SRC-SY-YB-DISTRICT"
    m["yield_method"] = m["yield_method"].fillna("official_yearbook")
    m["quality"] = "A"
    m["scope"] = "沈北新区（全区）"

    # 来源B：沈北新区国民经济统计资料（区级官方，B级；2021/2022/2024/2025）
    # 数值来自扫描件目视转录，单位换算：玉米单产 kg/ha = 公斤/亩 × 15；总产 t = 万吨 × 10000
    pnb = pd.DataFrame([
        # year, area_ha, prod_t, yield_kg_per_mu(原始), 来源卷
        (2021, 14898, 128000, 576, "2022卷"),
        (2022, 14912, 130000, 573, "2022卷"),
        (2024, 15301, 128000, 559, "2025卷"),
        (2025, 15628, 135000, 575, "2025卷"),
    ], columns=["year", "area_ha", "prod_t", "yield_mu", "vol"])
    pnb["yield_kg_ha"] = (pnb["yield_mu"] * 15).astype(float)

    # 合并：以市级年鉴为主序列，区级年鉴用于交叉验证与 2025 补齐
    base = m[["year", "corn_area_ha", "corn_production_t", "corn_yield_kg_ha",
              "area_src", "prod_src", "yield_src", "yield_method", "quality", "scope"]].copy()
    base["pnb_yb_area_ha"] = np.nan
    base["pnb_yb_production_t"] = np.nan
    base["pnb_yb_yield_kg_ha"] = np.nan
    base["pnb_yb_vol"] = None
    for _, r in pnb.iterrows():
        yy = int(r["year"])
        if yy in base["year"].values:
            i = base.index[base["year"] == yy][0]
            base.loc[i, ["pnb_yb_area_ha", "pnb_yb_production_t", "pnb_yb_yield_kg_ha", "pnb_yb_vol"]] = [
                r["area_ha"], r["prod_t"], r["yield_kg_ha"], r["vol"]]
        else:
            base.loc[len(base)] = {
                "year": yy, "corn_area_ha": np.nan, "corn_production_t": np.nan,
                "corn_yield_kg_ha": np.nan, "area_src": "NOT_AVAILABLE",
                "prod_src": "NOT_AVAILABLE", "yield_src": "NOT_AVAILABLE",
                "yield_method": "not_available", "quality": "A",
                "scope": "沈北新区（全区）",
                "pnb_yb_area_ha": r["area_ha"], "pnb_yb_production_t": r["prod_t"],
                "pnb_yb_yield_kg_ha": r["yield_kg_ha"], "pnb_yb_vol": r["vol"]}
    # 2025：市级年鉴尚未发布，采用区级年鉴值作为主值（标注来源）
    i25 = base.index[base["year"] == 2025]
    for i in i25:
        base.loc[i, ["corn_area_ha", "corn_production_t", "corn_yield_kg_ha"]] = [
            base.loc[i, "pnb_yb_area_ha"], base.loc[i, "pnb_yb_production_t"],
            base.loc[i, "pnb_yb_yield_kg_ha"]]
        base.loc[i, ["area_src", "prod_src", "yield_src"]] = ["SRC-PNB-YB-2025"] * 3
        base.loc[i, "yield_method"] = "official_district_yearbook"
    base = base.sort_values("year").reset_index(drop=True)
    base.to_csv(os.path.join(out_dir, "corn_annual_pnb.csv"), index=False, encoding="utf-8-sig")
    log(f"[agriculture] corn_annual_pnb.csv rows={len(base)} years={base.year.min()}-{base.year.max()}")

    # 沈北粮食/水稻/大豆 辅助序列（区级年鉴，2021/2022/2024/2025）
    grain = pd.DataFrame([
        (2021, 29635, 14094, 468, 240000, 107000, 128000, 2000, 536, 506, 576, 232),
        (2022, 29803, 14136, 600, 240000, 110000, 130000, 2000, 537, 627.5, 573, 182),
        (2024, 29958, 13888, 661, 240000, 107000, 128000, 2000, 528.0, 514, 559, 152),
        (2025, 30303, 13927, 661, 240000, 110000, 135000, 2000, 534.4, 507.8, 575, 154),
    ], columns=["year", "grain_area_ha", "rice_area_ha", "soy_area_ha", "grain_prod_t",
                "rice_prod_t", "corn_prod_t", "soy_prod_t",
                "grain_yield_mu", "rice_yield_mu", "corn_yield_mu", "soy_yield_mu"])
    grain["source_id"] = "SRC-PNB-YB-2025/2022"
    grain["quality"] = "B（扫描件目视转录）"
    grain.to_csv(os.path.join(out_dir, "pnb_grain_rice_soy.csv"), index=False, encoding="utf-8-sig")
    log(f"[agriculture] pnb_grain_rice_soy.csv rows={len(grain)}")


# ---------------------------------------------------------------- 天气
def _read_openmeteo_daily(path, variables):
    d = json.load(open(path, encoding="utf-8"))
    d = d["daily"]
    df = pd.DataFrame(d)
    df["time"] = pd.to_datetime(df["time"])
    return df


def build_weather():
    out_dir = os.path.join(CLEAN, "weather")
    os.makedirs(out_dir, exist_ok=True)

    # 逐小时（本研究新采集）
    frames = []
    for y in range(2015, 2027):
        fp = os.path.join(RAW, "weather", f"openmeteo_hourly_沈北新区_{y}.json")
        d = json.load(open(fp, encoding="utf-8"))
        frames.append(pd.DataFrame(d["hourly"]))
    h = pd.concat(frames, ignore_index=True)
    h["time"] = pd.to_datetime(h["time"])
    h = h.drop_duplicates("time").sort_values("time").reset_index(drop=True)
    h.to_parquet(os.path.join(out_dir, "pnb_hourly.parquet"), index=False)
    log(f"[weather] pnb_hourly rows={len(h)} {h.time.min()}..{h.time.max()} "
        f"missing_precip={int(h.precipitation.isna().sum())}")

    # 日值：既有 AgriScope（基线1991-2020 + 现状2021-2026）
    AGRI = os.path.join(BASE, "..", "..", "..", "..", "data/raw", "weather")
    base = _read_openmeteo_daily(os.path.join(AGRI, "openmeteo_沈北新区_baseline_1991-01-01_2020-12-31.json"), None)
    cur = _read_openmeteo_daily(os.path.join(AGRI, "openmeteo_沈北新区_current_2021-01-01_2026-09-14.json"), None)
    daily = pd.concat([base, cur], ignore_index=True).drop_duplicates("time").sort_values("time").reset_index(drop=True)
    daily = daily.rename(columns={"time": "date"})
    daily["source_id"] = "SRC-OM-ERA5-DAILY"
    daily["data_nature"] = "reanalysis_era5"
    daily.to_parquet(os.path.join(out_dir, "pnb_daily_1991_2026.parquet"), index=False)
    log(f"[weather] pnb_daily rows={len(daily)} {daily.date.min().date()}..{daily.date.max().date()}")

    # 逐小时聚合到日，用于与日值交叉校验
    hh = h.set_index("time")
    agg = pd.DataFrame({
        "date": hh.resample("D").size().index,
        "precip_hourly_sum": hh.precipitation.resample("D").sum().values,
        "temp_mean_hourly": hh.temperature_2m.resample("D").mean().values,
    })
    agg.to_csv(os.path.join(out_dir, "pnb_daily_from_hourly_2015_2026.csv"), index=False, encoding="utf-8-sig")
    log(f"[weather] pnb_daily_from_hourly rows={len(agg)}")


# ---------------------------------------------------------------- 灾害
def build_disaster():
    out_dir = os.path.join(CLEAN, "disaster")
    os.makedirs(out_dir, exist_ok=True)
    rows = [
        # event_id, datetime_start, datetime_end, location, location_level, event_type, description,
        # affected_crop, affected_area_mu, waterlogging, damage_level, source_id, evidence_type, confidence, notes
        ("DIS-PNB-2026-001", "2026-07-12", "2026-07-15", "辽宁省（含沈阳）", "province",
         "持续强降雨/洪涝", "台风巴威外围云系+东北冷涡+副高，7-12 20时至7-15 0时持续52小时；"
         "全省平均109.2mm；沈阳城区13日0时-14日16时346.8mm（特大暴雨）；沈北新区等11个国家站52h累计超常年7月总量",
         "玉米、水稻（正值生长关键期）", None, "低洼农田渍涝", "特大暴雨（历史极值）",
         "SRC-LN-MET-2026-0716", "官方专报", "high", "省级/市级口径，非沈北单列"),
        ("DIS-PNB-2026-002", "2026-07-13", "2026-07-14", "沈阳市沈北新区兴隆台街道", "township",
         "农田受淹", "据官方灾情综述：7月14日凌晨兴隆台街道万亩农田受淹；101国道沿线高标准农田"
         "（大营子/孟家台/石佛一/石佛二等村）涉及；蒲河水位暴涨",
         "玉米、水稻", 10000, "万亩农田受淹", "较重", "SRC-LN-GOV-2026-0717", "官方综述转述", "medium",
         "面积口径为‘万亩’的定性量级，非精确统计"),
        ("DIS-PNB-2026-003", "2026-07-12", "2026-07-14", "沈阳市沈北新区新城子街道八间房村排水站南侧水田区", "village",
         "农田内涝", "积水最深处超过1米，8000余亩农田受淹；即将抽穗的水稻与生长关键期玉米面临灭顶之灾",
         "水稻、玉米", 8000, "最深>1米", "重", "SRC-SYD-2026-0814", "权威媒体", "medium",
         "‘8000余亩’为媒体量级描述"),
        ("DIS-PNB-2026-004", "2026-07-13", "2026-07-15", "沈阳市沈北新区马刚街道", "township",
         "涉险群众转移", "全街235户423名涉险群众全部安全妥善安置", None, None, "山洪/涉险", "转移",
         "SRC-NSY-GOV-2026-0715", "官方", "high", "人员指标，非农业面积"),
        ("DIS-PNB-2026-005", "2026-07-13", "2026-07-14", "沈阳市沈北新区虎石台街道", "township",
         "内涝/群众转移", "累计撤离受灾群众50余名；帮扶老弱病残孕120人次；古城宜家小区内涝疏散60余人",
         None, None, "小区/道路内涝", "转移", "SRC-NSY-GOV-2026-0714", "官方", "high", "人员指标"),
        ("DIS-PNB-2026-006", "2026-07-14", "2026-07-15", "沈阳市沈北新区蒲河主干", "district",
         "河道洪水/积水", "蒲河1957年以来第一大洪水；无人机对蒲河主干全线33.2公里空中动态监测；道路积水点9处",
         None, None, "道路积水9处", "重（河道）", "SRC-SY-GOV-2026-0715-PUHE", "官方", "high",
         "河道与道路指标"),
        ("DIS-PNB-2026-007", "2026-08-24", "2026-08-24", "沈阳市沈北新区兴隆台街道办", "township",
         "短时强降水", "8月24日6-16时最大小时降雨量97.1mm出现在沈北新区兴隆台街道办（省水利厅汛情快报）",
         None, None, "短时强降水", "强", "SRC-LN-SLT-QKB", "官方", "high",
         "属2026年8月事件，非7月主事件；用于对照沈北局地极端雨强"),
    ]
    cols = ["event_id", "datetime_start", "datetime_end", "location", "location_level", "event_type",
            "description", "affected_crop", "affected_area_mu", "waterlogging", "damage_level",
            "source_id", "evidence_type", "confidence", "notes"]
    df = pd.DataFrame(rows, columns=cols)
    df.to_csv(os.path.join(out_dir, "disaster_event_timeline.csv"), index=False, encoding="utf-8-sig")
    log(f"[disaster] disaster_event_timeline.csv rows={len(df)}")


# ---------------------------------------------------------------- 干预
def build_intervention():
    out_dir = os.path.join(CLEAN, "intervention")
    os.makedirs(out_dir, exist_ok=True)
    rows = [
        # intervention_id, datetime_start, datetime_end, location, location_level, action_type,
        # description, intensity, observed_2026, source_id, evidence_type, confidence, notes
        ("INT-PNB-2026-001", "2026-07-13T09:10", "2026-07-14", "沈阳市（含沈北）", "city",
         "应急响应/预警", "市防指9时10分发布防汛红色预警，应急响应升至最高一级；13-14日停课停工停运停业+居家办公",
         "最高一级响应", "yes", "SRC-SY-GOV-2026-0714", "官方", "high",
         "预警—行动时间锚点；13日9:10发令"),
        ("INT-PNB-2026-002", "2026-07-13", "2026-07-15", "沈阳市沈北新区马刚街道", "township",
         "群众转移安置", "划分劝导转移/安置转运/后勤保障组，逐户‘一对一’方案，紧急对接两处酒店分流安置",
         "235户423人", "yes", "SRC-NSY-GOV-2026-0715", "官方", "high", ""),
        ("INT-PNB-2026-003", "2026-07-13", "2026-07-14", "沈阳市沈北新区虎石台街道", "township",
         "人员撤离/安置", "撤离受灾群众；帮扶转运老弱病残孕", "撤离50余人/帮扶120人次", "yes",
         "SRC-NSY-GOV-2026-0714", "官方", "high", ""),
        ("INT-PNB-2026-004", "2026-07-14", "2026-07-18", "沈阳市沈北新区新城子街道八间房村/北四家子村", "village",
         "排涝（泵站+移动泵车）", "7-14村支书对接区农业农村局协调排水设备；7-15增援两台大功率泵车+一台50泵+三组8寸管"
         "（排水能力=7台8寸泵）及一台应急排水车；共12台8寸泵同时作业，排入左小河→辽河；7-18下午田间积水基本排净",
         "12台8寸泵；8000余亩", "yes", "SRC-SYD-2026-0814", "权威媒体", "medium",
         "含清晰的干预起止时间与设备强度；最重要的排涝干预案例"),
        ("INT-PNB-2026-005", "2026-07-15", "2026-07-17", "沈阳市沈北新区兴隆台街道新民村", "village",
         "清障疏渠/抢排积水", "多部门联动清障疏渠、抢排积水", "定性", "yes",
         "SRC-LN-GOV-2026-0717", "官方", "high", "省级通报明确记载的干预锚点"),
        ("INT-PNB-2026-006", "2026-07-14", "2026-07-15", "沈阳市沈北新区蒲河主干", "district",
         "低空监测/巡查", "无人机对蒲河主干全线33.2公里无死角空中动态监测，12架次巡航", "12架次/33.2km",
         "yes", "SRC-SY-GOV-2026-0715-PUHE", "官方", "high", "监测型干预，非直接排涝"),
        ("INT-PNB-2026-007", "2026-07-17", "2026-07-17", "沈阳市沈北新区兴隆台街道3村", "village",
         "农技指导/灾情排查", "市乡村振兴中心下沉兴隆台街道3个行政村，核查田间积水、涝灾病害；"
         "结论：排水系统通畅、无积水、作物长势优良、未发现高发病虫害",
         "3村/3点位", "yes", "SRC-SY-RURAL-2026-0721", "官方", "high",
         "雨后恢复结果：干预后7-17已无田间积水"),
        ("INT-PNB-2026-008", "2026-09-02", "2026-09-02", "沈阳市沈北新区辉山街道", "district",
         "救灾款物", "红十字救灾捐款52749元拨付用于受灾安置", "52749元", "yes",
         "SRC-NSY-GOV-2026-0902", "官方", "high", "灾后救助，非排涝"),
    ]
    cols = ["intervention_id", "datetime_start", "datetime_end", "location", "location_level",
            "action_type", "description", "intensity", "observed_2026", "source_id",
            "evidence_type", "confidence", "notes"]
    df = pd.DataFrame(rows, columns=cols)
    df.to_csv(os.path.join(out_dir, "intervention_timeline.csv"), index=False, encoding="utf-8-sig")
    log(f"[intervention] intervention_timeline.csv rows={len(df)}")


# ---------------------------------------------------------------- 物候
def build_phenology():
    out_dir = os.path.join(CLEAN, "phenology")
    os.makedirs(out_dir, exist_ok=True)
    rows = [
        # stage, start, end, confidence, evidence, source_id
        ("播种期(sowing)", "2026-04-20", "2026-05-10", "中（官方适播期区间）",
         "沈阳市2026年技术指导意见：玉米适播期5-10cm地温稳定8-10℃，我市一般4月下旬至5月上旬；"
         "沈阳春耕计划4月下旬开犁、5月中旬播完", "SRC-SY-NYJ-2026-JSZ"),
        ("出苗期(emergence)", "2026-05-01", "2026-05-20", "低（推算）", "播种后约7-15天出苗（农学常识）", "SRC-CROP-CALENDAR"),
        ("拔节期(jointing)", "2026-06-01", "2026-06-25", "低（区域经验）", "辽宁春玉米拔节多在6月", "SRC-CROP-CALENDAR"),
        ("大喇叭口期", "2026-06-25", "2026-07-10", "低（区域经验）", "抽雄前10-15天", "SRC-CROP-CALENDAR"),
        ("抽雄期(tasseling)", "2026-07-10", "2026-07-25", "中（区域粒度：7月）",
         "AgriScope作物日历：辽宁玉米flowering/抽雄期=7月；官方技术资料称7月玉米‘正值生长关键期’", "SRC-CROP-CALENDAR"),
        ("吐丝期(silking)", "2026-07-18", "2026-08-03", "中（区域粒度：7月-8月）",
         "AgriScope作物日历：pollination/吐丝期=7月-8月；需水临界期", "SRC-CROP-CALENDAR"),
        ("灌浆期(grain filling)", "2026-08-05", "2026-09-05", "中（区域粒度：8月-9月）",
         "AgriScope作物日历：grain_filling=8月-9月", "SRC-CROP-CALENDAR"),
        ("成熟期(maturity)", "2026-09-20", "2026-10-05", "中（区域粒度：9月下旬-10月上旬）",
         "AgriScope作物日历：maturity=9月；harvest=9月下旬-10月上旬", "SRC-CROP-CALENDAR"),
    ]
    cols = ["stage", "start", "end", "confidence", "evidence", "source_id"]
    df = pd.DataFrame(rows, columns=cols)
    df.to_csv(os.path.join(out_dir, "corn_phenology_2026.csv"), index=False, encoding="utf-8-sig")
    log(f"[phenology] corn_phenology_2026.csv rows={len(df)}")


if __name__ == "__main__":
    build_agriculture()
    build_weather()
    build_disaster()
    build_intervention()
    build_phenology()
    log("=== build_clean done ===")
