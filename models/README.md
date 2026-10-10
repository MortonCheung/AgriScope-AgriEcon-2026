# AgriScope Decision Engine v1（穹衡 · 种植决策引擎）

> 面向智慧农业的多源数据驱动种植决策与市场风险分析平台 —— **决策引擎建模工作区**。
> 本工作区不修改 AgriScope 前端，不覆盖 canonical 数据；所有输入以只读快照冻结。

## 快速开始

```bash
cd "/Users/morton_cheung/Desktop/比赛/大数据分析"

# 一键重建全流程（数据快照 → Dataset → 模型 → 区间 → 风险 → 回放 → 报告 → 测试）
python3 decision_engine/scripts/run_all.py

# 附：Optuna 调参 / 全部开源 benchmark（较慢）
python3 decision_engine/scripts/run_all.py --with-tuning --with-oss

# 直接调用 Decision Engine
python3 - <<'PY'
import sys; sys.path.insert(0, "AgriScope/pipelines/modeling/src")
from decision_engine.engine.engine import DecisionEngine
eng = DecisionEngine()
r = eng.evaluate_plan({
    "city": "沈阳", "crop": "西红柿",
    "plant_date": "2026-10-10", "harvest_date": "2027-01-10",
    "area_mu": 80, "cost_per_mu": 5200, "expected_yield_per_mu": 4500,
    "risk_preference": "balanced"})
print(r["price"], r["decision"], r["confidence"]["grade"])
PY
```

## 目录结构

```
decision_engine/
├── config/           # paths / model / feature 配置
├── data/
│   ├── snapshots/v1/ # 冻结输入快照（SHA256 见 manifests/input_manifest.csv）
│   ├── processed/    # decision_dataset_v1.parquet / .csv
│   ├── features/     # price/weather/HRI/risk/climate/production 特征
│   └── manifests/    # input_manifest / join_qc / feature_dictionary
├── src/decision_engine/
│   ├── data/         # 数据集构建（join 校验、单位换算）
│   ├── features/     # 严格 point-in-time 特征 + 气象/土壤
│   ├── models/       # 回测框架 / 模型族 / 区间 / 开源 benchmark
│   ├── risk/         # HRI / Market Risk / Climate Exposure / Production Context
│   ├── profit/       # 收益与盈亏平衡
│   ├── confidence/   # 置信度（含 drift）
│   └── engine/       # Decision Score + DecisionEngine API
├── models/{price,registry}/   # 最终模型 artifact + 注册表
├── evaluation/{backtests,metrics,figures,cases,open_source}/
├── scripts/          # 全部可复现入口
├── tests/            # 单元测试 + 泄漏测试 + 引擎测试
├── docs/             # 全部报告
└── outputs/          # 演示与日志
```

## 核心脚本

| 脚本 | 作用 |
|---|---|
| `scripts/snapshot_inputs.py` | 冻结输入快照 + manifest（SHA256） |
| `scripts/build_dataset.py` | Decision Dataset v1（价格/成交量/日历/滞后/滚动/分位/季节分位/目标） |
| `scripts/build_weather_features.py` | 六城气象/土壤特征（气候暴露与 ablation） |
| `scripts/train_models.py` | Baseline + 多模型时间回测 + 最终模型选择 + 注册 |
| `scripts/tune_models.py` | Optuna（时间序列验证目标，mean+λ·std） |
| `scripts/build_intervals.py` | P10/P50/P90 四种方法 + coverage 校准对比 |
| `scripts/build_risk_models.py` | HRI / Market Risk / Climate / Production |
| `scripts/build_regional.py` | 朝阳 / 锦州 简化模块 |
| `scripts/run_replay.py` | 历史回放（strict point-in-time）+ 案例 |
| `scripts/explain_models.py` | EBM/SHAP/线性解释 |
| `scripts/make_figures.py` / `make_reports.py` | 图表与全部报告 |
| `scripts/oss_*.py` | 开源公平 benchmark（StatsForecast / AutoGluon / Prophet / FLAML / Darts / sktime / Chronos / tsfresh / Evidently） |

## 科学边界（写死）

- 气象不驱动价格（ablation 复验，见 `docs/PRICE_MODEL_REPORT.md`）；
- 跨城市价格层级不同，**禁止混用**；不做跨城联动；
- 成交量单位未知 → 仅相对口径；
- HRI 是「扩种诱因强度」，不是扩种概率；Climate Exposure ≠ 减产；
- 历史分位未校准时只称 scenario range；亩均成本必须用户输入。

详见 `docs/MODEL_LIMITATIONS.md` 与 `docs/FINAL_MODEL_REPORT.md`。