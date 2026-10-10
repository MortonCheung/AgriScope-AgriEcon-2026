# AgriScope 当前状态 · RC3

更新于 2026-10-08。唯一正式仓库为 MortonCheung/AgriScope；当前交付包含前端、后端、冻结 Final、Daily、长期双目标、**真实 LLM 评估**及部署/验收工具。

短期 Final 保持 final_v1，实时源码指纹 b19b187268ee92db，施工前 173 个源码/报告/模型文件全部逐字节未变。

长期 V2 已完成标签成熟清洗、目标/模型选择与校准分离、历史回测、独立指标重算、120 项 Registry 和上市决策接口。正式上市目标为基准日后第 H 至 H+13 天的平均批发市场价；周期目标为第 1 至 H 天的市场均价。两者不可互换。

2024–2026 历史已参与旧版研究，最终独立样本为 **0**。当前 80 项情景结果、40 项 150/180 天探索结果，全部低可信度。90/120/150/180 天市场方向决策回放没有改善季节基线的证据；不支持强推荐或生产点预测。未来预测发行和成熟标签评估已接通，不能靠旧历史重新切片取得独立资格。

Daily 与长期结果最新观测均为 2026-10-06，Daily 标记发布延迟。长期任务在 Daily 成功后独立推理、不重训；异常不破坏短期或 Daily。

真实 LLM 评估已完成（`REAL_LLM_EVALUATED_RETROSPECTIVE_ONLY`）：356 次真实调用、360 条有效响应、0 失败；带 PIT 上下文的 LLM 预测相对基线平均 **+4.62pp**（74/96 组更优，60/90/120/150 全档为正），匿名盲测 **−4.71pp**（无增益），残差 −4.21pp（无增益）；Hybrid A/B/C 均未过门禁，标 `HYBRID_NO_GAIN_STATISTICAL_FALLBACK_ACTIVE`。LLM/Hybrid 一律 `RESEARCH_ONLY`，不进入生产 Registry。服务器地址可达但 SSH 公钥认证被外部阻塞，部署包与 systemd/nginx 手册已备，**本机联调不等于服务器上线**。

实际全量验证：前端 322 tests；Python 全层 168 tests + Daily 84 tests；Backend 19/19；Final 38/38；Daily 33/33；长期产物 120 条门禁通过；独立指标重算 586,000 行最大偏差 ≈2.8e-14。唯一未过项是资产哈希门禁（RC3 改动文件与 RC2 manifest 不一致，发布前需重冻结）。更完整证据见 RC3_FINAL_REPORT.md、RC3_TEST_REPORT.md、RC3_DEPLOYMENT_REPORT.md 与三份 LLM 报告。
