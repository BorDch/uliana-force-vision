"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { getAudioCueText } from "@/lib/audio-cues";

export type ReviewAssessment = { condition: string; result: string; reason?: string; evidence?: Record<string, unknown> };
export function explainReview(assessment?: ReviewAssessment) {
  if (!assessment || assessment.result !== "condition_detected") return null;
  const duration = assessment.evidence?.longest_persistent_duration_ms;
  const seconds = typeof duration === "number" && Number.isFinite(duration) ? `${(duration / 1000).toFixed(1)} seconds` : null;
  if (assessment.condition === "body_alignment_deviation") return {
    issue: "Body alignment moved outside the assessed range.",
    evidence: seconds ? `The visible body line remained outside the current alignment range for ${seconds}.` : "The visible body line moved outside the current alignment range.",
    action: "Keep shoulders, hips and ankles aligned.", cue: getAudioCueText(assessment.condition, assessment.result)
  };
  if (assessment.condition === "push_up_depth_proxy") return {
    issue: "Range of motion needs review.", evidence: "The visible elbow angle near the bottom was outside the assessed range.",
    action: "Lower through a controlled range that suits your set.", cue: getAudioCueText(assessment.condition, assessment.result)
  };
  return null;
}

// Cache generated audio by its short cue text for this page session.
const audioCache = new Map<string, Promise<string>>();
function audioUrl(text: string, sessionId: string): Promise<string> {
  const existing = audioCache.get(text);
  if (existing) return existing;
  const pending = apiFetch("/api/tts/synthesize", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, voice: "af_heart", session_id: sessionId }),
  }).then(async response => {
    if (!response.ok) throw new Error("Audio unavailable");
    return URL.createObjectURL(await response.blob());
  }).catch(error => { audioCache.delete(text); throw error; });
  audioCache.set(text, pending);
  return pending;
}

export function AudioReviewCue({ cue, momentKey, sessionId, video, targetMs }: { cue: string | null; momentKey: string; sessionId: string; video: HTMLVideoElement | null; targetMs: number }) {
  const [enabled, setEnabled] = useState(false);
  const [error, setError] = useState("");
  const played = useRef<string | null>(null);
  const player = useRef<HTMLAudioElement | null>(null);
  const play = useCallback(async () => {
    if (!cue || video?.muted) return;
    try {
      const url = await audioUrl(cue, sessionId);
      player.current?.pause();
      player.current = new Audio(url);
      await player.current.play();
      setError("");
    } catch { setError("Audio unavailable"); }
  }, [cue, sessionId, video]);
  useEffect(() => {
    if (!video || !enabled || !cue) return;
    const enter = () => {
      if (played.current === momentKey || Math.abs(video.currentTime * 1000 - targetMs) > 700) return;
      if (video.muted || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      played.current = momentKey;
      void play();
    };
    video.addEventListener("timeupdate", enter);
    return () => video.removeEventListener("timeupdate", enter);
  }, [video, enabled, cue, momentKey, targetMs, play]);
  useEffect(() => () => { player.current?.pause(); }, []);
  return <div className="audio-review"><label><input type="checkbox" checked={enabled} onChange={event => { setEnabled(event.target.checked); if (!event.target.checked) player.current?.pause(); }} /> Audio cue during review</label><button type="button" onClick={() => void play()} disabled={!enabled || !cue || video?.muted}>Play audio cue</button>{error && <span role="alert">{error}</span>}</div>;
}
