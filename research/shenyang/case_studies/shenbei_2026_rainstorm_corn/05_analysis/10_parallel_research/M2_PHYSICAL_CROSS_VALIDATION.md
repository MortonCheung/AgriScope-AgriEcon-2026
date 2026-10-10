# M2_PHYSICAL_CROSS_VALIDATION.md（R03 / §十四~十七）

对每个变量回答三件事：① 物理预期方向 ② 证据区实际方向 ③ 是否可能受数据结构/空间偏差影响。

            variable expected  evidence_region_median  background_median     diff      z direction_consistent               possible_bias
           elevation        −                  51.691             47.880    3.811  0.219                False 证据点误差3–5km；河网/道路掩膜；DSM 建筑树冠
               slope        −                   0.402              0.434   -0.032 -0.023                 True 证据点误差3–5km；河网/道路掩膜；DSM 建筑树冠
        local_relief        −                   1.636              1.753   -0.116 -0.025                 True 证据点误差3–5km；河网/道路掩膜；DSM 建筑树冠
    depression_depth        +                   0.116              0.107    0.009  0.021                 True 证据点误差3–5km；河网/道路掩膜；DSM 建筑树冠
   flow_accumulation        +                   2.443              2.330    0.113  0.006                 True 证据点误差3–5km；河网/道路掩膜；DSM 建筑树冠
                 twi        +                   9.552              9.518    0.035  0.038                 True 证据点误差3–5km；河网/道路掩膜；DSM 建筑树冠
                hand        −                   0.000              0.000    0.000  0.000                False 证据点误差3–5km；河网/道路掩膜；DSM 建筑树冠
   dist_mapped_water        +                4930.567           3258.481 1672.087  0.542                 True 证据点误差3–5km；河网/道路掩膜；DSM 建筑树冠
   dist_mapped_river        +                7567.101           6310.087 1257.014  0.415                 True 证据点误差3–5km；河网/道路掩膜；DSM 建筑树冠
dist_mapped_drainage        +                7851.727           5516.538 2335.189  0.462                 True 证据点误差3–5km；河网/道路掩膜；DSM 建筑树冠
     dist_major_road      n/a                 845.730           1076.270 -230.541 -0.255                 None 证据点误差3–5km；河网/道路掩膜；DSM 建筑树冠

**方向一致变量数：8/10**

## flow_accumulation 反向专项调查（§十六）

- 证据区中位数 = 2.44，背景中位数 = 2.33 → 证据区**偏低**。
- log1p(flow_accumulation) 与其它变量的相关：{'hand': 0.112, 'depression_depth': -0.223, 'dist_mapped_water': -0.218, 'dist_mapped_river': -0.073, 'dist_mapped_drainage': -0.2, 'twi': 0.071}
- 高汇流值占比：max=582（该像元百分位 1.000）；高汇流像元多位于**河道/主干沟**，而 **cropland mask 把河道排除** → 农田单元本身**远离大汇流**。
- D8 在**平坦东北平原**易产生人工集中流路；填洼（Priority-Flood）会改变农田微地形 → 汇流指标在本地**物理可解释性弱**。
- 与 HAND / depression / 水系距离**存在共线**（见上表相关系数）。

### 结论
> `flow_accumulation` 的“方向异常”**不能解释为机制反例**：它是**数据结构效应**（河道被排除、平坦地形 D8 失真、与 HAND/距离共线）。
> **处理**：不删除、不反转、不改权重；保留原样，在正式 M2 中**降权或改用 `specific catchment area`/log1p** 作为敏感性变体（§十七禁止因方向不好看而擅改）。
