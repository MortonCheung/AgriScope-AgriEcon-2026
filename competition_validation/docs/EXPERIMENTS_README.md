# experiments/ — 独立论文验证环境（AgriScope HRI / 价格模型 / 策略回测）

本目录是**独立的复算与修复环境**，用于在不改动原工程的前提下验证并修复审查报告中的 P0 缺陷。

- 原始工程：`/Users/morton_cheung/Desktop/比赛/大数据分析`（**只读，0 修改**）
- 只读快照：`../source_snapshot/`（内容哈希与迁移基线一致）
- 本环境：`农业建模/experiments/`（唯一写入位置）

## 目录

```text
experiments/
├── README.md                  # 本文件
├── REPORT.md                  # ★ 新研究报告（含论文标题/核心图表/结论）
├── run_chain.py               # 运行入口（隔离 PROJECT_ROOT）
├── environment/               # 环境与输入指纹
│   ├── env_fingerprint.json   # Python/依赖/种子/代码指纹/折定义
│   ├── input_fingerprint.json # 冻结快照逐文件 SHA256
│   └── pip_freeze_key.txt
├── code/
│   ├── src/                   # 已修复的代码副本（决策引擎）
│   ├── scripts/
│   └── FIXES.md               # ★ 逐条 P0 修复说明（diff + 前失败/后通过）
├── code_original/src/         # 未修复代码副本（用于"修复前测试失败"证明）
├── root/                      # 隔离 PROJECT_ROOT（数据快照 + 全部运行输出）
├── baseline/                  # 冻结的旧结果与旧报告（只读）
├── results/
│   ├── A00_repro_unpatched/   # 未修复代码的完整复现运行
│   ├── B01_fixed/             # 修复后运行
│   ├── analysis/              # 前后对照 / 显著性 / 年份稳健性
│   ├── figures/               # 论文核心图表 F1–F4
│   ├── p0_regression_BEFORE.csv / _AFTER.csv
└── tests/p0_regression.py     # P0 回归测试（未修复 0/7 → 修复后 7/7）
```

## 运行方式

```bash
cd 农业建模/experiments

# 1) P0 回归测试：未修复 vs 修复后
EXPERIMENTS_DE_SRC="$PWD/code_original/src" python3 tests/p0_regression.py   # 0/7 PASS
EXPERIMENTS_DE_SRC="$PWD/code/src"          python3 tests/p0_regression.py   # 7/7 PASS

# 2) 完整链路（隔离 PROJECT_ROOT=experiments/root）
PYTHONHASHSEED=0 python3 run_chain.py results/A00_repro_unpatched "leakage,models,intervals,risk,hri,backtest"
PYTHONHASHSEED=0 python3 run_chain.py results/B01_fixed            "risk,hri,backtest"

# 3) 对照 + 显著性 + 成图
PYTHONHASHSEED=0 python3 analysis/compare.py
python3 analysis/figures.py
```

## 冻结与可复现约定

- **输入冻结**：`root/models/data/snapshots/final_v1` 来自源快照 `final_v1`（`environment/input_fingerprint.json` 记录逐文件 SHA256）。
- **代码冻结**：`code/src` 与 `code_original/src` 的 `.py` 内容树哈希记录在 `environment/env_fingerprint.json`。
- **随机性**：`PYTHONHASHSEED=0`，模型种子 `SEED=42`，切点随机抽取改为日期派生确定性种子。
- **时间切分**：expanding walk-forward，三折 `test2024 / test2025 / test2026(≤2026-09-14)`。
- **失败即报告**：任一阶段异常写入 `results/*/run.log` 并中止，不凭旧 CSV 编造结果。

## 边界（务必与结论一并引用）

- 主指标 `realized_return = 未来30天窗口均价/建仓价 − 1`，是**市场机会收益**，**不是农户经营利润**。
- HRI 是"扩种诱因/跟风环境"指标，**不是农户行为概率**，也**无扩种标签**，不作因果推断。
- 模型选择使用同一 OOT 折（残余选择偏差），详见 `code/FIXES.md` 附录。
- 本次只重跑沈阳/朝阳价格模型 + HRI + 沈阳策略回测；未重跑 60/90 天长期与跨城链路。
