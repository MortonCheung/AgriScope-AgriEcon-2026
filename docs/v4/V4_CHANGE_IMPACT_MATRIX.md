# V4 需求落点与影响

- R01 删除讲解：AppShell/presentation/README/迁移矩阵；移除 launcher、快捷键、轮询、样式和专用测试；不改 Evidence Drawer。
- R02 省域默认：appContext/useContextUrl/Router；city nullable，省域无周期自动注入；风险=历史覆盖，Router回归证明。
- R03 地图主体：liaoning-page.css/cameraViews；左右低密度 Inspector、窄屏 Sheet；风险=遮挡与取景，六尺寸实测。
- R04 省域/城市分离：LiaoningPage/CitySummary/观测 API；已发布年度面积与完整年气候，严格注明年份/范围；无省域均价。
- R05 Hover/Click：SpatialShell/Canvas/Mesh/selection helper；同一 select、独立 hover、leave恢复；实际 Mesh 与 DOM 两入口验收。
- R06 技术文案：LiaoningPage/MarketOverview/ProvinceThemes/DecisionPage/研究工作台；主区不展示层级、哈希、内部编号；真实限制进依据。
- R07 控件去重：AppHeader/ContextBar/CityModulesWorkspace/NavigationControls；结构删除双壳，不用 CSS 隐藏重复。
- R08 六城决策：capability_service/schemas/planning observations/经营分析；旧价格 supported 保持，新增 feature contract 与假设计算；禁止生产 fake/fallback。
- R09 开场：cameraViews/AssemblyDriver/Opening；弧长曲线真实环绕+精确末帧；采样proof+录屏。
- R10 城市一致：CityResearchPage/CityModulesWorkspace/DecisionPage；同壳不同研究颗粒度；保留正式内容原文。

## 扩展边界
仅新增只读轻量观测与功能能力契约，不改变 Decision Engine 或模型。规则计算与正式推理分开；六城非预测分析不调用不存在的价格接口。保持单 Canvas、现有 Research Repository、Evidence Drawer、设计 tokens。任何数据不一致直接显示可解释错误，不补假指标。
