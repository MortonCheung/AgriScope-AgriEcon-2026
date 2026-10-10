# Opening 与省域共享移动端取景

正式手机与平板使用同一个 Canvas 舞台：宽度等于视口，起点为 `var(--ag-nav-height)`，高度为 `43dvh`。Opening 全页仍占整屏，品牌与进入/跳过控件位于 DOM 层。省域首屏沿用同一个舞台，因此路由提交前后 Camera.aspect、projection 与 Camera Pose 都不变化。

只有 Camera Pose 相同不足以保证画面连续：把 Canvas 从 390×844 突然改成 390×363 时，垂直 focal length 同时改变，地图像素尺寸仍会跳。正式实现已经采用共用舞台，避免这个根因；不需要把宽高差掩盖成额外 zoom 动画。

## 纯函数与接入

`responsiveProvinceRadius(actualRadius, aspect)` 只调摄影机取景半径，不改变地图几何：

```ts
fittedRadius = actualRadius * Math.max(1, 0.875 / actualCanvasAspect)
```

`0.875` 来自本轨迹对真实辽宁地块的水平取景和六倍纸面覆盖联合验收。无有效 Canvas 比例时回退到原半径；无有效几何半径时抛 RangeError，不给 WebGL 写入 NaN。

在 `SceneContents` 从 `useThree(state => state.size)` 取得实际 Canvas width/height，而不是 `window.innerWidth / window.innerHeight`。以同一个 fittedRadius 驱动 `CameraRig` 和 `AssemblyDriver`；几何、PaperGround、SketchPaper、dropHeight 等继续消费真实 model.radius。

正式 sketch/ready 与 `orbitView(fittedRadius, 1)` 共用摄影机半径；`phase=ready` 必须 instant，立即跳过才会直接到终态。窄屏后撤若大于原半径，CameraControls 的 maxDistance 也要按 fittedRadius 提高，不能由旧 5×actualRadius 上限偷偷夹回去。

## 真实几何证明

证明使用 `frontend/public/geo/liaoning.json` 的真实投影坐标；对每个轨迹位置逐点检查地块 y=0 与 y=1.8 面，计算 NDC x/y 与视锥深度，而非仅检查圆形或猜测 CSS 宽度。

正式共用舞台：

- 手机 390×362.92（390×844 页面中的 43dvh）：aspect=1.074617、fit=1；721 位姿最低 NDC 留边 0.235839；末帧地图约 240.94×156.92px；网格可见范围 3.72772×actualRadius。
- 平板 768×440.32（768×1024 页面中的 43dvh）：aspect=1.744186、fit=1；721 位姿最低 NDC 留边 0.284478；末帧地图约 292.32×190.39px；网格可见范围 4.702285×actualRadius。

保守比较另保留两种原始 Canvas 比例：

- 全屏 390×844：fit=1.893590；最低 NDC 留边 0.079421；末帧地图约 293.47×189.87px；网格可见范围 5.927913×actualRadius，仍在 6×actualRadius 纸面内。
- 紧凑 390×363：fit=1；最低 NDC 留边 0.235671；末帧地图约 240.99×156.96px。

实际模型 radius=28.781682；四种比例全部不截地图，末帧精确等于对应 `provinceView(fittedRadius)`。这里的 NDC 留边是 `1 - max(abs(x), abs(y))`，不是浏览器 screenshot 的像素测量。

## 可重复验收

运行 `node docs/v4/CAMERA_PATH_PROOF.mjs` 更新 CAMERA_PATH_SAMPLES.json 的四个 responsiveCases，以及原桌面证明。脚本对地图截断、网格露边、角度、相机高度、速度差和末帧不一致设置失败退出。

`cameraViews.test.ts` 额外从渲染层 `buildLiaoningSolidModel` 读取真实简化几何，用 three PerspectiveCamera 实际投影顶/底面，四种比例各检查 181 个时间点，并验证同舞台 Opening→省域共用 fit 与精确终态。数学验收通过后，还须看实际浏览器手机截图/录屏，检查 DOM 控件、城市名字、面板与地图的重叠。
