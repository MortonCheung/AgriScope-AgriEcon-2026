# AgriScope 前端 V3 压力验收与可访问性抽查报告

日期：2026-10-09（Asia/Shanghai）｜范围：只做验证与取证，不修改任何源码，不做 git 操作。

## 1. 执行环境与方法

- 前端：http://127.0.0.1:5173（Vite dev server，package agriscope v1.0.0；React 19 + react-router-dom 7 + zustand 5 + motion + three）。后端：http://127.0.0.1:8787，前端以 /api 代理到 8787。
- 真实工具：
  - TRAE 内置浏览器（browser_lock/unlock、browser_snapshot、browser_click、browser_press_key、browser_evaluate、browser_console_messages、browser_take_screenshot）；承担压测 1/2/3/4/6/7、键盘可达序列、DOM 取值与截图。
  - Chrome DevTools MCP（CDP 级，独立 Chrome 实例，同一 dev URL）：承担视口缩放（resize_page）与设备仿真（emulate viewport）、CDP 级按键（Enter/Escape 复核），并直接对 /api/decision、/api/forecast/long-horizon 发起 POST 取原始 JSON 做交叉验证。
  - 说明：TRAE 内置浏览器无窗口/视口缩放原语，resize 项改在 Chrome DevTools 实例取证；两处均为真实浏览器访问真实 dev 服务。
- 症状探针（每次操作后执行，客观量）：
  - ①底部飞线：遍历 .ag-underline[data-active]，bottomN = 下划线 top 大于等于 innerHeight-2 的个数。
  - ②错误按钮飞线：staticN = 宿主 position 为 static 的个数；misN = 下划线逸出宿主矩形（top 小于宿主 top-1 或 top 大于宿主 bottom+1）的个数。
  - ④resize 错位：documentElement.scrollWidth 大于 innerWidth+1（横向溢出）；头部容器 .ag-header__inner 与 main 左缘是否一致。
  - 控制台：按 [error] 计数；每次硬刷新取当前导航后的消息。

## 2. 压测结果表（规范 §32）

| 序号 | 项目 | 次数 | ①底部飞线 | ②错误按钮飞线 | ③首次刷新闪烁 | ④resize 错位 | 证据 |
|---|---|---|---|---|---|---|---|
| 1 | hard refresh（/liaoning 与 /decision 与 /research 轮换） | 20 | 无 | 无 | 无 | 不适用 | 20 次探针 bottomN=0、staticN=0、misN=0；活动下划线恒为当前一级导航（top 约 56，宿主 relative，落在宿主 -4..57 内）；每次硬刷新 2 条 [error] net::ERR_ABORTED（capabilities + daily） |
| 2 | route change（5 个空间 SPA 切换） | 30 | 无 | 无 | 无 | 不适用 | 30 次真实路由变更（含少量同路由重复点击与目标未就绪的尝试，已如实计入）；每次 actN=1 且高亮与路径一致 |
| 3 | city change（/liaoning 六城） | 20 | 无 | 无 | 无 | 不适用 | URL 每次更新 ?city=slug，ContextBar select 值同步（shenyang/tieling/chaoyang/jinzhou/dandong/dalian）；bottomN、misN、overflowX 全 0 |
| 4 | horizon change（决策中心 7/14/30 与长期 30/60/90/120/150/180） | 20 | 无 | 无 | 无 | 不适用 | 短期页签与长期页签 aria-pressed 均按点击正确切换（如 short=30 天、long=180 天）；无飞线与溢出 |
| 5 | resize（1440x900 到 1920x1080 到 1280 到 1024 到 768 到 390，两轮） | 2 轮 x 6 尺寸 | 无 | 无 | 无 | 无 | 每档 scrollWidth 等于 innerWidth（无横向溢出）；hdrLeft 等于 mainLeft（1440 为 40、1920 为 280、其余为 0）；下划线均落在宿主内 |
| 6 | back / forward（三个一级空间各 5 后退 + 5 前进） | 30 | 无 | 无 | 无 | 不适用 | 交替后退/前进 URL 成对复原（/liaoning 对 /research，/cities/dandong/decision 对 /research 等） |
| 7 | direct URL（6 个地址） | 6 | 无 | 无 | 无 | 不适用 | /cities/chaoyang、/cities/dandong、/cities/cross_city、/research?view=cross_city、/research?view=synthesis 均正常渲染；/liaoning?city=朝阳&horizon=7 的 city 被忽略 |
| 8 | production preview | 0 | 不适用 | 不适用 | 不适用 | 不适用 | 未执行：5173 为 dev server，无法覆盖 production preview，未伪造结果 |

四种症状总体结论：① 未复现；② 未复现；③ 未观察到异常闪烁（硬刷新首帧为正常 loading 骨架加三维地图淡入，头部与内容无跳动、无白屏）；④ 未复现。

## 3. 可访问性结果表（规范 §38）

| 检查项 | 结果 | 证据 |
|---|---|---|
| Tab 到达主导航 | 通过 | Tab 序列命中 AGRISCOPE、上一级、辽宁农业态势/决策中心/研究中心 |
| Tab 到达地图城市按钮 | 通过 | 命中六城按钮（aria-label 如 沈阳，市场状态：关注） |
| Tab 到达决策页页签 | 通过 | 命中 决策中心/短期市场比较/上市窗口决策，以及短期 7/14/30 与长期 30 到 180 页签、作物/周期选择 |
| Tab 到达风险剖面条 | 通过 | 命中 .center-risk__head（5 条，aria-expanded） |
| Tab 到达抽屉开关 | 通过 | 命中证据抽屉触发按钮；移动端命中 city-research__drawer-toggle（aria-expanded、aria-controls） |
| Enter 激活 | 通过（CDP 复核） | CDP 级 Enter：焦点在 研究中心 链接则路由跳转到 /research；焦点在风险剖面 head 则 aria-expanded 由 false 变 true |
| Escape 关闭 Evidence Drawer | 通过 | TRAE 与 CDP 复核：role=dialog、aria-modal=true 的抽屉在 Escape 后 dialog 数归 0 |
| Escape 关闭移动端抽屉 | 通过 | CDP：Escape 后 drawer-toggle 的 aria-expanded 由 true 回 false，焦点回到开关 |
| focus-visible 可见 | 通过 | 全站 :focus-visible 2px 描边；实测聚焦元素 outline-width=2px、outline-color=rgb(26,25,23) 或 rgba(26,25,23,.72) |
| 图表文本摘要 | 通过 | 决策中心图 1 个 figure 含 .ag-sr-only 文本（figcaption）；情景模拟对比图含 .ag-sr-only 说明；EstimateChart 含 .ag-sr-only |
| 颜色非唯一状态表达 | 通过 | 六城按钮同时含符号（三角/圆/半圆）+ 文本（关注/数据不足/部分数据）+ aria-label；风险剖面每条含文字档位（低/中等/偏高）配 data-band 颜色 |
| 每页 error 级控制台报错 | 存在（dev 噪音） | /liaoning、/decision、/research 各 2 条；/cities/shenyang 3 条；/scenario-lab 6 条；/cities/chaoyang、/cities/dandong、/research?view=cross_city、/research?view=synthesis 各 1 条。均为 net::ERR_ABORTED |

## 4. 数据交叉验证表（规范 §49 随机抽样）

| 抽样项 | 前端值 | 来源值 | 是否一致 | 核对方法 |
|---|---|---|---|---|
| 短期 forecast（沈阳·土豆·7 天） | 中心 2 元/kg；区间 1.5-3.1；horizon 7 天；更新 2026-10-06 | POST /api/decision：price.mid=1.96、low=1.54、high=3.13、unit=CNY/kg | 是 | 前端 .decision-note 文本 vs CDP 直接 POST 原始 JSON；前端按 1 位小数四舍五入 |
| long horizon 150（沈阳·土豆） | 2.69 元/kg；区间 1.59-2.69；探索性·可信度低 | POST /api/forecast/long-horizon(150)：point_forecast=2.6908、range_low=1.5938、range_high=2.6908、production_status=EXPLORATORY_SCENARIO_ONLY | 是 | 前端长期区块 vs CDP POST 原始 JSON |
| long horizon 180（沈阳·土豆） | 2.61 元/kg；区间 1.49-2.61 | POST /api/forecast/long-horizon(180)：point_forecast=2.6098、range_low=1.4928、range_high=2.6098 | 是 | 同上 |
| 朝阳 HHI（跨城条形与表） | 0.691 | runtime/research/product/cross_city/tables/cross_city_production_concentration.csv = 0.6907355855478551 | 是 | 前端跨城页文本 vs runtime 研究导出 CSV |
| 铁岭 HHI | 0.723 | 同 CSV = 0.7231541212009527 | 是 | 同上 |
| seasonal amplitude（季节指数极差，沈阳·土豆价格） | 0.266（Evidence Drawer 第 2 层） | runtime/research/product/shenyang/tables/A01_seasonal_amplitude.csv 土豆 price = 0.26596560588502927，toFixed(3)=0.266 | 是 | 前端证据抽屉 vs runtime CSV |
| weather effect（沈阳 A02） | 在含自回归的日度模型中，100 项核心检验仅 6 项 FDR 显著且效应量小于等于 0.06 个标准差，94 项无证据。序列持续性极强（AR(1) 中位 0.930）（Drawer 第 4 层） | runtime/research/product/shenyang/articles/A02.json 的 frontend_summary 原文一致 | 是 | 前端证据抽屉 vs runtime 研究产物 article.json |
| cross-city r（西红柿季节同步均值） | 西红柿 r 均值 = 0.97（A10 结论） | runtime/research/product/cross_city/tables/cross_city_seasonal_sync_by_crop.csv 西红柿 mean_corr = 0.9672904529197479 | 是 | 前端 A10 结论文本 vs runtime CSV |
| NOT_SUPPORTED（铁岭模块） | 铁岭页 chips：A01 到 A06、A08 = NOT_SUPPORTED；A07、A09 = DRAFT | runtime/research/product/tieling/manifest.json 同状态 | 是 | 前端模块工作台 chips vs runtime manifest.json |

一致率：9 / 9 = 100%。

## 5. 未执行或无法验证的项

- production preview：5173 为 Vite dev server（npm run dev），未覆盖 production preview（test 里另有 preview 脚本），未伪造结果。
- resize 下限：Chrome 窗口最小宽度约 500px，390 档以设备仿真（emulate viewport 390x844x2,mobile,touch）测量，非真实窗口尺寸；高度 1080 被显示器钳制（实际 vh=771）。
- Enter 激活：TRAE 内置浏览器的合成 Enter 未触发原生 link/button 默认激活（工具限制），故改用 CDP 级 Chrome DevTools 复核；结论为应用侧正常。
- resize 与 CDP 级按键在第二个 Chrome 实例（Chrome DevTools MCP）完成，非 TRAE 内置浏览器同一实例。
- StrictMode 差异：dev 下 React.StrictMode 双挂载使首次请求被 Abort（net::ERR_ABORTED）；production 无 StrictMode，行为可能不同，未在 production 构建验证。
- 未测：hover 态下划线、prefers-reduced-motion 实际表现、真实触摸手势、Lighthouse 性能/Core Web Vitals、长时间内存泄漏。
- 未核对：Daily 快照的 土豆 2.2 元/kg、HRI 46.2、市场风险 47.6 未逐字段与 latest.json 比对（仅界面读取）。

## 6. 发现的问题清单（按严重度）

### 中：控制台 error 级报错（net::ERR_ABORTED）在每次硬刷新/首屏出现
- 复现步骤：硬刷新 http://127.0.0.1:5173/liaoning（或任一页），打开 DevTools 控制台。
- 实际现象：/api/daily/latest、/api/decision/capabilities、/api/research/*（articles、catalog）出现 net::ERR_ABORTED，1 到 6 条每页。
- 判断：dev 下 React.StrictMode 双挂载 + AbortController 清理导致首个请求被取消，页面随后正常渲染；属 dev-only 噪音，但会污染"每页 error 级报错"验收与误报监控。建议在验收口径中区分 aborted 噪音，或在非必要处避免首帧双请求。

### 中：/liaoning?city=朝阳&horizon=7 的 city 参数被忽略
- 复现步骤：直接打开 http://127.0.0.1:5173/liaoning?city=朝阳&horizon=7。
- 实际现象：URL 变为 /liaoning?city=dandong&horizon=7，沿用会话内城市；中文城市名未被识别（isKnownCity 仅接受英文 slug）。horizon=7 生效。
- 影响：若验收期望中文城市参数生效，则口径不一致；否则应与既有"忽略非法值并回退"一致并加说明。

### 低：Evidence Drawer 关闭后焦点恢复不稳定
- 复现步骤：鼠标点击"为什么？看这句结论的来源"打开抽屉，再按 Escape。
- 实际现象（TRAE 观察）：抽屉关闭后焦点落到 body，而非触发按钮；CDP 复核中因触发元素恰为先前聚焦项而恢复正确，未能稳定复现，列为待核。

### 低：/cities/tieling/research/A02 深链显示"研究条目不存在"
- 复现步骤：直接打开 http://127.0.0.1:5173/cities/tieling/research/A02。
- 实际现象：显示 tieling / A2 研究条目不存在；而 /cities/tieling 页面内点选 A02 模块仅在页内切换、不改变 URL（模块级工作台不使用 URL 深链）。为路由可达性/一致性提示，非崩溃。

### 信息：连续后退后前进按钮曾短暂禁用
- 复现步骤：在应用内多次点击"后退"到达栈底附近后再尝试"前进"。
- 实际现象：app history 前进栈在部分序列下被废弃，前进按钮 disabled；交替 back/forward 与每个一级空间各 5 次均正常。

### 信息：窄视口下顶部导航换行
- 复现步骤：将窗口宽度收窄到约 411 CSS px 观察顶栏。
- 实际现象："辽宁农业态势"换行为两行，功能与可达性正常。
