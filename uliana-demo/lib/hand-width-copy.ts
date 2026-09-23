export type HandWidthClassification = "aligned" | "slightly wide" | "slightly narrow" | "too wide" | "too narrow";

export type HandWidthChatResult = {
  hand_width_cm: number | null;
  deviation_cm: number | null;
  classification: HandWidthClassification | null;
};

export function handWidthCoachMessage(result: HandWidthChatResult | null): string | null {
  if (!result || result.hand_width_cm === null || result.deviation_cm === null || result.classification === null) return null;
  const difference = Math.abs(result.deviation_cm);
  switch (result.classification) {
    case "aligned": return "Hand width is aligned with your shoulders.";
    case "slightly wide": return `Hand width is ${difference} cm wider than your shoulders. Try bringing hands slightly closer.`;
    case "slightly narrow": return `Hand width is ${difference} cm narrower than your shoulders. Try widening your hands slightly.`;
    case "too wide": return `Hands are significantly wider than shoulders (${difference} cm). Bring them closer to shoulder width.`;
    case "too narrow": return `Hands are significantly narrower than shoulders (${difference} cm). Widen them to shoulder width.`;
  }
}
