# MODEL_CARD_M2.md

| 项 | 值 |
|---|---|
| 模型名称 | **M2 沈北农田渍涝空间易感性/风险模型（Route A：证据重建）** |
| 版本 | v1.0（2026-09-23） |
| 研究目标 | 回答“2026-07 暴雨后，沈北哪些农田更易积水、为什么、证据多强” |
| 研究区域 | 沈北新区行政边界 ∩ 耕地（ESA WorldCover class40） |
| 空间单元 | **100 m 规则网格**（42,473 个耕地单元，424.7 km²） |
| 输入变量 | PRE-EVENT：elevation/slope/local_relief/depression_depth/flow_accumulation/twi/hand、dist_mapped_{water,river,drainage}、drainage_density、dist_major_road、cropland_frac；EVENT：event_precip、antecedent_7d/14d |
| 输出变量 | susceptibility（物理易涝性 0–1）、event_exposure_rank、M2R_risk（重建风险 0–1）、risk_class、confidence_class |
| 数据来源 | 边界=DataV；DEM=Copernicus GLO-30；耕地=ESA WorldCover 10m；水系/道路=OSM；降雨=ERA5；SAR=Sentinel-1(PC) |
| 空间分辨率 | 分析 30 m；**输出 100 m**（受最弱数据源约束；soil 缺失、rainfall 单点） |
| 时间范围 | 事件 2026-07-12~15；事件前 14 日湿润；SAR 2026-07-06 / 07-18 |
| 标签结构 | G1=0；G2=7；G3=1；**可靠负样本=0**；空间误差 3–5 km |
| 模型方法 | **非监督**：机制方向 + 等权的物理易感性指数 + 三层融合（易感性 / 事件暴露 / 观测证据） |
| 验证方式 | 已知正样本邻域召回、秩一致性、与独立 SAR 证据的 Spearman；**不做** ROC/AUC（无负样本） |
| 适用范围 | **描述与重建 2026 事件**；识别“为何某些区域更易涝”的地形—水文机制 |
| 不适用范围 | ❌ 未来降雨情景预测；❌ 无灾害世界定量；❌ 田块级（<100m）精确判定；❌ 玉米专属（仅 agricultural cropland） |
| 局限 | 排水网络严重不完整；无可靠负样本；SAR 无历史对照且未定标；土壤缺失；降雨为单点 forcing；证据点空间误差 3–5 km |
| 是否能反事实 | **否**（`ELIGIBLE_FOR_DESCRIPTION_ONLY`） |
| 模型等级 | **M2-L2（多源事件重建）**，未达 L3/L4 |
