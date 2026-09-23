import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { heatmapZones, MatVisualization, SENSOR_LAYOUT } from "../components/mat-visualization";
import { HandWidthStatus, type HandWidthResult } from "../components/mobile-sensor";

type Readings = Parameters<typeof heatmapZones>[1];

function readings(active: number[]): Readings {
  return Object.fromEntries(SENSOR_LAYOUT.map(sensor => [sensor.channel, {
    raw: 980, delta: 0, hand: active.includes(sensor.channel),
  }])) as Readings;
}

function markup(active: number[]): string {
  return renderToStaticMarkup(<MatVisualization sensors={SENSOR_LAYOUT} channelData={readings(active)} baselineSet />);
}

test("zero active sensors leave both halves green", () => {
  assert.deepEqual(heatmapZones(SENSOR_LAYOUT, readings([])).map(zone => zone.kind), ["none", "none"]);
  const html = markup([]);
  assert.match(html, /fill="#4CAF50"/);
  assert.doesNotMatch(html, /<circle|<line|<polygon/);
});

test("one active sensor draws an orange gradient only in its half", () => {
  assert.deepEqual(heatmapZones(SENSOR_LAYOUT, readings([8])).map(zone => zone.kind), ["one", "none"]);
  const html = markup([8]);
  assert.match(html, /<circle[^>]+fill="url\(#/);
  assert.match(html, /stop-color="#FF9800"/);
  assert.doesNotMatch(html, /<line|<polygon/);
});

test("two active sensors in one half draw a red bridge", () => {
  assert.deepEqual(heatmapZones(SENSOR_LAYOUT, readings([8, 9])).map(zone => zone.kind), ["many", "none"]);
  const html = markup([8, 9]);
  assert.match(html, /<line[^>]+stroke="url\(#/);
  assert.match(html, /stop-color="#E53935"/);
});

test("three active sensors draw a red convex hull", () => {
  const html = markup([11, 12, 8]);
  assert.match(html, /<polygon[^>]+fill="#E53935"/);
});

test("one active sensor in each half draws separate orange zones", () => {
  assert.deepEqual(heatmapZones(SENSOR_LAYOUT, readings([8, 5])).map(zone => zone.kind), ["one", "one"]);
  const html = markup([8, 5]);
  assert.equal((html.match(/<circle/g) ?? []).length, 2);
  assert.doesNotMatch(html, /<line|<polygon/);
  assert.equal((html.match(/data-group="(left|right)"/g) ?? []).length, 2);
});

test("missing calibration does not display a false green or active zone", () => {
  const html = renderToStaticMarkup(<MatVisualization sensors={SENSOR_LAYOUT} channelData={readings([8])} baselineSet={false} />);
  assert.match(html, /fill="#808080"/);
  assert.doesNotMatch(html, /<circle|<line|<polygon/);
  assert.match(html, /Waiting for calibrated sensor activity/);
});

test("every channel uses the supplied coordinates and its own hand flag", () => {
  const expected = new Map<number, [number, number, string]>([
    [13, [25, 10, "left"]], [15, [12, 30, "left"]], [9, [38, 30, "left"]],
    [14, [12, 50, "left"]], [8, [38, 50, "left"]], [10, [12, 70, "left"]],
    [12, [38, 70, "left"]], [11, [25, 90, "left"]],
    [1, [75, 10, "right"]], [4, [62, 30, "right"]], [0, [88, 30, "right"]],
    [7, [62, 50, "right"]], [2, [88, 50, "right"]], [6, [62, 70, "right"]],
    [3, [88, 70, "right"]], [5, [75, 90, "right"]],
  ]);
  assert.equal(SENSOR_LAYOUT.length, 16);
  for (const sensor of SENSOR_LAYOUT) {
    assert.deepEqual([sensor.x, sensor.y, sensor.group], expected.get(sensor.channel));
    const html = renderToStaticMarkup(<MatVisualization sensors={SENSOR_LAYOUT} channelData={readings([sensor.channel])} baselineSet onSensorClick={() => {}} />);
    const active = html.match(/<button[^>]*class="sensor-mat-dot sensor-mat-active"[^>]*>/g) ?? [];
    assert.equal(active.length, 1, `C${sensor.channel} should be the only active marker`);
    assert.match(active[0], new RegExp(`left:${sensor.x}%;top:${sensor.y}%`));
    assert.match(active[0], new RegExp(`aria-label="C${sensor.channel}:`));
    const zone = heatmapZones(SENSOR_LAYOUT, readings([sensor.channel]));
    assert.deepEqual(zone.find(item => item.group === sensor.group)?.points, [{ x: sensor.x, y: sensor.y / 2 }]);
  }
});

test("groups stay in their halves and markers do not overlap", () => {
  assert.ok(SENSOR_LAYOUT.filter(sensor => sensor.group === "left").every(sensor => sensor.channel >= 8 && sensor.x >= 5 && sensor.x <= 45));
  assert.ok(SENSOR_LAYOUT.filter(sensor => sensor.group === "right").every(sensor => sensor.channel <= 7 && sensor.x >= 55 && sensor.x <= 95));
  for (let first = 0; first < SENSOR_LAYOUT.length; first += 1) {
    for (let second = first + 1; second < SENSOR_LAYOUT.length; second += 1) {
      const a = SENSOR_LAYOUT[first];
      const b = SENSOR_LAYOUT[second];
      const distance = Math.hypot(a.x - b.x, (a.y - b.y) / 2);
      assert.ok(distance > 9, `C${a.channel} and C${b.channel} are only ${distance.toFixed(1)}% apart`);
    }
  }
});

test("active heatmap is clipped away from the central 45–55% gap", () => {
  const html = markup(SENSOR_LAYOUT.map(sensor => sensor.channel));
  assert.match(html, /<clipPath[^>]*><rect x="5" y="0" width="40" height="50"><\/rect><\/clipPath>/);
  assert.match(html, /<clipPath[^>]*><rect x="55" y="0" width="40" height="50"><\/rect><\/clipPath>/);
  assert.match(html, /data-group="left" clip-path="url\(#.+-left\)"/);
  assert.match(html, /data-group="right" clip-path="url\(#.+-right\)"/);
});

test("shoulder guides use normalized x positions", () => {
  const html = renderToStaticMarkup(<MatVisualization sensors={SENSOR_LAYOUT} channelData={readings([])} baselineSet expectedShoulders={{ left_x: .3, right_x: .7 }} />);
  assert.match(html, /<line x1="30" y1="0" x2="30" y2="50"><\/line>/);
  assert.match(html, /<line x1="70" y1="0" x2="70" y2="50"><\/line>/);
  assert.match(html, /Shoulder L/);
  assert.match(html, /Shoulder R/);
});

test("hand width status formats classification and disagreement", () => {
  const result: HandWidthResult = { hand_width_cm: 48, deviation_cm: 6, classification: "slightly wide", sensor_camera_agree: false, expected_shoulders: null };
  const html = renderToStaticMarkup(<HandWidthStatus result={result} />);
  assert.match(html, /Hand width: 48 cm \(6 cm wider than shoulders\)/);
  assert.match(html, /hand-width-slightly/);
  assert.match(html, /Camera and sensor disagree/);
  assert.match(renderToStaticMarkup(<HandWidthStatus result={null} />), /Hand width: not assessed/);
});
