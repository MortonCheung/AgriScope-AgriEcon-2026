# V4 参考、源码与设计决策

## 参考阅读与实际查看
1. [Apple Maps](https://developer.apple.com/design/human-interface-guidelines/maps)：网页及 Apple 官方 DocC JSON 正文已读。采用 muted 地图、可交互空白区域、清晰 selection 描边；不覆盖地图中央。地图始终保留，外围 DOM 只在实际文字/控件区域接收指针。
2. [Split Views](https://developer.apple.com/design/human-interface-guidelines/split-views)：采用地图主区与左右附属栏、选择驱动详情、窄屏改为地图加信息 Sheet。当前选中持续可见，不重开 Inspector。
3. [Panels](https://developer.apple.com/design/human-interface-guidelines/panels)：Inspector 跟随正式选择自动更新，Hover 只显示临时极简预览，外壳不随城市卸载。
4. [Layout](https://developer.apple.com/design/human-interface-guidelines/layout) / [Disclosure](https://developer.apple.com/design/human-interface-guidelines/disclosure-controls)：一级留城市、农业情况、风险与行动；方法与版本放进依据；与内容相关的展开控件就近出现。本轮保留暖白出版物体系，不采用新 Liquid Glass 视觉。
5. [Siena case study](https://www.awwwards.com/siena-film-foundation-case-study.html)：已在真实浏览器打开并播放 dynamic-menu 嵌入视频；WebGL 内容与局部/全局导航各司其职。采用 Header 三入口、城市工作台局部目录和同 Canvas 连续性；不复制电影胶片、模糊后处理、商业资源或闭源实现。截图见 output/playwright/v4-baseline/siena-reference.png。
6. [Chartogne-Taillet](https://www.awwwards.com/inspiration/chartogn-taillet-dive-through-the-wines-plots)：查看 inspiration 页面和原站。原站有年龄声明门槛，本轮未替用户声明年龄；只把公开地图案例作为地域轮廓/地点层级视觉启发，不声称已验证门槛后的所有操作。
7. [CatmullRomCurve3](https://threejs.org/docs/pages/CatmullRomCurve3.html) / [Curve](https://threejs.org/docs/pages/Curve.html)：阅读官方 API 示例、上游原码及本地已安装 three 的 Curve.getPointAt，确认它通过 getUtoTmapping 弧长映射采样；使用 centripetal 曲线并验证累计方位角，不能用首尾 atan2 判断整圈。
8. [camera-controls](https://yomotsu.github.io/camera-controls/)：阅读实际 basic.html 与本地 setLookAt 实现，动画阶段每帧 setLookAt(...,false)；不叠加第二层 smooth。自主浏览控制在开场关闭，路由中断取消 RAF。
9. [R3F demand rendering](https://r3f.docs.pmnd.rs/advanced/scaling-performance)：保留 demand、动画触发 invalidate、停止后不持续请求帧；Canvas 不随 Outlet 重建。

## 方案选择
- 观察状态 A：URL 是省域 selection 权威，nullable 城市上下文只保留业务缓存，Hover 独立。采用此方案，取消通用 store→URL effect。备选所有状态单 store 继续易被历史/会话污染，拒绝仅把默认字符串改 null 的局部补丁。
- 镜头 A：手工段插值容易切线断裂；B：Catmull-Rom+独立 target；C：导演阶段。采用 B+C，完整闭合环绕段弧长采样，图纸/组装/环绕/落位共用时间轴，末帧显式 provinceView。
- 研究外壳 A：唯一城市壳与 body-only 模块页，采用；B：提前 return 两套独立壳虽能去双×但容易再次漂移，拒绝。
- 决策：保留旧 supported 价格语义，增加功能能力和已发布观测；六城统一经营分析默认入口。用户成本/亩产/销售价是显式假设，实时确定性计算；价格模型仅按真实功能能力开放。

## 文件施工计划
Phase 1：appContext/useContextUrl、provinceSelection、SpatialShell、Canvas selection、LiaoningPage 最小选择原型与 Router hydration 测试；Gate=无默认城、六城连续切换、POP恢复。
Phase 2：LiaoningPage/CitySummary/MarketOverview/ProvinceThemes/liaoning-page.css，以已发布生产与气候数据构建省域和城市两种 Inspector；Gate=地图主体、不同内容、无内部状态小字。
Phase 3：cameraViews、AssemblyDriver/CameraRig、OpeningPage/phase、相关测试与 camera proof；Gate=真正一圈、精确落位、跳过/中断/减少动效。
Phase 4：AppHeader/ContextBar、CityResearchPage/CityModulesWorkspace、NavigationControls/cityExit；Gate=一份壳、一个明确返回、旧链接可用。
Phase 5：后端 capability/schema/观测服务，前端经营计算器/功能能力适配/DecisionPage；Gate=六城实际输入计算、预测严格隔离。
Phase 6：context link helper、研究和决策入口/返回，useArticle 的请求切城隔离；Gate=city/crop/horizon/date 往返保持。
Phase 7：更新 ITEACH_MIGRATION_MATRIX 后删除 presentation 与无用 ContextBar，文案/焦点/响应式精修；Gate=无重复操作、手机完整操作。
Phase 8：正式自动门禁、六尺寸浏览器流程、Opening/hover/selection/六城/手机截图录屏、缺陷修复与提交报告。

修改产品前：本地必查源已读，两子 Agent 分别形成空间与能力独立审计；基线真实浏览器和 API 已运行；官方参考和实际源码已查看。报告落在 docs/v4，根目录不堆施工报告。各阶段 build 后本地提交；不 Push/Merge/Tag/Deploy。
