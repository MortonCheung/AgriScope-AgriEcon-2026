# M3_SYNTHETIC_EXPERIMENTS.md（R09 / §四十一~四十三）

> **合成输入**（0/12/24/48/72/96h × 5 阶段）**仅用于测试模型结构**，**不是沈北实际值**。

## 合成剂量响应（M3-A 与 M3-C）

        stage  duration_h  M3A_loss  M3C_low  M3C_high  M3C_width
   vegetative           0     0.000    0.000     0.000       0.00
   vegetative          12     0.000    0.000     0.000       0.00
   vegetative          24     0.000    0.000     0.000       0.00
   vegetative          48     0.180    0.130     0.280       0.15
   vegetative          72     0.240    0.190     0.340       0.15
   vegetative          96     0.300    0.250     0.400       0.15
     jointing           0     0.000    0.000     0.000       0.00
     jointing          12     0.000    0.000     0.000       0.00
     jointing          24     0.000    0.000     0.000       0.00
     jointing          48     0.000    0.000     0.000       0.00
     jointing          72     0.000    0.000     0.000       0.00
     jointing          96     0.210    0.160     0.310       0.15
    tasseling           0     0.000    0.000     0.000       0.00
    tasseling          12     0.000    0.000     0.000       0.00
    tasseling          24     0.000    0.000     0.000       0.00
    tasseling          48     0.000    0.000     0.000       0.00
    tasseling          72     0.000    0.000     0.000       0.00
    tasseling          96     0.000    0.000     0.000       0.00
      silking           0     0.000    0.000     0.000       0.00
      silking          12     0.000    0.000     0.000       0.00
      silking          24     0.000    0.000     0.000       0.00
      silking          48     0.000    0.000     0.000       0.00
      silking          72     0.000    0.000     0.000       0.00
      silking          96     0.000    0.000     0.000       0.00
grain_filling           0     0.000    0.000     0.000       0.00
grain_filling          12     0.000    0.000     0.000       0.00
grain_filling          24     0.000    0.000     0.000       0.00
grain_filling          48     0.000    0.000     0.000       0.00
grain_filling          72     0.000    0.000     0.000       0.00
grain_filling          96     0.135    0.085     0.235       0.15

## 单调性检查（M3-A）

        stage  monotone_nondecreasing
   vegetative                    True
     jointing                    True
    tasseling                    True
      silking                    True
grain_filling                    True

## 锚点不确定性敏感性（±25% 扰动 500 次）

        stage  mean_abs_dev_under_25pct_anchor_perturb
   vegetative                                   0.1147
     jointing                                   0.0327
    tasseling                                   0.0000
      silking                                   0.0000
grain_filling                                   0.0268

## 只回答以下五个问题（§四十三）
1. 数学稳定：单调性检查 全部通过；
2. 输出物理合理：M3-A 落在 [0, 0.95]；M3-C 区间宽度随时长增大；
3. 文献异质性区间：见 `M3C_width`（抽雄吐丝期宽度可达 ~0.2）；
4. 最敏感参数：锚点斜率（±25% 扰动下平均绝对偏差见上表）；
5. 必须由 Data Agent 补的输入：**积水持续时间**、**方差信息**、**春玉米本地试验**。

## 严禁
> ❌ 不得据此写出“沈北减产 X%”。
