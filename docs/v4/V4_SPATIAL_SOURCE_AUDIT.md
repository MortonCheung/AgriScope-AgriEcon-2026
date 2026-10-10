# AgriScope V4 Phase 0：空间、上下文与城市研究外壳审计

审计目录：`/Users/morton_cheung/Desktop/比赛/大数据分析/AgriScope`。本审计只读取实际源码，未修改产品代码。依据当前附件《前端 V4 重构施工手册》；附件的新需求优先于旧代码的 V3/V5 注释。以下行号来自本次读取的基线。

## 1. 当前根因与期望行为

### 1.1 `/liaoning` 默认沈阳是模型问题

- `frontend/src/app/context/appContext.ts:23` 定义 `DEFAULT_CITY_ID='shenyang'`，`:62–69` 的持久化类型要求 `cityId:string`，fallback 没有省域态。
- `appContext.ts:71–84` 读取 sessionStorage 的上次城市，`:106–114` 将城市与决策作物、日期、周期混在同一 store。
- `frontend/src/features/liaoning/LiaoningPage.tsx:36–38` 将全局 cityId 直接当 selectedCityId；`:48–50` 永远落回城市摘要，所以从未选择也显示沈阳（或 sessionStorage 城市）。
- `frontend/src/features/liaoning/LiaoningCanvas.tsx:229,354,369` 同样把 Context 当地图选中状态。
- `frontend/src/features/liaoning/MarketOverview.tsx:43` 左栏永远 `useDaily('shenyang')`；只清地图选中仍不能得到真正省域首屏。
- `frontend/src/features/liaoning/ProvinceThemes.tsx:80–99` 强制 cityId，并在主页面铺四个模块摘要；它没有省域数据分支。

期望：无 city 的 `/liaoning` 是省域；不从 sessionStorage 补城、不自动写 horizon；点击才成为 `/liaoning?city=chaoyang`。Hover 独立，不改变锁定城市与 URL。省域统计只能来自正式省级来源或明确标作六城研究区域的真实可比指标。

### 1.2 现有点击方向正确，但状态与镜头未实现完整流程

- `LiaoningCanvas.tsx:239–244` 对六个 study 城市只 `setCity`，没有立即进入城市路由；`LiaoningPage.tsx:94` rail 相同。保留“同一路由观察切城”的方向，不应改回点击就进 `/cities/*`。
- `SpatialShell.tsx:143–149` 是进入研究工作台的显式导航 handler，应由“查看研究”消费。
- `CameraRig` 位于 `LiaoningCanvas.tsx:154–205`；`:186–190` 只按 city mode/focusCity 推近。`SpatialShell.tsx:34–36` focus 只从 `/cities/*` 取值，因此 `/liaoning?city=…` 选择后镜头完全不动。
- `LiaoningPage.tsx:91–94` DOM rail 有 pointerenter/focus/blur，却没有 pointerleave，鼠标离开 rail 会残留 hoveredCityId。3D 的 `CitySolidMesh.tsx:230–232` 有 out 清 hover。
- `LiaoningCanvas.tsx:284–287` hover 时给其他城市 dim；`:354` selected 仍锁定 Context；`CitySolidMesh.tsx:142–149` 已有 hover/selected 抬升及描边优先级，可复用。
- `LiaoningPage.tsx:72` 用 `key=displayView.cityId` 重挂摘要；hover 会重挂完整右栏。应把 hover 限为名称/极简预览，正式 inspector 只由 selected city 驱动。

期望：province selection 与 hovered city 分开；selected 决定左栏/Inspector/小幅相机偏移；hover 决定地图临时强调与极简预览。离开 hover 恢复 selected 或 province，不重挂页面。连续朝阳→锦州无需退出与完整进出纸张动画。

### 1.3 URL 双 Effect 可把新链接反写成旧状态

真实执行链：

1. 初始 store 是沈阳 14；用户打开 `?city=chaoyang&horizon=30`。
2. `frontend/src/app/context/useContextUrl.ts:25–32` 的读 Effect 写 store。
3. 同一 commit 的 `:34–43` 写 Effect 闭包仍然是沈阳 14，比较后立即 replace 当前 URL 为旧值。
4. Zustand 的下一轮渲染与 Router 更新交错，后退、导览恢复、路径换城时可能继续来回覆盖。

这是代码路径推断；现有单测不足以证实没有竞态：`frontend/src/app/context/appContextUrl.test.ts:6–61` 只测试纯编解码，没有挂载同步 Hook、Router、POP 或 StrictMode。

第二写入者：`frontend/src/app/context/ContextBar.tsx:36–42` 依据城市路径 setCity，和 query bridge 并行；`:53–59` onChange 又 setCity 后 navigate。路径 `/cities/chaoyang/decision?city=shenyang` 形成路径、query、store 三方争写。

无条件 URL 注入：写 Effect 对 `/`、`/liaoning`、`/research` 全部执行，`:41–42` 会把 fallback city/horizon 自动加进去。

期望：路由负责观察状态；province 的 city query 是唯一选中来源；decision 的 city path 优先；决策 crop/horizon/as_of 只在决策路由读取与写入。只保留 URL→store 的集中 hydration，用户 event 显式 navigate 写 URL，取消通用的 store→URL 自动 Effect。若需 store 写回，必须作为同一事务，或有 hydration version 保护，不能靠 Effect 顺序。

### 1.4 单 Canvas 已实现，维持现有结构

- `frontend/src/app/AppShell.tsx:14–21` 一份 SpatialShell。
- `frontend/src/features/spatial/SpatialShell.tsx:154–166` 无 key、无按路由条件卸载 Canvas，隐藏只改容器状态。
- 全 `frontend/src` 的 `<Canvas` 只有 `LiaoningCanvas.tsx:411` 一处。
- `LiaoningCanvas.tsx:413` demand frameloop；原 mesh、材质、geometry 由 memo 持有，`CitySolidMesh.tsx:104–138` 有 dispose。
- `LiaoningCanvas.tsx:345` province root 的 Y rotation 使用 0 常量；视差子组仅 X/Z，`:81–95`，没有模型沿 Y 转一圈。

注意：`SpatialShell.tsx:99–102` route→mode 在普通 Effect 执行，store 初始 mode=opening（`spatialStageStore.ts:29–33`）；直接深链或路由变化会有一次提交使用旧模式。最小修复同步 derive route mode/focus，只让 exiting override，不再把路由衍生状态晚一帧复制到 store。隐藏的 Canvas 被当 province 模式传入 `:159`，会持续保持省域订阅；可显式用 active flag 控制请求、指针与 RAF。

### 1.5 当前确实只有 118°，新 V4 必须替换

- `frontend/src/features/liaoning/cameraViews.ts:21` 明确 118；`:69–81` sketch theta=province theta−118°；`:108–127` 在两角之间插值，实际不是完整环绕。
- `LiaoningCanvas.tsx:37` 是 3600ms；`:39–41` delay 从 0.10 到 0.65，配 `CitySolidMesh.tsx:23` DROP_SPAN=.25，到 .90 才全落定。
- `LiaoningCanvas.tsx:118–149` 当前单 RAF 时间轴同时驱动 assemblyRef、camera pose，可复用；cleanup cancel RAF、begin 幂等已存在。
- `OpeningPage.tsx:37–42` 每次首页 reset、assembleStarted+ready 才自动进 `/liaoning`，可复用。但 `:65–75` 只有进入，没有运行中“立即跳过”。
- `cameraViews.ts:42–59` provinceView 是可复用精确终点；cityView 不是省域选城轻调机位。

新 V4 附件明确拒绝旧 118°方案，必须根据半径/中心建立全环绕。不得把 118 常量改 360 并保留 atan2 首尾 lerp：首尾同方位会被折成 0°，需要 unwrapped theta 或实际曲线采样证明。

### 1.6 双 × 的真实 DOM 源头

非沈阳无 curated catalog 时：

```
CityResearchPage
  main.city-research
    div.city-research__paper
      header.city-research__chrome
        button.city-research__close ×        ← CityResearchPage.tsx:142–149
      CityModulesWorkspace                 ← CityResearchPage.tsx:239–242
        main.city-research
          div.city-research__paper
            header.city-research__chrome
              button.city-research__close ×  ← CityModulesWorkspace.tsx:72–79
```

外壳根源：`CityResearchPage.tsx:110–150` 无条件包 main/paper/header；fallback 内嵌 `CityModulesWorkspace.tsx:62–80` 另一整套 main/paper/header。因此重复标题、嵌套 landmark、双 × 与双 fold/unfold selector 都来自产品结构，不是 CSS。

最小修复：统一 `CityResearchPage`（或提取 CityResearchShell）为唯一 main/paper/header/close/decision入口；把 `CityModulesWorkspace` 降成 body-only 组件，只负责 module picker 与内容。沈阳 tree/body 与五城 module/body 共享外壳，不改变研究内容、编号或方法。若临时要避免提取，可直接在父组件外壳前 return 模块工作台，但不能满足长期统一外壳与入口，故只作为备选。

### 1.7 退出语义和历史语义混同

- `frontend/src/components/NavigationControls.tsx:50,74` 将城市页后退/上一级都送进退出协调器；实际上 via 分别 back/push，语义可保留。
- 两个 × 都 `requestCityExit({via:'back'})`，但 aria-label“返回辽宁”。`cityExit.ts:58–59` target 虽是辽宁，`SpatialShell.tsx:126–127` back 时交给 `appHistory.goBack`。
- `appHistory.tsx:113–123` 存在 app 历史就 navigate(-1)，fallback target 仅没历史用。因此从研究中心→朝阳时 × 会回研究中心，和标签不一致；从朝阳→锦州研究时 × 会回朝阳。
- 与新 province selected 状态不能复用同一个“先fold再route离开”协调器：返回全省应清 selection+query、还原侧栏、轻调相机，而不是 `/cities/*` fold。

建议：browser Back/Forward 保持历史；结构 Up 到父层；研究工作台单一“返回城市概览”显式 `/liaoning?city=<id>`；province Inspector 的“返回全省”只清 city query、hover 和正式选择。决定保留哪项全局 Up/工作台 Close 时按页面避免两个同义动作，不能仅 CSS 隐藏重复按钮。

### 1.8 讲解模式是始终常驻的全局负担

- `AppShell.tsx:20` 常驻 GuidedPresentation；`GuidedPresentation.tsx:255–258` 即使关闭也在每一页显示右下 launcher。
- `GuidedPresentation.tsx:24` EntrySnapshot cityId 必填，依赖默认城市；`:83–95` restore 连续逐字段 set + navigate，叠加旧 URL bridge 竞态。
- `GuidedPresentation.tsx:114–170` 可自动导航、轮询锚点、自动换步；`:172–202` 捕获 Escape 与方向键。新需求若默认关闭，应先移出 AppShell 常驻挂载（更新迁移矩阵），保留显式评审路由/开关入口仅在用户要求的位置。
- `steps.ts:38–41` 首步旁白复述当前“只有沈阳日度快照”能力限制，不宜沿用为新省域首屏主线；状态/模块名的真实来源需保持。

## 2. 两类方案比较

### 2.1 观察状态

方案 A（推荐）：URL 负责 province selection，独立省域 store（scope/city nullable）仅镜像解析结果；hover 归 spatial store；decision context 持有自己的可空城市及参数缓存。省域点击 push city query，return province push 无 city，POP 自然恢复；集中桥只 hydrate 对应路由。优点是无隐藏默认，Back/Forward 可以证明，作用域明确；改动集中在上下文、空间参数与省域页面。

方案 B：把整个 AppContext cityId 改 nullable 并承担地图、研究、决策全部 selection。改动代码表面更少，但共享状态仍容易混成一件事，研究路由/会话缓存又能污染省域，必需额外 scope 字段和路由策略后最终接近 A。只改 `DEFAULT_CITY_ID=null` 不构成修复。

最小步：新增 province selection 纯解析/转换函数与 tests；让 `/liaoning` render 根据 query 同步 derive；Context bridge 改成按路径 hydrate decision context；移除 ContextBar 视觉和它的同步 Effect；`/decision` 无正式城市显示选择入口。

### 2.2 摄影机轨迹

方案 A：手工分段 pose lerp。无需新增依赖，终点精确，但分段速度与切线容易跳，不易达成可观察连续环绕。

方案 B：three 已安装 `CatmullRomCurve3` camera position + 独立 target 曲线，使用 `getPointAt` 弧长采样。位置流畅、适合顶视证明；曲线可能过冲、穿近省域或累计角度不足，必须采样约束。

方案 C：导演分段，统一 progress 分配图纸、组装、环绕、落位。关键是时间线责任清楚，但若镜头仍 lerp 则只是 A。

推荐 B+C：建立半径相对的环绕 control points，在明确环绕段曲线弧长采样；独立 target 稳定省域中心；落位段以平滑混合接 provinceView；progress=1 直接返回 provinceView。保留单 RAF、dropPlan、scene mesh。至少 180–360 个采样计算 unwrap 方位累计变化、最小高度、水平半径、速度峰值、目标可见性。输出顶视 camera/target 轨迹及关键坐标、时间轴与真正浏览器关键帧，再调整实际节奏。

解析圆周+director 是备选最小实现：theta unwrapped、半径/高度函数、target独立，完全可证一圈且常速；但附件偏好 B+C，应在审计记录为什么选它（若采用），不能静默删掉曲线对比与 Camera Path Proof。

### 2.3 研究外壳

方案 A（推荐）：父层统一 shell、模块子组件 body-only，沈阳与五城目录内容组件不同、操作 chrome 一份。

方案 B：父层无 catalog 就提前 return 完整模块页，立刻消双 ×，但同样 header 的实现仍两份，后续 title/decision/up 样式容易漂移。可短期 gate 但不可视为完成六城外壳一致。

## 3. 最小实施顺序与验收

1. 状态/URL：纯省域 nullable 状态；route hydration 单责任；no city/no horizon injection。测试 pristine `/`、`/liaoning`、合法/非法 query、快速换城、POP、decision 路径优先、StrictMode。
2. 省域：省域 overview 与 selected city 左/右数据视图；禁止把沈阳日度冒充省域；保留真实研究载荷和可比性。hover仅极简预览，rail pointerleave 清 hover。
3. 地图：map click/DOM click 统一 selection handler；province selected mild pose；精确保持完整省域可观察，不套 cityView；常驻 Canvas 不重挂。
4. Opening：B+C 全环绕与 proof，减小 stagger、增加立即跳过；只一个时间轴；中断/重复点击/减少动效完成态测试。
5. 外壳：拆 body-only，统一 close/up/back/forward 语义；无重复 main/header/close；更新迁移矩阵后移除旧可见组件。
6. 每个阶段执行 npm run build；非平凡逻辑保留自动化检查。最终浏览器对六城连续切换、返回全省、研究入口、双 ×、focus、手机与 reduced motion 录屏/截图；现有纯 helper tests 不能替代 UI proof。

审计边界：这里没有运行浏览器、没有启动后端、没有逐条核验六城研究/决策能力；这些由同轮主审计负责，不把静态代码结论写成已通过视觉验收。
