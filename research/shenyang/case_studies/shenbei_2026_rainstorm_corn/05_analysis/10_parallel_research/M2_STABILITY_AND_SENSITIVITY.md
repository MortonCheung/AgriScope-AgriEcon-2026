# M2_STABILITY_AND_SENSITIVITY.md（R05 / §二十三~二十五）

## 权重集合（sensitivity ensemble，**不用于挑最好结果**）

| 设定 | 组成/权重 |
|---|---|
| equal | 变量 10 个；权重 [1.0] |
| terrain_emphasis | 变量 6 个；权重 [1.0, 3.0] |
| drainage_emphasis | 变量 3 个；权重 [1.0, 3.0] |
| depression_hand_emphasis | 变量 2 个；权重 [1.0, 3.0] |

### 设定间 Spearman 秩相关

                          equal  terrain_emphasis  drainage_emphasis  depression_hand_emphasis
equal                     1.000             0.810              0.793                     0.409
terrain_emphasis          0.810             1.000              0.398                     0.612
drainage_emphasis         0.793             0.398              1.000                     0.073
depression_hand_emphasis  0.409             0.612              0.073                     1.000

### 稳定性分类（基于 4 套设定）

stability_class
stable_other    27916
unstable        13845
robust_high       712

| 类别 | 定义 |
|---|---|
| **robust_high** | 4/4 套设定下均为 High/VeryHigh（>P80） |
| unstable | 仅 ≤2 套设定下为 High/VeryHigh |
| stable_other | 其余 |

## 与 Phase 4 分辨率敏感性的一致性（复述并加注）
- Phase 4：网格 50/100/250m 与 DEM 30/90m 下，正样本处易感性百分位约 0.50–0.57（较稳）。
- 本轮回审要点：**须用 rank correlation / High·VeryHigh 重叠 / 已知正样本富集 / 空间格局一致性** 共同判断，不能只看一个数字（§二十三）。

> ⚠️ 稳定性图**不是新“真值”**，只是**模型稳健性**（§二十五）。
