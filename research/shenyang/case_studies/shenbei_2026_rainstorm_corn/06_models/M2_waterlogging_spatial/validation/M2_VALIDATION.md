# M2_VALIDATION.md（P4-44/45/48）

> **无可靠负样本** → 不报告 accuracy/specificity/ROC-AUC（无意义）。改报与“已知正样本/独立证据”的一致性。

                                     metric  value
 known_positive_recall(neighborhood>median)   0.50
mean_susceptibility_percentile_at_positives   0.59
               background_median_percentile   0.50
     spearman_susceptibility_vs_SAR_deltaVV   0.05
                                 spearman_p   0.00

## 空间验证方式说明
- 本阶段 **Route A（无监督监督模型）** → 不适用 train/test 空间分块；
- 若未来获得 G1 标签，**必须**用 spatial block CV（按街道/方块留出），禁止随机像元切分（§43）。
