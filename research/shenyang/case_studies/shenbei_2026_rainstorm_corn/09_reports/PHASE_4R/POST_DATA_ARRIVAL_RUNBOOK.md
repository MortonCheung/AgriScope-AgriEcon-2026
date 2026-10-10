# POST_DATA_ARRIVAL_RUNBOOK.md（R18 / §八十八）

> 目标：Data Agent 完成后，**不需要重新思考整个项目**，按步骤直接执行即可进入正式建模。
> 前置条件：`FULL_DATA_ACQUISITION_REPORT.md` **存在**且数据 mtime 停止变化。

---

## Step 0（前置门禁）
- **输入**：仓库根目录 `FULL_DATA_ACQUISITION_REPORT.md`
- **动作**：确认存在；确认目标数据文件 mtime 已停止更新（≥10 分钟无变化）
- **PASS**：报告存在且无写入活动 → 继续
- **FAIL**：不存在或仍写入 → **停止**，不进入后续步骤

## Step 1 数据合同检查
- **输入**：全部新数据（`01_sources/ 02_raw/ 03_clean/ 04_marts/`）
- **脚本**：`python3 scripts/validate_new_data_contract.py --root .`
- **输出**：`logs/PHASE_4R/DATA_CONTRACT_CHECK.csv`
- **PASS**：所有 `REQUIRED` 项为 PASS 或 WARNING（可修复）
- **FAIL**：任一 `REQUIRED` 为 FAIL → 先修数据/单位/CRS，再重跑

## Step 2 更新输入快照
- **脚本**：`python3 scripts/90_p4r_snapshot_audit.py`（重跑）→ 追加 `logs/PHASE_4R/INPUT_SNAPSHOT.md`（增补段，含 SHA256/行数/时间范围）
- **注意**：**不修改** `01_sources/DATA_SOURCE_REGISTRY.csv`（Data Agent 维护）；如需补录来源，写入**独立的** `logs/PHASE_4R/REGISTRY_ADDENDUM.csv`
- **PASS**：快照覆盖全部新输入
- **FAIL**：出现 SHA256 冲突（同路径内容变化）→ 重新确认版本

## Step 3 重建统一数据集
- **脚本**：`python3 scripts/81_p4_terrain_hydro.py` → `82_p4_grid_sar.py` → `84_p4_baseline_reconstruct.py`
- **输出**：`04_marts/M2_spatial_dataset.{csv,gpkg}`（**注意：该路径属 Data Agent 只读区** → 改为写入 `06_models/M2_waterlogging_spatial/models/` 的新版本，**不覆盖**原文件）
- **PASS**：单元数、面积、风险分级账目闭合（总单元 = 有效分类 + 明确未分类）
- **FAIL**：出现 NaN/inf 传播或账目不平 → 回到 `aggregate()` 的 nodata 处理

## Step 4 M2 增强验证
- **脚本**：`python3 scripts/91_p4r_m2_crossval.py`
- **输出**：`05_analysis/10_parallel_research/M2_*.md`
- **PASS**：证据区域富集比 >1 且方向在 1/3/5km 缓冲下稳定；排水变量贡献**非主导**
- **FAIL**：富集比 ≈1 或方向随缓冲大幅翻转 → M2 维持 L2，不升级

## Step 5 判断 duration 是否解锁
- **输入**：多时相 SAR（≥3 时相）或官方积水起止记录
- **判定（§五十七）**：D1 官方起止 / D2 多期遥感限定区间 / D3 仅单次 → **D3 不解锁**
- **PASS**：≥D2 → 计算 `waterlogging_duration_proxy` 并写入 M3 输入
- **FAIL**：仅 D3 → **M3 不得启动**（§九十一）

## Step 6 若解锁 → 正式 M3
- **脚本**：`python3 scripts/92_p4r_m3_prebuild.py`（结构）→ 用真实 duration 重新校准 **M3-B（先验级，全球 meta 分组效应作弱信息先验）** 与 **M3-C（保守区间）**，M3-A 作透明基准
- **文献输入**：`06_models/prebuild/M3/M3_LITERATURE_EVIDENCE_AUDIT.csv`（8 行；含 `LIT-TIAN2021META` 全球 meta、`LIT-BILL2026RICE` 方法学）
- **契约**：`06_models/prebuild/M3/M3_INPUT_CONTRACT.md`
- **PASS**：单调性通过 + 区间物理合理
- **FAIL**：缺方差 → 禁止加权 meta（只允许区间/先验）；缺 duration → 停止

## Step 7 若排水参数解锁 → 正式 M4
- **脚本**：`05_analysis` 下的 M4 校准（基于 `06_models/prebuild/M4/m4_water_balance.py`）
- **测试**：`python3 scripts/tests/test_m4_mass_balance.py`、`test_m4_monotonicity.py`、`test_m4_scenario_ordering.py`
- **PASS**：5 不变量 + 3 测试全通过
- **FAIL**：任一不变量失败 → **先修模型**，不得进入反事实

## Step 8 若市场数据足够 → 事件研究
- **设计**：`06_models/prebuild/market/MARKET_EVENT_STUDY_PREREGISTRATION.md`
- **PASS**：玉米 farmgate/wholesale/retail 至少一级、2021–2025 同期可用
- **FAIL**：仅他作物 → **标记 NOT_FEASIBLE**，不用替代作物

## Step 9 重新判断四世界资格
- **脚本**：`06_models/prebuild/counterfactual/engine.py` + `scripts/tests/test_mc_propagation.py`
- **门禁**：M2 Gate A–F、M3 单调性、M4 不变量、B/C/D 定义合规（B≠rain=0；C≠all drainage=0）
- **PASS** → 生成 `COUNTERFACTUAL_ELIGIBILITY_*` 新版，允许**带区间**的四世界结果
- **FAIL** → 只输出**描述性重建**，并写明缺失项

---

## 禁止事项（贯穿全流程）
1. 不修改 Data Agent 目录中的既有文件；
2. 不用假默认值让 pipeline “跑通”（缺字段一律 `WAITING_FOR_DATA`）；
3. 缺 `waterlogging_duration` 时输出任何“沈北减产 X%”；
4. 缺 `drainage capacity / depth` 时输出“提前 24h 减少 X 小时积水”；
5. 直接生成正式平行世界数字。
