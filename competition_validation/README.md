# competition_validation — 论文最终实验审计与验证包

- 分支：`paper-validation-20261010`（**不影响 `main`**）
- 生成日期：2026-10-10
- 用途：为 2026 辽宁省大学生农业经济建模大赛论文提供**经充分核验、可用于写作**的结论与证据
- 数据快照：`final_v1`（沈阳 10 蔬菜，2021-01-01 ~ 2026-10-06；回测切点池 2024-01-01 ~ 2026-09-04）
- 代码指纹：未修复 `2e42c7e6c5615cdb` / 已修复 `a8a3dc725098bbf2`

> **本包不包含**：模型权重、任何 Parquet 原始/派生数据、第三方原始资料、凭据、完整运行日志。
> 仅含报告、必要源码、指标 CSV/JSON 与正式图表。

---

## 1. 入口

| 文件 | 说明 |
|---|---|
| [`docs/PAPER_EVIDENCE_AUDIT.md`](docs/PAPER_EVIDENCE_AUDIT.md) | ★ **论文证据审计**：逐结论标注原始数字/来源/对照基线/样本量/显著性/局限/是否建议写入 |
| [`docs/REPORT.md`](docs/REPORT.md) | 修复与重跑研究报告（含论文标题、核心图表、结论建议） |
| [`docs/FIXES.md`](docs/FIXES.md) | P0 缺陷逐条修复说明（diff 级 + 修复前失败/修复后通过） |
| [`docs/EXPERIMENTS_README.md`](docs/EXPERIMENTS_README.md) | 独立验证环境的运行与冻结约定 |

## 2. 目录

```text
competition_validation/
├── docs/        报告与审计文档
├── metrics/
│   ├── analysis/     修复前后对照、显著性、年份稳健性
│   ├── audit/        A–I 最终审计产物（候选池同一性、同口径公式对照、多种子随机、重叠感知推断、多重检验、HRI 审计、预测精度）
│   ├── tables/       冻结指标表（HRI 验证、策略基准、价格模型选择、区间校准、泄漏检查）
│   └── environment/  环境与输入指纹、依赖版本
├── figures/     F1–F4 正式图表（PNG）
└── source/      必要源码：已修复决策引擎、三处未修复原模块、审计与测试脚本
```

## 3. 核心可核验结论（详见 `docs/PAPER_EVIDENCE_AUDIT.md`）

1. **候选池/时间窗口/价格数据在修复前后完全一致**（价格与预测列哈希 `5424a42f91a084be`，两代码树相同）。
2. **同一候选池、同一切点、同一 HRI 下的公式隔离**：
   旧"利润"基线（跨作物绝对价格）step30 **−1.53%** → 新相对收益基线 **+8.92%**。
3. **策略显著性（多重检验校正后）**：
   - step7（140 切点）：`Highest_forecast_return / Most_Robust / Seasonal / Balanced_fix_v2` 四项通过保守 Bonferroni；
   - step30（33 不重叠切点）：仅 `Seasonal`、`Most_Robust` 通过保守 Bonferroni，另两项仅通过 BH-FDR。
4. **随机基准多口径核对**：500 次多种子随机分布均值为 step30 +0.13%、step7 +1.04%；
   单次最差分别为 −5.61%、−1.53%。**报告中的"+1.5%"来自旧 667 切点运行，已更正为同口径数值。**
5. **HRI 结论已降级**：12 周普通检验 9/10 显著；经 BH-FDR 多重检验校正后 **5/10** 同时通过块 bootstrap 与 HAC；
   非重叠检验在 12 周窗口不可用。
6. **概念严格分离**：`realized_return` 为市场价格窗口变化，**不是农户利润**；WAPE 为预测精度，不等同收益。

## 4. 复现方式

```bash
# 环境：Python 3.9.6；依赖见 metrics/environment/pip_freeze_key.txt
# 源码：source/decision_engine_patched（已修复）、source/decision_engine_original（未修复，仅 3 个模块）
EXPERIMENTS_DE_SRC=<patched> python3 source/p0_regression.py   # 修复后应 7/7 通过
EXPERIMENTS_DE_SRC=<original> python3 source/p0_regression.py  # 未修复应 0/7 通过
python3 source/audit_final.py                                   # 生成 metrics/audit/*
python3 source/figures.py                                       # 生成 figures/*
```

## 5. 边界声明

- 全部收益指标为**市场价格机会收益**（未来 30 天窗口均价/建仓价 − 1），**非农户经营利润**（无成本/亩产数据）。
- HRI 为"扩种诱因/跟风环境"指标，**不是农户行为概率、不构成因果**。
- 模型选择使用同一 OOT 折（未做嵌套 CV），存在残余选择偏差。
- 主结果仅沈阳；朝阳仅用于价格模型对照，价格口径不同不可合池。
