# A06_REVIEW — 《沈阳市蔬菜市场量价关系风险传导与天气信息预测增量》同行评审记录

**状态**：ACCEPTED
**评审方式**：结构化自评（按施工手册 §39 检查项逐项核对文章与其结果表）
**声明**：自动化一致性检查不构成同行评审，也不代表论文价值。

## 1 Research question（方法是否真的回答问题）
三个问题（量价关系、传导链条、预测增量）与三套方法（含 AR 的回归、预注册两步规则、Rolling Origin）匹配。传导未被写成成立的结论，符合规则。

## 2 Data（数据范围是否被夸大）
数据同上；预测明确采用 Rolling Origin 而非随机切分；填补值与标准化仅用训练折（防泄漏）。

## 3 Statistics
- **autocorrelation（自相关）**：量价回归含 price_z_(t-1)（系数 0.93–0.97）与 HAC(14)；预测任务以 RMSE 比较，规避标准误问题。
- **multiplicity（多重比较）**：量价家族 10 品种 BH-FDR；预测为模型比较未作多重检验，已说明。
- **sample size / power（样本量与功效）**：量价 N=916/项、N=9,160（POOLED）；预测每品种约 4–5 折，折数少已列入局限。
- **confounding（混杂）**：含节假日与自身滞后；Ridge alpha 预注册固定为 1.0（未调参），已在局限说明。
- **effect size（效应量）**：量价报告 β 与 CI；预测报告 ΔRMSE 与相对增益百分比。
- **uncertainty（不确定度）**：量价 CI；预测以 Wilcoxon 符号秩检验给出 p（C-A06-FORECAST 已附 p）。

## 4 Claims（结论是否超过证据）
C-A06-PV、C-A06-CHAIN、C-A06-FORECAST 均为 not_supported 且均附 p；结论未越界为因果。

## 5 Figures（图是否误导）
以表为主；A06_price_volume.csv、A06_forecast_gain.csv 可独立阅读。

## 6 Sources（引用是否真的支持对应事实）
Roberts & Schlenker (2013) 对应供需弹性识别框架；Ubilava (2017) 对应价格可预测性；Pan & Zheng (2023)、杨娟等 (2020)、张昊 (2023) 对中国批发市场量价与传导提供背景。

## 7 Reproducibility（数字能否从脚本重算）
A06_core() 与 A06_forecast() 可重跑；Ridge 为确定性算法。

## 8 评审意见汇总
**ACCEPTED**。天气无预测增量这一阴性结论已按 §21 正常报告并给出检验统计量。
