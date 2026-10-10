# A08_REVIEW — 《气象条件与沈阳市农业单产变化的区县面板研究》同行评审记录

**状态**：ACCEPTED
**评审方式**：结构化自评（按施工手册 §39 检查项逐项核对文章与其结果表）
**声明**：自动化一致性检查不构成同行评审，也不代表论文价值。

## 1 Research question（方法是否真的回答问题）
问题为气象与单产的关系；主结局选择单产而非总产量的理由（总产量=面积×单产）在正文明确，方法匹配。

## 2 Data（数据范围是否被夸大）
生产 A 级、气象为再分析网格（已声明非实测）；≥35℃ 高温日在 2020-2024 为 0 这一数据约束被明确说明并据此改用生长季平均气温。该处理正确。

## 3 Statistics
- **autocorrelation（自相关）**：面板为年度尺度，序列相关弱于日度；仍采用聚类稳健 SE。
- **multiplicity（多重比较）**：家族定义为作物 × 暴露，按暴露分家族 BH-FDR，报告 raw p 与 q。
- **sample size / power（样本量与功效）**：关键局限：每作物 56 观测、聚类数 8，模型含 14 个固定效应参数。正文明确声明不假装 8 个聚类足够精确，并并列报告 wild cluster bootstrap。
- **confounding（混杂）**：含区县与年份固定效应，未控制灌溉、品种、投入（无数据，已列入局限）。
- **effect size（效应量）**：报告 log 因变量下的 β（弹性解释）与 95% CI。
- **uncertainty（不确定度）**：聚类 95% CI 与 wild bootstrap p 双口径并列。关键：4 项显著的聚类 p 为 0.006–0.017，但 wild bootstrap p 均为 0.057，正文据后者判定为部分支持但不确定——处理正确且诚实。

## 4 Claims（结论是否超过证据）
C-A08-PANEL 为 partly_supported；C-A08-WCB 为 descriptive_only，明确指出 8 聚类下推断的不可靠性。

## 5 Figures（图是否误导）
表 A08_panel_results.csv、A08_wild_bootstrap.csv、A08_robustness_loo.csv 可独立阅读。

## 6 Sources（引用是否真的支持对应事实）
Bertrand 等 (2004)、Cameron 等 (2008)、Roodman 等 (2019) 对应少聚类推断；Chen & Gong (2021)、Tao 等 (2008)、Deschênes & Greenstone (2007)、Schlenker 等 (2006) 对应面板识别；Huang & Zhang (2026) 对应温度指标设定的关键警示。

## 7 Reproducibility（数字能否从脚本重算）
A08() 可重跑；wild bootstrap 299 次、固定种子。

## 8 评审意见汇总
**ACCEPTED**。少聚类推断的谨慎处理（并列两种 p、不宣称显著）是本项目的核心方法学优点。建议扩展区县或年份后重估该效应。
