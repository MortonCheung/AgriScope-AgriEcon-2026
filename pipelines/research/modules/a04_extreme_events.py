"""a04_extreme_events.py — A04 极端事件前后变化（六城统一）。

- 事件识别（再分析口径）：单期降水≥50mm、3 期累计≥100mm、最高温≥35℃；合并 3 期内相邻为事件簇。
- 事件响应：事件后 10 天各作物价格异常 z 的均值。
- 安慰剂判定：与随机日期窗口的分布比较，得安慰剂 p。
- 官方灾情事件（disaster_events_observed）单独列出，不与算法事件混同。
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from ..lib import contract, emit, loaders, panel, stats

MODULE = "A04"
SLUG = "extreme-events-response"
TITLE = "极端天气事件前后市场变化"
CITY_FREQ = {"chaoyang": "D", "jinzhou": "D", "dalian": "W", "shenyang": "D"}


def _detect_events(weather: pd.DataFrame, an: Dict, freq: str) -> pd.DataFrame:
    w = weather.sort_values("date").copy()
    for c in ["precipitation_sum", "temperature_2m_max"]:
        w[c] = pd.to_numeric(w[c], errors="coerce")
    p50 = float(an["events"]["precip_daily_mm"]); p3 = float(an["events"]["precip_3d_mm"])
    tmax = float(an["events"]["temp_max_c"])
    w["rain3"] = w["precipitation_sum"].rolling(3, min_periods=1).sum()
    flags = {
        "rainstorm": w["precipitation_sum"] >= p50,
        "rain_3d": w["rain3"] >= p3,
        "heat": w["temperature_2m_max"] >= tmax,
    }
    ev = []
    for name, m in flags.items():
        idx = w.index[m.fillna(False)]
        for i in idx:
            ev.append({"date": w.loc[i, "date"], "type": name,
                       "value": float(w.loc[i, "precipitation_sum"] if name != "heat"
                                      else w.loc[i, "temperature_2m_max"])})
    if not ev:
        return pd.DataFrame(columns=["date", "type", "value"])
    return pd.DataFrame(ev).sort_values("date").reset_index(drop=True)


def _clusters(events: pd.DataFrame, gap_days: int = 3) -> List[Dict]:
    if events.empty:
        return []
    e = events.sort_values("date").reset_index(drop=True)
    clusters, cur = [], [0]
    for i in range(1, len(e)):
        if (e.loc[i, "date"] - e.loc[cur[-1], "date"]).days <= gap_days:
            cur.append(i)
        else:
            clusters.append(cur); cur = [i]
    clusters.append(cur)
    out = []
    for c in clusters:
        sub = e.loc[c]
        out.append({"start": sub["date"].min(), "end": sub["date"].max(),
                    "n_days": len(sub), "types": ",".join(sorted(sub["type"].unique())),
                    "max_value": float(sub["value"].max())})
    return out


def run(city: str) -> Dict:
    if city not in CITY_FREQ:
        return emit.emit_not_supported(city=city, module=MODULE, slug=SLUG, title=TITLE,
                                       reason="无满足最小覆盖的价格序列，无法做事件前后市场变化分析。")
    cfg = loaders.load_cities()[city]
    an = loaders.load_analysis()
    win = int(an["price"]["deseason"]["doy_window"]); min_obs = int(an["price"]["min_days_weather"])
    alpha = float(an["global"]["alpha"]); freq = CITY_FREQ[city]
    weather = loaders.load_weather(city)
    veg = loaders.veg_crops()
    pool = [c for c in veg if len(loaders.load_primary_series(city, c)) >= min_obs]

    # 各作物价格异常序列（日/周索引）
    panels = {}
    for crop in pool:
        s = panel.deseasonalize_strict(loaders.load_primary_series(city, crop), "price_per_kg", "date",
                                       freq=freq, doy_window=win)
        s = s.dropna(subset=["z"]).sort_values("date").reset_index(drop=True)
        panels[crop] = s

    events = _detect_events(weather, an, freq)
    clusters = _clusters(events)
    # 事件响应（后 10 天 z 均值，跨作物中位）
    post = 10
    resp_rows, cluster_rows = [], []
    all_post = []
    for cl in clusters:
        d0 = cl["end"]
        vals = []
        for crop, s in panels.items():
            sub = s[(s["date"] > d0) & (s["date"] <= d0 + pd.Timedelta(days=post))]
            if len(sub) >= 2:
                vals.append(sub["z"].mean())
        if vals:
            cl = dict(cl)
            cl["median_z_post"] = float(np.median(vals)); cl["n_crops"] = len(vals)
            cluster_rows.append(cl); all_post.append(float(np.median(vals)))
    # 安慰剂：随机起点（非事件期）
    rng = np.random.default_rng(int(an["global"]["random_seed"]))
    any_panel = list(panels.values())[0] if panels else None
    placebo_p = np.nan
    if any_panel is not None and len(clusters) and len(any_panel) > 60:
        ev_dates = set(events["date"].dt.normalize()) if not events.empty else set()
        cand = any_panel["date"][~any_panel["date"].dt.normalize().isin(ev_dates)].to_numpy()
        if len(cand) > 30:
            boot = []
            for _ in range(int(an["global"]["n_boot"])):
                d0 = pd.Timestamp(cand[rng.integers(0, len(cand))])
                vals = []
                for crop, s in panels.items():
                    sub = s[(s["date"] > d0) & (s["date"] <= d0 + pd.Timedelta(days=post))]
                    if len(sub) >= 2:
                        vals.append(sub["z"].mean())
                if vals:
                    boot.append(float(np.median(vals)))
            boot = np.array(boot)
            obs = float(np.median(all_post))
            placebo_p = float(np.mean(np.abs(boot) >= abs(obs)))

    w = contract.StudyWriter(city, MODULE, SLUG, f"{cfg['name']}市{TITLE}")
    if clusters:
        w.save_table(pd.DataFrame(cluster_rows), f"{MODULE}_event_clusters.csv")
    w.save_table(events if not events.empty else pd.DataFrame(columns=["date", "type", "value"]),
                 f"{MODULE}_event_days.csv")
    # 官方灾情
    dis = loaders.load_disaster(city)
    if not dis.empty:
        keep = [c for c in ["event_id", "event_name", "event_type", "start_date", "end_date",
                            "crop", "official_description", "source_name"] if c in dis.columns]
        w.save_table(dis[keep], f"{MODULE}_official_disaster.csv")

    n_ev = len(clusters)
    obs_med = float(np.median(all_post)) if all_post else np.nan
    fig = _fig(cfg["name"], all_post)
    w.save_fig(fig, f"{MODULE}_post_response.png")
    metrics = {"city": city, "freq": freq, "n_event_days": int(len(events)), "n_event_clusters": n_ev,
               "n_official_disaster": int(len(dis)), "median_post_z": obs_med,
               "placebo_p": placebo_p, "alpha": alpha}
    w.dump_metrics(f"{MODULE}_summary.json", metrics)

    abstract = (
        f"本研究检验{cfg['name']}在极端天气事件后市场价格是否发生可检出变化。事件由再分析气象阈值"
        f"识别（单期降水≥{an['events']['precip_daily_mm']}mm、3 期累计≥{an['events']['precip_3d_mm']}mm、"
        f"最高温≥{an['events']['temp_max_c']}℃），并合并为事件簇；官方灾情通报单独列出、不与算法事件混同。"
        f"共识别 {len(events)} 个事件日、{n_ev} 个事件簇；事件后 10 天价格异常跨作物中位数为 "
        f"{obs_med:.3f}，安慰剂检验 p={placebo_p:.3f}。\n\n**关键词**：极端天气；事件研究；安慰剂检验；"
        f"价格异常；{cfg['name']}"
    )
    frontend_summary = (f"{cfg['name']}：事件日 {len(events)}、簇 {n_ev}；事件后中位异常 {obs_med:.3f}，"
                        f"安慰剂 p={placebo_p:.3f}。")
    data_scope = (f"### 2.1 研究对象\n{cfg['name']}主要蔬菜价格异常（{'、'.join(pool)}）。\n\n"
                  f"### 2.2 数据来源\n价格：{cfg['price_level_note']}；气象：ERA5 再分析网格；"
                  f"官方灾情：disaster_events_observed.csv。\n\n"
                  f"### 2.3 变量\n- z：严格去季节化价格异常；- 事件簇：算法识别的极端天气时段；- 事件窗：事件后 10 天（各城统一，避免日/周口径不等价）。")
    methods = (f"### 3.1 事件识别\n再分析阈值识别 + 3 期合并为簇。\n\n"
               f"### 3.2 事件响应\n事件后 10 天 z 均值，跨作物取中位。\n\n"
               f"### 3.3 安慰剂\n随机起点窗口分布比较，得安慰剂 p（{int(an['global']['n_boot'])} 次）。")
    results_text = [
        ("事件识别", f"共 {len(events)} 个事件日、{n_ev} 个事件簇；事件类型分布见 {MODULE}_event_days.csv。"),
        ("事件后响应", f"事件后 10 天价格异常跨作物中位数为 **{obs_med:.3f}**，"
                       f"安慰剂 p=**{placebo_p:.3f}**。"),
        ("官方灾情", f"官方通报灾情事件 {len(dis)} 条，单独列出，不与算法事件混同。"),
    ]
    discussion = ("若安慰剂 p 较大，说明事件后市场变化与随机日期不可分辨，不支持『极端天气事件伴随可检出的"
                  "平均市场响应』这一假设。本城样本价格口径与频率限制使检出功效有限。观察性设计不构成因果。")
    limitations = [
        f"1. **价格口径**：{cfg['price_level_note']}，非批发市场。",
        "2. **再分析网格**：ERA5 对极端值有平滑，高温事件可能被低估。",
        f"3. **事件样本少**：仅 {n_ev} 个簇，功效有限。",
        "4. **频率限制**：周度城市对事件时序定位更粗。",
        "5. **官方灾情口径不一**：仅作并列陈述，不合并。",
    ]
    conclusion = (f"{cfg['name']}：识别 {n_ev} 个极端天气事件簇；事件后价格异常中位数 {obs_med:.3f}，"
                  f"安慰剂 p={placebo_p:.3f}，"
                  f"{'与随机日期不可分辨，不支持可检出的平均市场响应。' if (np.isfinite(placebo_p) and placebo_p > alpha) else '存在一定事件响应信号，但需更大样本确认。'}")
    explorer = {
        "selectors": [{"key": "event_type", "label": "事件类型",
                       "options": sorted(events["type"].unique().tolist()) if not events.empty else []},
                      {"key": "crop", "label": "作物", "options": pool}],
        "metrics": ["n_event_days", "n_event_clusters", "median_post_z", "placebo_p"],
        "series": [{"id": "post_response", "table": f"{MODULE}_event_clusters.csv", "x": "end",
                    "y": "median_z_post"}],
        "tables": [f"{MODULE}_event_clusters.csv", f"{MODULE}_event_days.csv"],
        "figures": [f"{MODULE}_post_response.png"], "sources": [],
        "methodology": methods, "limitations": limitations,
    }
    return emit.emit_study(
        city=city, module=MODULE, slug=SLUG, title=f"{cfg['name']}市{TITLE}",
        abstract=abstract, frontend_summary=frontend_summary,
        keywords=["极端天气", "事件研究", "安慰剂检验", "价格异常", cfg["name"]],
        research_questions=[f"极端天气事件后{cfg['name']}市场价格是否发生可检出变化？"],
        data_scope=data_scope, methods=methods, results=results_text, discussion=discussion,
        limitations=limitations, conclusion=conclusion, explorer=explorer,
        tables=[f"{MODULE}_event_clusters.csv", f"{MODULE}_event_days.csv"],
        figures=[f"{MODULE}_post_response.png"],
        claims=[{"claim_id": f"{city}-A04-C1", "study_id": "A04", "city": cfg["name"],
                 "claim_text": f"事件后价格异常中位 {obs_med:.3f}，安慰剂 p={placebo_p:.3f}",
                 "claim_type": "inferential", "table_id": f"{MODULE}_event_clusters.csv",
                 "estimate": obs_med, "p_adjusted": placebo_p, "sample_size": n_ev,
                 "status": "NOT_SUPPORTED" if (np.isfinite(placebo_p) and placebo_p > alpha) else "PARTIAL"}])


def _fig(city_name, all_post):
    from ..lib.plotting import setup_plt, C_MAIN
    plt = setup_plt()
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    if all_post:
        ax.hist(all_post, bins=min(12, max(3, len(all_post))), color=C_MAIN)
        ax.axvline(float(np.median(all_post)), color="red", lw=1.2, label="事件后中位")
        ax.legend()
    ax.set_xlabel("事件后 10 天价格异常（中位，单位=SD）"); ax.set_ylabel("事件簇数")
    ax.set_title(f"{city_name}市 事件后价格异常分布")
    return fig