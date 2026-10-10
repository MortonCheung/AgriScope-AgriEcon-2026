/** Node >= 24: node docs/v4/CAMERA_PATH_PROOF.mjs. Rebuilds proof from the product trajectory and real map. */
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import {
  CAMERA_FOV_DEG, OPENING_DURATION_MS, OPENING_TIMELINE, orbitView,
  openingStageForProgress, orbitSpanDegrees, provinceView, groundReach, responsiveProvinceRadius,
} from '../../frontend/src/features/liaoning/cameraViews.ts';

const mapUrl = new URL('../../frontend/public/geo/liaoning.json', import.meta.url);
const mapText = readFileSync(mapUrl, 'utf8');
const geo = JSON.parse(mapText);
const coordinates = [];
function collect(value) {
  if (!Array.isArray(value)) return;
  if (typeof value[0] === 'number' && typeof value[1] === 'number') coordinates.push(value);
  else value.forEach(collect);
}
geo.features.forEach((feature) => collect(feature.geometry?.coordinates));
const lngs = coordinates.map((point) => point[0]);
const lats = coordinates.map((point) => point[1]);
const centerLng = (Math.min(...lngs) + Math.max(...lngs)) / 2;
const centerLat = (Math.min(...lats) + Math.max(...lats)) / 2;
const projected = coordinates.map(([lng, lat]) => [(lng - centerLng) * Math.cos(centerLat * Math.PI / 180) * 11, -(lat - centerLat) * 11]);
const xs = projected.map((point) => point[0]);
const zs = projected.map((point) => point[1]);
const radius = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...zs) - Math.min(...zs)) / 2;
const aspects = { '1512x982': 1512 / 982, '1440x900': 1440 / 900, '16:9': 16 / 9, '16:10': 16 / 10, '21:9': 21 / 9 };
const tanV = Math.tan(CAMERA_FOV_DEG * Math.PI / 360);
const normalize = (v) => { const length = Math.hypot(...v); return v.map((n) => n / length); };
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const dot = (a, b) => a.reduce((sum, n, i) => sum + n * b[i], 0);
const subtract = (a, b) => a.map((n, i) => n - b[i]);
const round = (n) => Number(n.toFixed(6));
const roundedPose = (pose) => ({ position: pose.position.map(round), target: pose.target.map(round) });
const samples = [];
let previousTheta = 0;
let accumulatedDegrees = 0;
let maxGroundWhileGridVisible = 0;
let maxSpeed = 0;
let maxSpeedDelta = 0;
let previousSpeed = 0;
let minCameraClearance = Infinity;
let minHorizontalRadius = Infinity;
let finalProjectionBounds = {};
const margins = Object.fromEntries(Object.keys(aspects).map((name) => [name, 1]));
const steps = 720;
for (let index = 0; index <= steps; index++) {
  const progress = index / steps;
  const pose = orbitView(radius, progress);
  const unit = orbitView(1, progress);
  const theta = Math.atan2(pose.position[2], pose.position[0]) * 180 / Math.PI;
  if (index > 0) accumulatedDegrees += ((theta - previousTheta + 540) % 360) - 180;
  previousTheta = theta;
  minCameraClearance = Math.min(minCameraClearance, pose.position[1] - 1.8);
  minHorizontalRadius = Math.min(minHorizontalRadius, Math.hypot(pose.position[0], pose.position[2]) / radius);
  let speed = 0;
  if (index > 0) {
    speed = Math.hypot(...subtract(pose.position, samples[index - 1].pose.position)) / radius / (OPENING_DURATION_MS / steps / 1000);
    maxSpeed = Math.max(maxSpeed, speed);
    maxSpeedDelta = Math.max(maxSpeedDelta, Math.abs(speed - previousSpeed));
  }
  previousSpeed = speed;
  const forward = normalize(subtract(pose.target, pose.position));
  const right = normalize(cross(forward, [0, 1, 0]));
  const up = cross(right, forward);
  const frameMargin = Object.fromEntries(Object.keys(aspects).map((name) => [name, 1]));
  const frameBounds = Object.fromEntries(Object.keys(aspects).map((name) => [name, { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity }]));
  for (const [x, z] of projected) {
    for (const y of [0, 1.8]) {
      const relative = subtract([x, y, z], pose.position);
      const depth = dot(relative, forward);
      for (const [name, aspect] of Object.entries(aspects)) {
        const ndcX = dot(relative, right) / (depth * tanV * aspect);
        const ndcY = dot(relative, up) / (depth * tanV);
        const margin = depth > 0 ? 1 - Math.max(Math.abs(ndcX), Math.abs(ndcY)) : -Infinity;
        frameMargin[name] = Math.min(frameMargin[name], margin);
        if (index === steps) {
          const bounds = frameBounds[name];
          bounds.minX = Math.min(bounds.minX, ndcX); bounds.maxX = Math.max(bounds.maxX, ndcX);
          bounds.minY = Math.min(bounds.minY, ndcY); bounds.maxY = Math.max(bounds.maxY, ndcY);
        }
      }
    }
  }
  if (index === steps) finalProjectionBounds = Object.fromEntries(Object.entries(frameBounds).map(([name, bounds]) => [name, Object.fromEntries(Object.entries(bounds).map(([axis, value]) => [axis, round(value)]))]));
  for (const name of Object.keys(aspects)) margins[name] = Math.min(margins[name], frameMargin[name]);
  if (progress <= 0.60) maxGroundWhileGridVisible = Math.max(maxGroundWhileGridVisible, groundReach(unit, 21 / 9));
  samples.push({ progress: round(progress), timeMs: round(progress * OPENING_DURATION_MS), stage: openingStageForProgress(progress).stage, pose: roundedPose(pose), normalizedPose: roundedPose(unit), cumulativeAzimuthDegrees: round(accumulatedDegrees), speedRadiusPerSecond: round(speed), frustumMargin: Object.fromEntries(Object.entries(frameMargin).map(([name, value]) => [name, round(value)])) });
}
const responsiveCases = [];
for (const [name, width, height] of [['phoneOpeningCanvas', 390, 844], ['phoneProvinceCanvas', 390, 363], ['sharedPhoneStage', 390, 362.92], ['sharedTabletStage', 768, 440.32]]) {
  const aspect = width / height;
  const fitRadius = responsiveProvinceRadius(radius, aspect);
  let minMargin = 1;
  let maxGridReach = 0;
  let finalBounds = null;
  for (let index = 0; index <= steps; index++) {
    const progress = index / steps;
    const pose = orbitView(fitRadius, progress);
    const forward = normalize(subtract(pose.target, pose.position));
    const right = normalize(cross(forward, [0, 1, 0]));
    const up = cross(right, forward);
    const bounds = { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity };
    for (const [x, z] of projected) {
      for (const y of [0, 1.8]) {
        const relative = subtract([x, y, z], pose.position);
        const depth = dot(relative, forward);
        const ndcX = dot(relative, right) / (depth * tanV * aspect);
        const ndcY = dot(relative, up) / (depth * tanV);
        const margin = depth > 0 ? 1 - Math.max(Math.abs(ndcX), Math.abs(ndcY)) : -Infinity;
        minMargin = Math.min(minMargin, margin);
        if (index === steps) {
          bounds.minX = Math.min(bounds.minX, ndcX); bounds.maxX = Math.max(bounds.maxX, ndcX);
          bounds.minY = Math.min(bounds.minY, ndcY); bounds.maxY = Math.max(bounds.maxY, ndcY);
        }
      }
    }
    if (index === steps) finalBounds = Object.fromEntries(Object.entries(bounds).map(([axis, value]) => [axis, round(value)]));
    if (progress <= 0.60) maxGridReach = Math.max(maxGridReach, groundReach(pose, aspect) / radius);
  }
  if (minMargin <= 0 || maxGridReach > 6) throw new Error(`${name} responsive path failed: ${JSON.stringify({ minMargin, maxGridReach })}`);
  responsiveCases.push({ name, canvasWidth: width, canvasHeight: height, aspect: round(aspect), actualRadius: round(radius), fittedRadius: round(fitRadius), fitFactor: round(fitRadius / radius), minFrustumMargin: round(minMargin), maxGridReachWhileVisibleInActualRadii: round(maxGridReach), finalProjectedBounds: finalBounds, finalMapPixelWidth: round((finalBounds.maxX - finalBounds.minX) * width / 2), finalMapPixelHeight: round((finalBounds.maxY - finalBounds.minY) * height / 2), endpointStrictlyEqualsProvinceView: JSON.stringify(orbitView(fitRadius, 1)) === JSON.stringify(provinceView(fitRadius)) });
}
const keyProgress = [0, 0.04, 0.18, 0.18 + 0.70 / 4, 0.53, 0.18 + 0.70 * 3 / 4, 0.88, 1];
const keyframes = keyProgress.map((progress) => ({ progress, timeMs: round(progress * OPENING_DURATION_MS), stage: openingStageForProgress(progress).stage, ...roundedPose(orbitView(radius, progress)) }));
const report = {
  generatedFor: 'AgriScope V4 Phase 3', modelSource: 'frontend/public/geo/liaoning.json', mapSha256: createHash('sha256').update(mapText).digest('hex'),
  cameraSourceSha256: createHash('sha256').update(readFileSync(new URL('../../frontend/src/features/liaoning/cameraViews.ts', import.meta.url))).digest('hex'),
  model: { projectedRadius: round(radius), projectedBoundingBox: { minX: round(Math.min(...xs)), maxX: round(Math.max(...xs)), minZ: round(Math.min(...zs)), maxZ: round(Math.max(...zs)) }, vertexCount: coordinates.length, solidDepth: 1.8 },
  durationMs: OPENING_DURATION_MS, timeline: OPENING_TIMELINE.map((entry) => ({ ...entry, startMs: entry.start * OPENING_DURATION_MS, endMs: entry.end * OPENING_DURATION_MS })),
  sampling: { steps, deltaTimeMs: OPENING_DURATION_MS / steps, interpolator: 'centripetal CatmullRomCurve3 + getPointAt (1200 arc length divisions), per-stage smoothstep' },
  metrics: { accumulatedAzimuthDegrees: round(orbitSpanDegrees(radius)), minCameraClearanceAboveSolid: round(minCameraClearance), minHorizontalRadiusInProvinceRadii: round(minHorizontalRadius), maxSpeedRadiusPerSecond: round(maxSpeed), maxAdjacentSpeedDeltaRadiusPerSecond: round(maxSpeedDelta), minFrustumMargins: Object.fromEntries(Object.entries(margins).map(([name, value]) => [name, round(value)])), maxGroundReachWhileGridVisible: round(maxGroundWhileGridVisible), paperHalfSpan: 6, endpointStrictlyEqualsProvinceView: JSON.stringify(orbitView(radius, 1)) === JSON.stringify(provinceView(radius)) },
  finalProjectionBounds, responsiveCases,
  limitations: ['Projection checks desktop and phone/tablet frustums with actual 1.8-depth map geometry. Production Opening/province share the compact Canvas stage.', 'No browser screenshot or video is claimed by this mathematical proof.', 'Per-stage speed easing deliberately accelerates/decelerates; the arc length sampler removes control-point density speed jumps.'],
  keyframes, samples,
};
if (Math.abs(report.metrics.accumulatedAzimuthDegrees - 360) > 0.001 || minCameraClearance <= 0 || Object.values(margins).some((margin) => margin <= 0) || maxGroundWhileGridVisible > 6 || maxSpeed > 8 || maxSpeedDelta > 0.3 || !report.metrics.endpointStrictlyEqualsProvinceView) throw new Error(`Camera path failed proof: ${JSON.stringify(report.metrics)}`);
const out = (name) => new URL(name, import.meta.url);
writeFileSync(out('CAMERA_PATH_SAMPLES.json'), `${JSON.stringify(report, null, 2)}\n`);

const width = 1200;
const height = 840;
const plot = { x: 78, y: 92, width: 650, height: 650 };
const extent = 3.45;
const screen = (x, z) => [plot.x + plot.width / 2 + x / extent * plot.width / 2, plot.y + plot.height / 2 + z / extent * plot.height / 2];
const line = (points) => points.map((point) => point.map((n) => n.toFixed(2)).join(',')).join(' ');
const cameraPoints = samples.map((sample) => screen(sample.normalizedPose.position[0], sample.normalizedPose.position[2]));
const targetPoints = samples.map((sample) => screen(sample.normalizedPose.target[0], sample.normalizedPose.target[2]));
const paths = geo.features.flatMap((feature) => {
  const polygons = feature.geometry?.type === 'MultiPolygon' ? feature.geometry.coordinates : [feature.geometry?.coordinates];
  return polygons.filter(Boolean).map((polygon) => polygon[0].map(([lng, lat]) => screen((lng - centerLng) * Math.cos(centerLat * Math.PI / 180) * 11 / radius, -(lat - centerLat) * 11 / radius)));
});
const groupedMarks = [];
keyframes.forEach((frame, index) => {
  const [x, y] = screen(frame.position[0] / radius, frame.position[2] / radius);
  const existing = groupedMarks.find((mark) => Math.hypot(mark.x - x, mark.y - y) < 0.01);
  if (existing) existing.labels.push(index + 1);
  else groupedMarks.push({ x, y, labels: [index + 1] });
});
const marks = groupedMarks.map(({ x, y, labels }) => `<circle cx="${x}" cy="${y}" r="5" fill="#a06144"/><text x="${x + 10}" y="${y - 9}" class="label">${labels.join('/')}</text>`).join('');
const altitudePlot = { x: 810, y: 405, width: 315, height: 190 };
const profile = line(samples.map((sample) => [altitudePlot.x + sample.progress * altitudePlot.width, altitudePlot.y + altitudePlot.height - sample.normalizedPose.position[1] / 4.1 * altitudePlot.height]));
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="AgriScope Opening camera path proof">
<rect width="1200" height="840" fill="#f4f1e8"/><style>text{font-family:system-ui,sans-serif;fill:#2b3029}.title{font-size:25px;font-weight:600}.subtitle{font-size:15px;fill:#626c5e}.label{font-size:13px}.small{font-size:12px;fill:#626c5e}.metric{font-size:17px;font-weight:600}</style>
<text x="60" y="42" class="title">AgriScope · Opening 相机轨迹证明</text><text x="60" y="70" class="subtitle">真实辽宁几何 · 相机完整环绕 360° · ${OPENING_DURATION_MS / 1000}s · 721 个采样位姿</text>
<rect x="${plot.x}" y="${plot.y}" width="650" height="650" fill="#fbf9f2" stroke="#d8d7cb"/><path d="M403 92V742M78 417H728" stroke="#deded3"/>
${paths.map((points) => `<polygon points="${line(points)}" fill="#d1d6c5" stroke="#828d75" stroke-width="0.55"/>`).join('')}
<polyline points="${line(cameraPoints)}" fill="none" stroke="#a06144" stroke-width="2.7"/><polyline points="${line(targetPoints)}" fill="none" stroke="#325b59" stroke-width="3"/><circle cx="403" cy="417" r="5" fill="#325b59"/>${marks}
<text x="392" y="83" class="label">N / −Z</text><text x="392" y="762" class="label">S / +Z</text><text x="735" y="422" class="label">+X</text>
<text x="810" y="120" class="metric">累计方位：${report.metrics.accumulatedAzimuthDegrees}°</text><text x="810" y="154" class="metric">最低相机离地块：${report.metrics.minCameraClearanceAboveSolid}</text><text x="810" y="180" class="small">地图世界半径 r = ${report.model.projectedRadius}</text><text x="810" y="211" class="metric">最小画面留边：${(Math.min(...Object.values(margins)) * 100).toFixed(1)}%</text><text x="810" y="237" class="small">实地图顶面与底面，全桌面比例逐点投影</text><text x="810" y="268" class="metric">末帧严格 = provinceView(r)</text>
<text x="810" y="310" class="label">红：Camera Position 顶视轨迹</text><text x="810" y="336" class="label">绿：独立 Target（X/Z 固定省域中心）</text><text x="810" y="378" class="label">相机高度（r）/ 线性时间</text>
<path d="M810 405V595H1125" fill="none" stroke="#b2b6a9"/><polyline points="${profile}" fill="none" stroke="#a06144" stroke-width="2"/><text x="807" y="616" class="small">0s</text><text x="1088" y="616" class="small">4.8s</text>
<text x="810" y="660" class="label">1–2 图纸；3 组装落位；4–6 环省飞行</text><text x="810" y="686" class="label">7 闭合回位；8 上升接正式机位</text><text x="60" y="810" class="small">数学轨迹验证；浏览器关键帧与录屏另行验收。可复建：node docs/v4/CAMERA_PATH_PROOF.mjs</text>
</svg>`;
writeFileSync(out('CAMERA_PATH_PROOF.svg'), svg);
const summary = `# Camera Path Proof\n\n轨迹已通过数学采样，浏览器关键帧与录屏仍需在实际场景验收。\n\n- 采用 three 已安装的 centripetal CatmullRomCurve3 + getPointAt（1200 段弧长表），不新增依赖。\n- 统一线性时间轴 4800ms；分段导演内部 smoothstep；相机 Position 与 Target 独立。\n- 图纸 0–192ms；组装/下降 192–864ms；完整环省 864–4224ms；上升落位 4224–4800ms。\n- 累计展开方位 ${report.metrics.accumulatedAzimuthDegrees}°，不是误用首尾角差。\n- 实际地图半径 ${report.model.projectedRadius}、${coordinates.length} 顶点；每个采样对 1.8 深度顶/底面与 5 个桌面比例检查。\n- 最低相机高于地块 ${report.metrics.minCameraClearanceAboveSolid}；最低水平半径 ${report.metrics.minHorizontalRadiusInProvinceRadii}r（高俯视开场）。\n- 最小画面留边 ${(Math.min(...Object.values(margins)) * 100).toFixed(2)}%；全体地图顶点在画面内。\n- 最大速度 ${report.metrics.maxSpeedRadiusPerSecond}r/s；相邻 6.667ms 采样的最大速度差 ${report.metrics.maxAdjacentSpeedDeltaRadiusPerSecond}r/s。分段故意缓入缓出，未把整段速度伪称常速。\n- 网格可见时，21:9 地面最大覆盖半径 ${report.metrics.maxGroundReachWhileGridVisible}r ≤ 6r 纸面。\n- 最后一帧 JSON 与 provinceView(radius) 严格相等；省域根节点 Y rotation=0。\n\n关键位姿与全量时间/target/速度/投影采样见 CAMERA_PATH_SAMPLES.json；顶视与高度证明见 CAMERA_PATH_PROOF.svg。\n\n窄屏最终 fit 由父场景统一增加相机距离，不在此数学证明中宣称已完成移动端视觉验收。\n\n复建：在项目根目录运行 node docs/v4/CAMERA_PATH_PROOF.mjs（Node 24，直接读取实际产品 TS 轨迹与真实 GeoJSON）。\n`;
writeFileSync(out('CAMERA_PATH_PROOF.md'), summary);
console.log(JSON.stringify({ responsiveCases, files: ['CAMERA_PATH_PROOF.svg', 'CAMERA_PATH_SAMPLES.json', 'CAMERA_PATH_PROOF.md'].map((name) => fileURLToPath(out(name))), metrics: report.metrics }, null, 2));
