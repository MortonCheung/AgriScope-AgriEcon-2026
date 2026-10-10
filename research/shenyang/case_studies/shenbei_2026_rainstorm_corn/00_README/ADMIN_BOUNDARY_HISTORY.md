# ADMIN_BOUNDARY_HISTORY.md — 行政区划沿革与可比性（P2-03）

> 目的：回答“旧行政区名称的数据能否与今天沈北新区拼接”。
> 字段：`year | administrative_name | boundary_change | affected_area | comparability | source_id`

## 1. 沿革事实（官方来源）

| 年份 | administrative_name | boundary_change | affected_area | comparability | source_id |
|---|---|---|---|---|---|
| 1959-12-31 | 撤销**沈阳县**建制，设立**新城子区** | 沈阳县辖地分别划入邻近各区，并设立新城子区 | 今沈北一带 | UNKNOWN | SRC-HIST-XZQH |
| 1960 | **新城子区** | 正式设立（沈阳市民政局口径：1960 年撤沈阳县设新城子区） | 今沈北一带 | APPROXIMATELY_COMPARABLE | SRC-SY-MZJ-NAMES |
| 1960–2006-11-06 | **新城子区** | 无“更名”以外的边界变更证据落在本地资料中 | 今沈北一带 | APPROXIMATELY_COMPARABLE | SRC-SY-MZJ-NAMES |
| 2006-10-08 | 民政部批准更名 | 《民政部关于辽宁省沈阳市新城子区更名为沈北新区的批复》民函〔2006〕300号；辽政〔2006〕240号 | — | — | SRC-SY-GOV-2006-27 |
| **2006-11-07** | **沈北新区**（更名生效） | **“所辖行政区域不变，政府驻地不变”** | 全境 | **DIRECTLY_COMPARABLE** | SRC-SY-GOV-2006-27 |
| 2007-01-01 | 沈北新区（公章启用） | 机构公章自 2007-01-01 起启用 | — | DIRECTLY_COMPARABLE | SRC-SY-GOV-2006-27 |
| 2006-11-22 | 沈北新区揭牌 | 由“新城子老区 + 农业高新区”合署后二区并一区 | 全境 | DIRECTLY_COMPARABLE | SRC-CCTV-2006 |

## 2. 关键裁定

> **2026 年沈北新区的地理范围 = 2006-11-07 起的新城子区（更名后同名）**：市政府文件明确“**所辖行政区域不变、政府驻地不变**”。

- 因此，**2006-11-07 之后的“沈北新区”数据与今天 DIRECTLY_COMPARABLE**。
- **1960–2006-11-06 的“新城子区”数据**：更名公告证明 **2006 年时点**其辖域与今沈北一致，但**该区间内部是否存在更早的边界微调，本地无证据** → 保守判为 **APPROXIMATELY_COMPARABLE**（进入模型前须逐一核验边界）。
- 结论：**旧“新城子区”数据不是“不能拼接”，而是“需要逐一核验边界后可拼接”**；当前因**未取得任何 2000–2017 的新城子区/沈北玉米数据**，该问题在本阶段**尚不触发**。

## 3. 对历史玉米序列的影响

- 若未来取得 **2000–2006 年的“新城子区”玉米数据**，可比性按 **APPROXIMATELY_COMPARABLE** 处理（需核边界），**不得直接无缝拼接**。
- 若取得 **2007 年及以后“沈北新区”数据**，按 **DIRECTLY_COMPARABLE** 处理。

## 4. 新增来源登记（见 DATA_SOURCE_REGISTRY.csv）

| source_id | 来源 | URL | 时间 |
|---|---|---|---|
| SRC-SY-GOV-2006-27 | 沈阳市政府《关于新城子区更名为沈北新区的通知》沈政发[2006]27号 | https://www.shenyang.gov.cn/zwgk/zcwj/zfwj/szfwj/202112/t20211201_1700582.html | 2006-12-20 |
| SRC-SY-MZJ-NAMES | 沈阳市民政局·沈阳13个区县市名称由来 | https://mzj.shenyang.gov.cn/xxgk/zwgkzdgz/fdzdgknr/qhdmzl/dmgl/202208/t20220815_3951353.html | 2018-02-04 |
| SRC-HIST-XZQH | 行政区划网·沈阳市历史沿革 | http://www.xzqh.org/html/show/ln/4054.html | — |
| SRC-CCTV-2006 | 央视国际·中国最年轻新区诞生（沈北新区揭牌） | http://news.cctv.com/china/20061122/103811.shtml | 2006-11-22 |
