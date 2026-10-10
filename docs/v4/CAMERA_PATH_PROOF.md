# Camera Path Proof

轨迹已通过数学采样，浏览器关键帧与录屏仍需在实际场景验收。

- 采用 three 已安装的 centripetal CatmullRomCurve3 + getPointAt（1200 段弧长表），不新增依赖。
- 统一线性时间轴 4800ms；分段导演内部 smoothstep；相机 Position 与 Target 独立。
- 图纸 0–192ms；组装/下降 192–864ms；完整环省 864–4224ms；上升落位 4224–4800ms。
- 累计展开方位 360°，不是误用首尾角差。
- 实际地图半径 28.781682、6896 顶点；每个采样对 1.8 深度顶/底面与 5 个桌面比例检查。
- 最低相机高于地块 78.932715；最低水平半径 0.65r（高俯视开场）。
- 最小画面留边 28.45%；全体地图顶点在画面内。
- 最大速度 7.71548r/s；相邻 6.667ms 采样的最大速度差 0.204081r/s。分段故意缓入缓出，未把整段速度伪称常速。
- 网格可见时，21:9 地面最大覆盖半径 5.708094r ≤ 6r 纸面。
- 最后一帧 JSON 与 provinceView(radius) 严格相等；省域根节点 Y rotation=0。

关键位姿与全量时间/target/速度/投影采样见 CAMERA_PATH_SAMPLES.json；顶视与高度证明见 CAMERA_PATH_PROOF.svg。

窄屏最终 fit 由父场景统一增加相机距离，不在此数学证明中宣称已完成移动端视觉验收。

复建：在项目根目录运行 node docs/v4/CAMERA_PATH_PROOF.mjs（Node 24，直接读取实际产品 TS 轨迹与真实 GeoJSON）。
