export function getAudioCueText(criterion: string, state: string): string | null {
  if (state === "not_assessed" || state === "unavailable") return null;
  if (state === "consistent" || state === "adequate") return "Your body line looked consistent.";
  if (criterion === "body_alignment_review" || criterion === "body_alignment_deviation") return "Keep your hips in line.";
  if (criterion === "body_alignment_review_alt") return "Brace your core and keep your body straight.";
  if (criterion === "range_of_motion_review" || criterion === "push_up_depth_proxy") return "Lower until your elbows reach about ninety degrees.";
  if (criterion === "range_of_motion_review_alt") return "Try to go a little deeper next time.";
  return null;
}
