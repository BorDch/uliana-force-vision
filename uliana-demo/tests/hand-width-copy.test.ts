import assert from "node:assert/strict";
import { test } from "node:test";
import { handWidthCoachMessage, type HandWidthChatResult } from "../lib/hand-width-copy";

const result = (classification: HandWidthChatResult["classification"], deviation_cm: number): HandWidthChatResult => ({
  hand_width_cm: 48,
  deviation_cm,
  classification,
});

test("hand width chat copy covers every classification", () => {
  assert.equal(handWidthCoachMessage(result("aligned", 1)), "Hand width is aligned with your shoulders.");
  assert.equal(handWidthCoachMessage(result("slightly wide", 6)), "Hand width is 6 cm wider than your shoulders. Try bringing hands slightly closer.");
  assert.equal(handWidthCoachMessage(result("slightly narrow", -5)), "Hand width is 5 cm narrower than your shoulders. Try widening your hands slightly.");
  assert.equal(handWidthCoachMessage(result("too wide", 12)), "Hands are significantly wider than shoulders (12 cm). Bring them closer to shoulder width.");
  assert.equal(handWidthCoachMessage(result("too narrow", -10)), "Hands are significantly narrower than shoulders (10 cm). Widen them to shoulder width.");
});

test("hand width chat copy is omitted without an assessment", () => {
  assert.equal(handWidthCoachMessage(null), null);
  assert.equal(handWidthCoachMessage({ hand_width_cm: null, deviation_cm: null, classification: null }), null);
});
