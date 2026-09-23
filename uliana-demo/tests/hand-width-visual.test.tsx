import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { HandWidthComparison, type HandWidthVisual } from "../components/mobile-video-review";
import { handWidthGuideXs } from "../components/review-overlay";

const visual: HandWidthVisual = {
  shoulder_width_cm: 42,
  hand_width_cm: 48,
  deviation_cm: 6,
  classification: "slightly wide",
  expected_shoulders: { left_x: .3, right_x: .7 },
};

test("comparison bars scale to the larger measurement", () => {
  const html = renderToStaticMarkup(<HandWidthComparison result={visual} />);
  assert.match(html, /Hand width comparison/);
  assert.match(html, /width:100%/);
  assert.match(html, /width:87.5%/);
  assert.match(html, /6 cm wider than shoulders/);
  assert.match(html, /hand-width-comparison-slightly/);
});

test("comparison omits bars when hand width is unavailable", () => {
  const html = renderToStaticMarkup(<HandWidthComparison result={{ ...visual, hand_width_cm: null }} />);
  assert.match(html, /Hand width: not assessed/);
  assert.doesNotMatch(html, /hand-width-bar-row/);
});

test("video guide positions follow the measured hand-to-shoulder ratio", () => {
  const guides = handWidthGuideXs(visual);
  assert.ok(guides);
  assert.equal(guides.leftShoulder, .3);
  assert.equal(guides.rightShoulder, .7);
  assert.ok(Math.abs(guides.leftHand - .27143) < .00001);
  assert.ok(Math.abs(guides.rightHand - .72857) < .00001);
  assert.equal(handWidthGuideXs({ ...visual, hand_width_cm: null }), null);
});
