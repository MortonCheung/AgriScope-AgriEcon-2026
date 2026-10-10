# competition_validation_final — 定稿前方法核验与正式论文

- 分支：`paper-final-20261010`（**不影响 `main`**）
- 日期：2026-10-10
- 用途：汇总本轮三项方法核验（P0-A/B/C）、权威结果、正式论文与提交清单

---

## 1. 本轮三项方法核验

| 编号 | 问题 | 判定 | 影响 |
|---|---|---|---|
| P0-A | 季节策略使用了"决策日之后才可获知"的未来标签 | **成立** | 季节策略成绩被高估，已修正并重算（step30 均值 +9.26% → **+4.01%**） |
| P0-B | 随机策略的高 HRI 命中率被布尔化，恒为 100% | **成立** | 风险对照失真，已改为池内占比口径（约 10%） |
| P0-C | 价格模型训练标签跨越测试起点 | **成立** | 训练集含测试期价格信息，已实施 purge/embargo 并**重训** |

回归测试：`tests/p0_final_regression.py`——**修复前 0/4 通过 → 修复后 4/4 通过**
（证据：`metrics/p0_final_BEFORE.csv`、`metrics/p0_final_AFTER.csv`）

## 2. 结论变动（摘要）

- ❌ **作废**："在不重叠口径上，季节策略与最小尾部风险策略显著优于随机" → 修正后 **31 个不重叠切点上无任何策略通过校正**。
- ✅ **保持**：价格预测 7/10 品种优于基线（改善 2.7%—24.0%）。
- ✅ **保持**：HRI 与未来 12 周收益负向关联，**BH-FDR 校正后 5/10 显著**（非重叠检验在 12 周窗口不可用）。
- ✅ **保持（核心）**：**四个重点配对全部不显著**——复杂预测策略未能显著优于季节策略。
- ✅ **保持**：在 128 个 7 天切点上，四个正向策略显著优于随机基准。

详见 `docs/CHANGELOG.md` 与 `docs/FINAL_RESULTS.md`。

## 3. 目录

```text
competition_validation_final/
├── docs/
│   ├── METHOD_AUDIT.md               # 三项方法问题核验（结论、证据、修复）
│   ├── PIT_LEAKAGE_TEST.md           # 价格模型前瞻标签泄漏审计与 purge
│   ├── FINAL_RESULTS.md              # 权威结果（唯一口径）
│   ├── FINAL_EVIDENCE_REGISTER.md    # 逐结论证据登记（含"可宣称/不可宣称"）
│   ├── FIGURE_REGISTER.md            # 图表登记与质量自检
│   ├── CHANGELOG.md                  # 本轮变更与被作废结论
│   ├── PAPER_EVIDENCE_AUDIT.md       # 早期证据审计（历史）
│   ├── FINAL_STRATEGY_COMPARISON.md  # 策略配对对照（历史）
│   ├── REPORT.md                     # 修复与重跑研究报告（历史）
│   ├── PAPER_REVIEW_NOTES.md         # 论文审稿修改记录
│   └── PAPER_OUTLINE.md              # 论文目录
├── paper/
│   ├── PAPER_DRAFT_v2.md             # 可编辑定稿（Markdown）
│   ├── 论文正式版.docx               # 正式版 Word（按附件1 排版）
│   ├── 论文正式版.pdf                # 正式版 PDF（27 页）
│   └── 提交材料检查表.md
├── figures/                          # 论文图表（含技术路线与预测对照）
├── metrics/
│   ├── tables/                       # 策略/预测权威结果表
│   ├── audit/                        # 审计中间结果
│   └── p0_regression_*.csv, p0_final_*.csv
└── source/
    ├── decision_engine_patched/      # 修复后决策引擎源码
    ├── pre_fix/                      # 修复前版本（2 个关键文件，用于对照）
    ├── audit_final.py / final_strategy_comparison.py / figures_*.py
    ├── p0_regression.py / p0_final_regression.py
    └── run_chain.py
```

## 4. 未上传的内容与原因

| 内容 | 原因 |
|---|---|
| `submission/参赛数据包.zip`（6.9 MB，含建模数据集） | 数据来自政府公开平台，**再分发条款未逐条核验**；仅在本地交付，并已在论文与数据包说明中标注合规缺口 |
| 模型权重（joblib/npz）、原始第三方资料、完整运行日志 | 与结论复现无关或属受限内容 |

## 5. 重要边界（与论文一致）

- 所有收益为**市场价格窗口的相对变化**，**不是农户经营利润**；
- 策略比较是**历史价格序列的滚动回测**，**不是真实种植经营试验**；
- HRI 是**追高环境指标**，**不是农户跟风概率**；本文**未观测农户扩种决策**；
- 模型选择使用同一 OOT 折，**未做嵌套交叉验证**（残余选择偏差已声明）。
