# RC2 需求、研究与施工顺序

本轮唯一仓库为 `MortonCheung/AgriScope`，起点 `main=12bf227`；施工分支 `feat/long-horizon-v2-hybrid-final`。`v1.0.0-rc1` 与原 stash 永久保留。本计划记录本轮实际需求，不替代验收证据。

## 当前行为与期望行为

当前长期层把 `(t,t+H]` 的均价当唯一目标；选型与成绩复用相同年度测试，训练标签未按成熟时间清洗；Job 每次拟合模型且不使用最新 Daily。期望区分周期市场中枢和真正上市窗口价格，训练只由显式命令触发，Daily 成功后仅做推理，长期决策收益情景采用上市窗口价格。

用户明确选择预计上市跨度或日期。不得从作物名称猜生育期，不得以粗区域日历覆盖输入。没有可信成本和亩产，不报告真实利润。当前 HRI、市场风险和气候背景不得冒充未来风险。

## 冻结边界

- Final `final_v1`、`code_fingerprint=b19b187268ee92db` 的算法、模型、报告、训练数据不改、不重训。
- Daily 核心保持原样，由外围编排器在成功后启动独立长期 Job；失败隔离。
- 旧 `/api/decision` 与 `/api/daily/latest` 保持兼容；新增长期决策契约。
- 前端保留当前视觉，增加必要输入与双目标展示。
- LLM Secret 仅检查 present/absent，不记录值，不挪用 IDE 凭据。无 Key 完成工程和统计研究，真实数值实验报告阻塞。

## 研究结论必须服从证据

2024、2025、2026 已进入 RC1 目标和模型选型，不能将其中任何重新切片自动变成 untouched。V2 采用按成熟标签清洗的 development / tuning / calibration / retrospective audit，后者明确为被查看过的历史重分析。真正 untouched 采用未来事先冻结协议，当前 final 样本数为零；没有独立证据时只发布情景或探索结果，不能宣称长期模型已得到独立生产验证。

候选包含 endpoint、centered/post 的 7/14/30 日窗口与周期均价；窗口选择仅使用开发与调优段，并先施加销售业务约束。逐 crop×horizon×target 记录结果。样本账本区分完整历史、评估窗、实际完整标签及保守非重叠暴露，非重叠不等于统计独立。

## 按依赖施工与验收

1. 只读 Git、报告、数据及代码重审；实跑旧基线；两个并行研究方案比较。
2. 程序化目标、标签成熟时间、严格时间切分与样本账本；锁定目标、模型候选、配置和实用增益 Gate，记录 hash。
3. 重跑统计模型、区间校准、逐目标 Registry 与历史上市决策回放；保留可重算预测记录。
4. 显式 retrain 生成版本化长期模型包；Daily appended 同口径历史用于推理。Job 实现锁、幂等、fsync 原子发布、防 latest 回退。
5. LLM 匿名归一化、PIT 上下文、严格 schema、有效响应缓存和真实重复性修复；有合法 Key 先小规模真实 Pilot，无 Key 不伪造。
6. 独立长期决策 API、双目标 API、freshness/fallback/version 契约；最小前端集成。
7. Manifest 用 immutable/generated/external/optional 类型，模型、Registry、schema、prompt、运行代码强校验；准备 systemd/nginx/env/bundle/smoke。
8. Frontend、Backend、Final、Daily、长期、LLM、真实浏览器 E2E、秘密和大文件扫描；独立重算关键指标。
9. 根报告替换过期叙事，历史移至 `docs/archive/rc1/`；所有结果与限制入库。按真实 Freeze Gate 决定发布，不用标签掩盖科学证据不足。

终止条件：所有授权且当前可完成的代码、实验、集成、验收和部署准备完成；只保留真实外部 Secret/权限缺口。若独立评估证据缺失，必须另行明确科学验证未满足，禁止把工程通过写成 `LONG_HORIZON_V2_VALIDATED`。

方法依据：[模型选择与评估偏差](https://www.jmlr.org/beta/papers/v11/cawley10a.html)；[非交换数据的分割校准限制](https://jmlr.org/papers/v25/23-1553.html)。这些依据不能替代项目自身独立测试。
