# A05_REVIEW — 《沈阳市不同蔬菜的气象响应差异与市场恢复特征》同行评审记录

**状态**：ACCEPTED
**评审方式**：结构化自评（按施工手册 §39 检查项逐项核对文章与其结果表）
**声明**：自动化一致性检查不构成同行评审，也不代表论文价值。

## 1 Research question（方法是否真的回答问题）
问题为品种差异与恢复；差异检验用交互项 Wald-F（而非比较 p 值），恢复判据预先固定；整篇标为探索性，符合预注册的 hypothesis_type。

## 2 Data（数据范围是否被夸大）
数据同上；恢复用事件相对化异常，判据（|z_rel|≤0.5 连续 3 日、上限 42 日）在正文明确固定。

## 3 Statistics
- **autocorrelation（自相关）**：交互模型含 AR(1)；恢复过程基于事件相对化序列，已在局限说明未对恢复指标作显著性判定。
- **multiplicity（多重比较）**：交互检验家族 4 项，BH-FDR；恢复指标为描述性不做多重检验，已说明。
- **sample size / power（样本量与功效）**：交互检验 N=9,160（合并样本），力较强；恢复观察右删失率高（51%/46%）。
- **confounding（混杂）**：交互模型含 AR(1) 与节假日；未控制品种固定效应（以基准品种吸收），已在方法说明为饱和交互设定。
- **effect size（效应量）**：交互以 Wald-F 报告；恢复以天数中位数与删失比例报告。
- **uncertainty（不确定度）**：交互给 p 与 q；恢复为描述性未给 CI，已在局限说明。

## 4 Claims（结论是否超过证据）
C-A05-HET 为 partly_supported（q 最小 <0.0001）；C-A05-RECOVERY 为 descriptive_only。未构造韧性分数，符合要求。

## 5 Figures（图是否误导）
以表为主；A05_heterogeneity.csv、A05_recovery_by_crop.csv 可独立阅读。

## 6 Sources（引用是否真的支持对应事实）
Kaplan & Meier (1958) 对应右删失；Cameron 等 (2008) 对应推断方法；Pan & Zheng (2023) 对应易腐农产品波动传导背景。

## 7 Reproducibility（数字能否从脚本重算）
A05() 可重跑。

## 8 评审意见汇总
**ACCEPTED**（探索性）。建议对恢复阈值做敏感性扫描以量化判据选择的影响。
