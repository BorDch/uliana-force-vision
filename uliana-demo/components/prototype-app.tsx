"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  BarChart3,
  Camera,
  Check,
  ChevronRight,
  CircleAlert,
  Download,
  Play,
  RotateCcw,
  Trash2,
  Upload,
} from "lucide-react";
import { mobileCopy } from "@/lib/mobile-copy";
import { AudioReviewCue, explainReview, HandWidthComparison, type HandWidthVisual } from "@/components/mobile-video-review";
import { ReviewOverlay, reviewSeekMs, type ReviewMoment } from "@/components/review-overlay";
import { apiFetch } from "@/lib/api";
import { getAudioCueText } from "@/lib/audio-cues";
import { LiveChatControls } from "@/components/mobile-live-session";
import { handWidthCoachMessage, type HandWidthChatResult } from "@/lib/hand-width-copy";

type Mode = "select" | "pushup" | "pullup" | "processing" | "session" | "progress" | "demo";
type Interval = { rep_id: number; start_ms: number; bottom_ms?: number; end_ms: number; confidence?: number };
type Assessment = { condition: string; result: string; reason?: string; rep_id?: number; confidence?: number; evidence?: Record<string, unknown> };
type CriterionCard = { criterion_id: string; criterion_name: string; rep_id?: number; result: string; status_label: string; reason?: string; interval?: Interval; measurements: Array<{ name: string; value: number; unit: string }>; threshold?: unknown; measurement_definition: string; limitation?: string; reference_ids: string[]; validation_status: string };
type FeedbackReport = { assessment_policy_version: string; feedback_policy_version: string; count_summary: { count: number | null; available: boolean; message: string; limitation: string }; coverage: { answered: number | null; eligible: number | null; fraction: number; definition: string }; primary_observation: { criterion_id: string; title: string; explanation: string; action: string; rep_id?: number; interval?: Interval }; supporting_observations: string[]; next_steps: string[]; criterion_cards: CriterionCard[]; unsupported_criteria: Array<{ criterion_id: string; label: string; reason: string }>; references: Array<{ id: string; citation: string; doi: string; supports: string; does_not_support: string }>; limitations: string[] };
type CoachSummary = { headline: string; summary: string; what_went_well: string; main_focus: string; next_session_plan: [string, string]; comparison_summary: string };
type SessionResult = { exercise_type?: string; session_id: string; profile_id?: string; exercise?: string; exercise_variation?: string; created_at?: string; status: string; repetition_count?: number | null; partial_movements?: number; duration_seconds?: number | null; overall_assessment_coverage?: number; detected_viewpoint?: { value: string; confidence?: number; reason?: string }; repetition_intervals?: Interval[]; assessments?: Assessment[]; warnings?: string[]; source_video_url?: string; annotated_video_url?: string; error?: string; feedback_report?: FeedbackReport; coach_summary?: CoachSummary };

const SUPPORTED = ["body_alignment_deviation", "push_up_depth_proxy"] as const;
const EXPERIMENTAL = ["head_neck_alignment", "elbow_to_torso_flare", "hand_placement"] as const;
const isSupported = (item: Assessment) => SUPPORTED.includes(item.condition as (typeof SUPPORTED)[number]);
const supportedAssessments = (result: SessionResult) => (result.assessments ?? []).filter(isSupported);
const criterionLabel = (id: string) => ({ body_alignment_deviation: "Body alignment", push_up_depth_proxy: "Range of motion", head_neck_alignment: "Head position", elbow_to_torso_flare: "Elbow-to-torso flare", hand_placement: "Hand placement" }[id] ?? pretty(id));
const beginnerCriterion = (id: string) => ({ body_alignment_deviation: "Keep your body in one straight line", push_up_depth_proxy: "How far you lowered" }[id] ?? criterionLabel(id));
const shortCriterion = (id: string) => ({ body_alignment_deviation: "Alignment", push_up_depth_proxy: "Lowering range" }[id] ?? criterionLabel(id));

const API = process.env.NEXT_PUBLIC_API_BASE ?? "";
const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const staticDemo = process.env.NEXT_PUBLIC_STATIC_DEMO === "1";
const screenPath = (value: string) => {
  const [route, query = ""] = value.split("?");
  const screens: Record<string, string> = { "/app": "app", "/record/push-up": "pushup", "/record/pull-up": "pullup", "/processing": "processing", "/session": "session", "/progress": "progress", "/demo": "demo" };
  return screens[route] ? `${base}/?screen=${screens[route]}${query ? `&${query}` : ""}` : `${base}${route}`;
};
const pretty = (value: string) => value.replaceAll("_", " ").replace(/^./, (x) => x.toUpperCase());
const stamp = (ms?: number) => (ms == null ? "—" : `${(ms / 1000).toFixed(1)} s`);
const dateLabel = (value?: string) => {
  if (!value || value.startsWith("Pre-recorded")) return value ?? "Date unavailable";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
};
export const plural = (count: number, singular: string, pluralForm = `${singular}s`) => `${count} ${count === 1 ? singular : pluralForm}`;
const median = (values: number[]) => {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};
const repDuration = (rep: Interval) => Math.max(0, rep.end_ms - rep.start_ms) / 1000;
const reviewIds = (result: SessionResult, criterion?: string) => new Set(supportedAssessments(result).filter((item) => (!criterion || item.condition === criterion) && item.result === "condition_detected" && item.rep_id != null).map((item) => item.rep_id as number));
const unavailable = (result: SessionResult) => supportedAssessments(result).filter((item) => item.result === "unavailable");
const assessedCriteria = (result: SessionResult) => SUPPORTED.filter((criterion) => supportedAssessments(result).some((item) => item.condition === criterion && item.result !== "unavailable")).length;
const medianDuration = (result: SessionResult) => median((result.repetition_intervals ?? []).map(repDuration));
const compatible = (a: SessionResult, b: SessionResult) => (a.profile_id ?? "local-default") === (b.profile_id ?? "local-default") && a.exercise === b.exercise && (a.exercise_type ?? "standard") === (b.exercise_type ?? "standard") && (a.exercise_variation ?? "standard") === (b.exercise_variation ?? "standard") && Boolean(a.detected_viewpoint?.value && a.detected_viewpoint.value === b.detected_viewpoint?.value);
const visibilityIssue = (result: SessionResult) => unavailable(result).some((item) => /visibility|landmark|view|body/i.test(item.reason ?? "")) || (result.warnings ?? []).some((item) => /visibility|framing|occlusion|body/i.test(item));
const boundaryIssue = (result: SessionResult) => Boolean(result.partial_movements) || (result.warnings ?? []).some((item) => /boundary|partial|incomplete|start|end/i.test(item));

const smartMatCriteria = ["Hand-pressure distribution", "Left/right load balance", "Contact position"];

function useHistory() {
  const [items, setItems] = useState<SessionResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const load = () => fetch(`${API}/api/sessions`)
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((data) => {
        const sessions = ((data as { sessions?: SessionResult[] }).sessions) ?? [];
        setItems(sessions);
        if (sessions.some((item) => !["completed","failed"].includes(item.status))) timer=setTimeout(load,1800);
      })
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
    load(); return ()=>clearTimeout(timer);
  }, []);
  return { items, loading, failed };
}

function Shell({ mode, title, children, appOnly = false, latestId }: { mode: Mode; title?: string; children: React.ReactNode; appOnly?: boolean; latestId?: string }) {
  const [runtimeAppOnly, setRuntimeAppOnly] = useState(appOnly);
  const [runtimeMobile, setRuntimeMobile] = useState(false);
  useEffect(() => {
    if (staticDemo) return;
    fetch("/api/runtime").then(async (response) => await response.json() as {mode?: string}).then((runtime) => { setRuntimeAppOnly(runtime.mode === "app" || runtime.mode === "mobile"); setRuntimeMobile(runtime.mode === "mobile"); }).catch(() => undefined);
  }, [appOnly]);
  appOnly = runtimeAppOnly;
  return <main id="main" className="proto-page">
    <header className="proto-header"><a href={screenPath(appOnly ? "/app" : "/")} className="proto-brand">ULIANA<span>·</span></a><nav>{staticDemo ? <><a href={screenPath("/")}>Back to landing page</a><a href={screenPath("/demo")}>Prepared sample</a></> : appOnly ? <><a href={screenPath("/app")}>{runtimeMobile ? "Coach" : "Train"}</a>{latestId && !runtimeMobile && <a href={screenPath(`/session?id=${latestId}`)}>Latest result</a>}<a href={screenPath("/progress")}>{runtimeMobile ? "My sessions" : "Progress"}</a>{runtimeMobile && <Link href="/?screen=sensor">Experimental sensor</Link>}</> : <><a href={screenPath("/app")}>Start</a><a href={screenPath("/progress")}>Progress</a><a href={screenPath("/demo")}>Presentation mode</a></>}</nav></header>
    <div className="journey">{["Record your set", "Review your technique", "Track your progress"].map((item, index) => <span key={item} className={(mode === "select" || mode === "pushup" || mode === "pullup" ? index === 0 : mode === "progress" ? index === 2 : index === 1) ? "active" : ""}>{index + 1}. {item}</span>)}</div>
    {title && <div className="proto-title"><a href={screenPath("/app")} aria-label="Back to start"><ArrowLeft /></a><h1>{title}</h1></div>}
    {children}
  </main>;
}

export function PrototypeApp({ mode, appOnly = false, mobile = false }: { mode: Mode; appOnly?: boolean; mobile?: boolean }) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  const [exerciseType, setExerciseType] = useState("standard");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(() => typeof window !== "undefined" && (mode === "processing" || mode === "session") && !new URLSearchParams(location.search).get("id") ? "Session link is incomplete." : "");
  const [result, setResult] = useState<SessionResult | null>(null);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);
  useEffect(() => {
    if (mode !== "processing" && mode !== "session") return;
    const id = new URLSearchParams(location.search).get("id");
    if (!id) return;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const response = await fetch(`${API}/api/sessions/${id}/${mode === "session" ? "result" : "status"}`);
        if (!response.ok) throw new Error("Session could not be loaded.");
        const data = await response.json() as SessionResult;
        setResult(data);
        if (mode === "processing" && data.status === "completed") location.href = screenPath(`/session?id=${id}`);
        else if (mode === "processing" && data.status !== "failed") timer = setTimeout(poll, 1400);
      } catch (caught) { setError(caught instanceof TypeError ? mobileCopy.unavailable : caught instanceof Error ? caught.message : "Session could not be loaded."); }
    };
    void poll();
    return () => clearTimeout(timer);
  }, [mode]);

  const choose = (selected?: File) => {
    if (!selected) return;
    if (!selected.type.startsWith("video/") && !/\.(mov|mp4|m4v|webm)$/i.test(selected.name)) return setError("Choose a supported MOV, MP4, M4V, or WebM video.");
    if (selected.size > 500 * 1024 * 1024) return setError("This video is larger than the 500 MB demo limit.");
    if (preview) URL.revokeObjectURL(preview);
    setFile(selected); setPreview(URL.createObjectURL(selected)); setError("");
  };
  const analyse = async (exercise: "push-up" | "pull-up") => {
    if (!file || !consent || busy) return;
    setBusy(true); setError("");
    try {
      const created = await apiFetch(`${API}/api/sessions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ exercise, consent: true, exercise_variation: "standard", exercise_type: exercise === "push-up" ? exerciseType : "standard" }) });
      if (!created.ok) throw new Error("Could not create a local session.");
      const session = await created.json() as { session_id: string };
      const body = new FormData(); body.append("video", file);
      const uploaded = await apiFetch(`${API}/api/sessions/${session.session_id}/video`, { method: "POST", body });
      if (!uploaded.ok) throw new Error(((await uploaded.json()) as { detail?: string }).detail ?? "Upload failed.");
      if (exercise === "push-up") {
        const started = await apiFetch(`${API}/api/sessions/${session.session_id}/analyse`, { method: "POST" });
        if (!started.ok) throw new Error("Analysis could not be started.");
        location.href = mobile && mode === "select" ? screenPath("/app") : screenPath(`/processing?id=${session.session_id}`);
      } else location.href = screenPath(`/session?id=${session.session_id}`);
    } catch (caught) { setBusy(false); setError(caught instanceof TypeError ? mobileCopy.unavailable : caught instanceof Error ? caught.message : "Upload failed."); }
  };

  if (mode === "select") return mobile ? <MobileCoachHome file={file} preview={preview} consent={consent} setConsent={setConsent} exerciseType={exerciseType} setExerciseType={setExerciseType} choose={choose} analyse={() => void analyse("push-up")} busy={busy} error={error} /> : appOnly ? <AppTrain mobile={mobile} /> : <Shell mode={mode}><section className="start-screen"><div className="start-copy"><p className="eyebrow">Camera-based recorded-session review</p><h1>Review your movement</h1><p className="start-lede">Record a push-up set and receive a camera-based session review.</p><div className="start-actions"><a className="action primary" href={screenPath("/record/push-up")}><Camera /> Record a set</a><a className="action" href={screenPath("/record/push-up")}><Upload /> Upload a video</a></div><a className="demo-link" href={screenPath("/demo")}><Play /> View sample session</a><a className="presentation-link" href={screenPath("/demo")}><BarChart3 /> Presentation mode <ChevronRight /></a></div><aside className="prep-card"><div className="phone-sketch"><img src={`${base}/uliana-studio-poster.webp`} alt="Static side-view push-up camera setup" /></div><h2>Before you record</h2>{["Keep the full body visible", "Place the phone on a stable surface", "Use sufficient lighting"].map((item) => <p key={item}><Check />{item}</p>)}<small>Camera analysis only. Pressure information is unavailable unless real sensor data is connected.</small></aside></section></Shell>;

  if (mode === "pushup" || mode === "pullup") {
    const pull = mode === "pullup";
    const tips = pull ? ["Keep the bar, hands, head, shoulders and hips visible.", "Use a front or slightly oblique view.", "Begin in the lower position and keep the camera still.", "Complete the final movement before stopping."] : ["Place the phone horizontally on a stable surface.", "Use a side or oblique view with your full body visible.", "Start in the upper position and stay still for one second.", "Return to the upper position before stopping."];
    return <Shell mode={mode} title={pull ? "Research recording setup" : "Recording setup"}><section className="capture-grid"><div className="instruction-card"><h2>Camera angle</h2><ol>{tips.map((tip, index) => <li key={tip}><span>{index + 1}</span>{tip}</li>)}</ol></div><div className="capture-card">{!pull && <label className="exercise-type-picker">Push-up type<select value={exerciseType} onChange={event => setExerciseType(event.target.value)}>{Object.entries(PUSH_UP_TYPES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><small>{exerciseType === "standard" ? "Camera analysis available for standard push-ups." : "Not assessed in this version. The video will be saved without technique conclusions."}</small></label>}{preview ? <video className="upload-preview" src={preview} controls playsInline onError={() => setError("This browser could not preview the selected video. Replace it or try another format.")} /> : <div className="empty-video"><Camera /><p>Select a recording to continue.</p><small>MOV, MP4, M4V or WebM · up to 500 MB</small></div>}<div className="capture-actions"><label className="action primary"><Camera /> Record video<input type="file" accept="video/*" capture="environment" onChange={(event) => choose(event.target.files?.[0])} /></label><label className="action"><Upload /> {file ? "Replace video" : "Choose video"}<input type="file" accept="video/*,.mov,.mp4,.m4v,.webm" onChange={(event) => choose(event.target.files?.[0])} /></label></div>{file && <p className="file-name"><Check /> {file.name} · {(file.size / 1048576).toFixed(1)} MB</p>}<label className="consent"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /><span>I agree to upload and process this recording for the ULIANA prototype test.</span></label>{error && <p className="form-error"><CircleAlert />{error}</p>}<button className="analyse-button" disabled={!file || !consent || busy} onClick={() => void analyse(pull ? "pull-up" : "push-up")}>{busy ? "Validating and uploading…" : pull ? "Save research recording" : "Continue to analysis"}</button><p className="privacy-note">The original stays outside public assets and can be deleted with the session.</p></div></section></Shell>;
  }

  if (mode === "processing") {
    const order = ["uploading", "queued", "processing_pose", "counting_repetitions", "rendering_video", "completed"];
    const current = order.indexOf(result?.status ?? "queued");
    const stages = ["Validating video", "Preparing frames", "Detecting movement", "Counting repetitions", "Creating annotated review"];
    const labels: Record<string, string> = { created: "Preparing your recording", uploading: "Validating your video", queued: "Preparing video frames", processing_pose: "Detecting visible movement", counting_repetitions: "Counting complete movement cycles", rendering_video: "Creating your annotated review", failed: "We could not complete this review" };
    const failed = Boolean(error) || result?.status === "failed";
    return <Shell mode={mode} title="Session processing"><section className="status-card">{!failed && <div className="spinner" />}<p className="eyebrow">Recorded-session analysis</p><h1>{failed ? labels.failed : labels[result?.status ?? "queued"]}</h1><p>{failed ? result?.error || error || "The recording could not be processed reliably." : "Longer recordings can take a few minutes. Progress below comes directly from the local pipeline."}</p><div className="stage-list">{stages.map((item, index) => <div key={item} className={current > index ? "done" : current === index ? "active" : ""}><span>{current > index ? <Check /> : index + 1}</span>{item}</div>)}</div>{failed && <div className="error-actions"><a className="action primary" href={screenPath("/record/push-up")}><RotateCcw /> Retry</a><a className="action" href={screenPath("/record/push-up")}>Choose another video</a><a href={screenPath("/record/push-up")}>View recording guidance</a><a href={screenPath("/demo")}>View pre-recorded example</a></div>}</section></Shell>;
  }
  if (mode === "demo") return <Shell mode={mode}><WorkoutReport result={demoResult()} demo /></Shell>;
  if (mode === "session") return <Shell mode={mode}>{result ? result.exercise_type && result.exercise_type !== "standard" ? <UnassessedPushUp result={result} /> : <WorkoutReport result={result} /> : <section className="status-card">{!error&&<div className="spinner" />}<h1>{error?"Session unavailable":"Loading session…"}</h1>{error && <p className="form-error">{error}</p>}</section>}</Shell>;
  if (mode === "progress") return <Shell mode={mode} title="My sessions"><ProgressDashboard /></Shell>;
  return null;
}

function AppTrain({mobile = false}:{mobile?: boolean}) {
  const { items, loading } = useHistory();
  const latest = items.find((item) => item.status === "completed");
  const alignment = latest ? supportedAssessments(latest).filter((item) => item.condition === "body_alignment_deviation") : [];
  const range = latest ? supportedAssessments(latest).filter((item) => item.condition === "push_up_depth_proxy") : [];
  const status = (rows: Assessment[]) => latest?.exercise_type && latest.exercise_type !== "standard" ? "Not assessed in this version." : !rows.some((item) => item.result !== "unavailable") ? "Not assessed: camera angle or landmark quality was insufficient." : rows.some((item) => item.result === "condition_detected") ? "Worth reviewing" : "Looks consistent in this check";
  const insecureLan = typeof window !== "undefined" && !window.isSecureContext && !["localhost", "127.0.0.1"].includes(location.hostname);
  return <Shell mode="select" appOnly latestId={latest?.session_id}><section className={`app-train${mobile ? " mobile-train" : ""}`}>
    <div className="app-train-intro"><p className="eyebrow">Train</p><h1>Analyse today’s workout</h1><p className="app-value">Upload one push-up set. Review one clear moment and take one focus into your next session.</p><div className="workflow-strip" aria-label="How ULIANA works">{["Record", "Analyse", "Review"].map((step, index) => <span key={step}><b>{index + 1}</b>{step}</span>)}</div><div className="start-actions"><a className="action primary" href={screenPath("/record/push-up")}><Camera /> Record a set</a><a className="action" href={screenPath("/record/push-up")}><Upload /> Upload push-up video</a></div>{mobile && <a className="demo-link" href={screenPath("/demo")}><Play /> View prepared example</a>}{insecureLan && <p className="recording-notice"><CircleAlert /> Direct camera recording may be unavailable over local HTTP. Uploading a video from your photo gallery still works.</p>}</div>
    <details className="recording-guide"><summary>Recording guide</summary>{["Keep the full body visible", "Use a fixed side or supported oblique view", "Start before the first repetition", "Stop after returning to the starting position"].map((item) => <p key={item}><Check />{item}</p>)}</details>
    {!loading && latest && <article className="latest-session"><div className="section-heading"><div><p className="eyebrow">Latest session</p><h2>{dateLabel(latest.created_at)}</h2></div></div><div className="latest-session-grid"><video src={latest.annotated_video_url || latest.source_video_url} muted playsInline preload="metadata" aria-label="Latest workout video thumbnail" /><dl><div><dt>Complete repetitions</dt><dd>{latest.repetition_count ?? "—"}</dd></div><div><dt>Worth reviewing</dt><dd>{reviewIds(latest).size}</dd></div><div><dt>Keep your body in one straight line</dt><dd>{status(alignment)}</dd></div><div><dt>How far you lowered</dt><dd>{status(range)}</dd></div></dl></div><p className="same-viewpoint">Record another session from the same viewpoint to see what changes.</p><a className="action primary latest-open" href={screenPath(`/session?id=${latest.session_id}`)}>Open workout summary <ChevronRight /></a></article>}
    <aside className="adaptive-note"><h2>Feedback adapts to your recording</h2><ul><li>ULIANA checks which criteria the camera view supports.</li><li>Unreliable checks are marked unavailable.</li><li>The clearest supported repetition is selected for review.</li><li>Compatible future sessions show what changed.</li></ul></aside>
  </section></Shell>;
}

function demoResult(): SessionResult {
  return { session_id: "prerecorded-demo", profile_id: "presentation-example", exercise_variation: "standard", status: "completed", exercise: "push-up", created_at: "Pre-recorded example · not your session", repetition_count: 5, duration_seconds: 9.1, overall_assessment_coverage: 1, detected_viewpoint: { value: "side", confidence: 1, reason: "dominant_valid_frame_evidence" }, source_video_url: `${base}/demo/demo-source.mp4`, annotated_video_url: `${base}/demo/demo-annotated.mp4`, coach_summary: { headline: "One clear focus for your next session", summary: "You completed 5 repetitions. Review repetition 1 for the clearest supported camera observation.", what_went_well: "No issue was detected in the available range-of-motion check.", main_focus: "Review repetition 1 and focus on keeping shoulders, hips and ankles aligned.", next_session_plan: ["Keep shoulders, hips and ankles aligned through the movement.", "Use the same side camera angle with your full body visible."], comparison_summary: "Complete another session with the same camera setup to start a comparison." }, repetition_intervals: [1, 2, 3, 4, 5].map((rep) => ({ rep_id: rep, start_ms: (rep - 1) * 1500, bottom_ms: (rep - 1) * 1500 + 750, end_ms: rep * 1500, confidence: 0.947 })), assessments: [1, 2, 3, 4, 5].flatMap((rep) => [{ condition: "body_alignment_deviation", result: rep === 1 ? "condition_detected" : "adequate", reason: rep === 1 ? "persistent_body_alignment_deviation" : "body_alignment_within_configured_range", rep_id: rep, confidence: 0.92, evidence: rep === 1 ? { maximum_alignment_angle_deviation_deg: 12.5, maximum_normalized_hip_displacement: .11, persistent_fraction: .75, longest_persistent_duration_ms: 600, experimental_thresholds: { angle_deviation_deg: 8, normalized_hip_displacement: .08, minimum_persistence_fraction: .25, minimum_persistence_ms: 250 } } : { maximum_alignment_angle_deviation_deg: 5.1, maximum_normalized_hip_displacement: .04 } }, { condition: "push_up_depth_proxy", result: "adequate", reason: "minimum_elbow_angle_within_configured_range", rep_id: rep, confidence: 0.92, evidence: { minimum_elbow_angle_deg: 96 + rep, experimental_threshold_deg: 110 } }, { condition: "head_neck_alignment", result: rep === 2 ? "condition_detected" : "adequate", rep_id: rep, confidence: .81 }]), warnings: [] };
}

export function coachHomeState(items: SessionResult[]): "empty" | "processing" | "completed" | "failed" {
  if (!items.length) return "empty";
  if (items[0].status === "completed") return "completed";
  if (items[0].status === "failed") return "failed";
  return "processing";
}

function MobileCoachHome({ file, preview, consent, setConsent, exerciseType, setExerciseType, choose, analyse, busy, error }: { file: File | null; preview: string | null; consent: boolean; setConsent: (value: boolean) => void; exerciseType: string; setExerciseType: (value: string) => void; choose: (file?: File) => void; analyse: () => void; busy: boolean; error: string }) {
  const { items, loading, failed } = useHistory();
  const uploadRequested = typeof window !== "undefined" && new URLSearchParams(location.search).get("upload") === "1";
  const latest = items[0];
  const homeState = coachHomeState(items);
  const showComposer = uploadRequested || homeState === "empty";
  const stages = ["uploading", "queued", "processing_pose", "counting_repetitions", "rendering_video"];
  const stage = latest ? stages.indexOf(latest.status) : -1;
  if (loading) return <Shell mode="select" appOnly><section className="coach-chat"><p className="coach-message">Loading your sessions…</p></section></Shell>;
  if (!showComposer && homeState === "completed" && (!latest.exercise_type || latest.exercise_type === "standard")) return <Shell mode="session" appOnly><WorkoutReport result={latest} /></Shell>;
  return <Shell mode="select" appOnly><section className="coach-chat coach-home" aria-label="ULIANA Coach workspace"><header className="coach-chat-header"><h1>ULIANA Coach</h1><details><summary aria-label="More options">•••</summary><a href={screenPath("/progress")}>My sessions</a><a href={`${base}/?screen=sensor`}>Sensor</a></details></header><div className="coach-chat-messages" aria-live="polite">
    {failed && <p className="coach-message">Session history is unavailable. Please try again.</p>}
    {showComposer ? <><article className="coach-message"><p>{latest ? "Upload another push-up set, and I’ll show you one thing to focus on." : "Welcome to ULIANA. I’m your push-up coach. Upload your first set, and I’ll show you one thing to focus on."}</p><div className="coach-message-actions"><label className="coach-upload-action">Upload push-up video<input type="file" accept="video/*,.mov,.mp4,.m4v,.webm" onChange={event => choose(event.target.files?.[0])} /></label><LiveChatControls /></div></article><article className="coach-message coach-upload-composer"><label className="exercise-type-picker">Push-up type<select value={exerciseType} onChange={event => setExerciseType(event.target.value)}>{Object.entries(PUSH_UP_TYPES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><small>{exerciseType === "standard" ? "Camera analysis available for standard push-ups." : "Not assessed in this version. The video will be saved without technique conclusions."}</small></label>{preview && <video className="upload-preview" src={preview} controls playsInline />}<label className="consent"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} /><span>I agree to upload and process this recording for the ULIANA prototype test.</span></label>{file && <p>{file.name}</p>}{error && <p className="form-error">{error}</p>}<button disabled={!file || !consent || busy} onClick={analyse}>{busy ? "Uploading…" : "Analyze this set"}</button></article></> : homeState === "failed" ? <article className="coach-message"><p>Something went wrong with this recording. Try uploading it again.</p><div className="coach-message-actions"><a href={`${screenPath("/app")}&upload=1`}>Retry upload</a><a href={screenPath("/progress")}>All checks</a></div></article> : homeState === "completed" ? <article className="coach-message"><p>Exercise: {PUSH_UP_TYPES[latest.exercise_type ?? "standard"]} — Not assessed in this version.</p><a href={screenPath(`/session?id=${latest.session_id}`)}>Open saved recording</a></article> : <article className="coach-message coach-processing"><p>Got it. Analyzing your set now.</p><p>{latest.status.replaceAll("_", " ")}</p><progress value={Math.max(0, stage + 1)} max={stages.length} aria-label="Recording processing progress" /><div className="stage-list">{stages.map((item, index) => <div key={item} className={stage > index ? "done" : stage === index ? "active" : ""}><span>{index + 1}</span>{item.replaceAll("_", " ")}</div>)}</div></article>}
  </div><nav className="coach-chat-nav" aria-label="Workspace views"><a href={screenPath("/progress")}>All checks</a><a href={`${base}/?screen=sensor`}>Sensor</a></nav></section></Shell>;
}

function feedbackCopy(result: SessionResult) {
  const flagged = representativeObservation(result);
  const available = supportedAssessments(result).some((item) => item.result !== "unavailable");
  if (result.repetition_count == null) return { title: "Movement feedback unavailable", support: "The recording did not provide enough reliable evidence to count complete repetitions.", action: "Record again with your full body visible.", rep: undefined as number | undefined };
  if (!available) return { title: "Movement feedback unavailable", support: "We counted your repetitions, but movement feedback was unavailable because the full body was not consistently visible.", action: "Move the camera farther away and keep your full body in frame.", rep: undefined as number | undefined };
  if (flagged) { const count=reviewIds(result, flagged.condition).size; return { title: beginnerCriterion(flagged.condition), support: `${plural(count,"assessed repetition")} contained this observation.`, action: `Watch the clearest example — Rep ${flagged.rep_id ?? "shown"}.`, rep: flagged.rep_id }; }
  return { title: "Looks consistent in the available checks", support: "ULIANA found no flags in the checks this camera view supported. This does not mean every aspect of the movement was assessed.", action: "Repeat the same setup to build a comparable history.", rep: undefined as number | undefined };
}

function nextSessionCopy(result: SessionResult, flagged: Set<number>) {
  void flagged;
  if (boundaryIssue(result)) return "Start before the first repetition and stop after returning to the starting position.";
  if (reviewIds(result, "body_alignment_deviation").size) return "Keep your shoulders, hips and ankles moving as one straight line.";
  if (reviewIds(result, "push_up_depth_proxy").size) return "Use the same viewpoint and focus on a controlled lowering range.";
  if (visibilityIssue(result) || (result.assessments ?? []).every((item) => item.result === "unavailable")) return "Move the camera farther away and keep your full body visible for the complete set.";
  return "Repeat the same setup to build a comparable history.";
}

function representativeObservation(result: SessionResult) {
  return supportedAssessments(result).filter((item) => item.result === "condition_detected").sort((a, b) => {
    const ae = a.evidence ?? {}, be = b.evidence ?? {};
    return Number(be.persistent_fraction ?? 0) - Number(ae.persistent_fraction ?? 0) || Number(be.longest_persistent_duration_ms ?? 0) - Number(ae.longest_persistent_duration_ms ?? 0) || (a.rep_id ?? 1e9) - (b.rep_id ?? 1e9);
  })[0];
}

const PUSH_UP_TYPES: Record<string, string> = { standard: "Standard push-up", diamond: "Diamond push-up", wide: "Wide push-up", incline: "Incline push-up", decline: "Decline push-up" };

function UnassessedPushUp({ result }: { result: SessionResult }) {
  return <section className="status-card unassessed-session"><p className="eyebrow">Saved recording</p><h2>Exercise: {PUSH_UP_TYPES[result.exercise_type ?? "standard"]} — Not assessed in this version.</h2><p>Technique analysis for this push-up type has not been calibrated. No repetition or body-alignment result is available.</p>{result.source_video_url && <video className="result-video" src={result.source_video_url} controls playsInline preload="metadata" />}<a className="action primary" href={screenPath("/progress")}>My sessions</a></section>;
}

function ChatReport({ result, demo, onAllChecks }: { result: SessionResult; demo: boolean; onAllChecks: (technical?: boolean) => void }) {
  const [showSecond, setShowSecond] = useState(false);
  const [showMoment, setShowMoment] = useState(false);
  const [showWhy, setShowWhy] = useState(false);
  const [showFinal, setShowFinal] = useState(false);
  const [moments, setMoments] = useState<ReviewMoment[]>([]);
  const [handWidth, setHandWidth] = useState<(HandWidthChatResult & HandWidthVisual) | null>(null);
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const attachVideo = useCallback((element: HTMLVideoElement | null) => { videoRef.current = element; setVideo(element); }, []);
  const primary = representativeObservation(result);
  const interval = result.repetition_intervals?.find(item => item.rep_id === primary?.rep_id);
  const moment = moments.find(item => item.rep_id === primary?.rep_id);
  const explanation = explainReview(primary);
  const count = primary ? reviewIds(result, primary.condition).size : 0;
  const assessed = primary ? supportedAssessments(result).filter(item => item.condition === primary.condition && item.result !== "unavailable").length : 0;
  const why = primary?.condition === "body_alignment_deviation"
    ? { text: "Keeping the shoulders, hips and ankles aligned helps maintain a stable push-up body configuration and reduces compensatory movement.", source: "https://doi.org/10.1519/SSC.0b013e31826d877b" }
    : { text: "Movement range changes the mechanical demands and training stimulus of the push-up. The camera estimates elbow angle near the bottom position; it does not confirm chest-to-floor contact.", source: "https://doi.org/10.1519/jsc.0000000000004415" };
  useEffect(() => { const timer = setTimeout(() => setShowSecond(true), 500); return () => clearTimeout(timer); }, []);
  useEffect(() => { if (!showMoment) return; const timer = setTimeout(() => setShowFinal(true), 800); return () => clearTimeout(timer); }, [showMoment]);
  useEffect(() => {
    if (demo) return;
    let active = true;
    fetch(`${API}/api/sessions/${result.session_id}/review-moments`).then(response => response.ok ? response.json() as Promise<{ moments: ReviewMoment[] }> : Promise.reject()).then(data => { if (active) setMoments(data.moments); }).catch(() => undefined);
    return () => { active = false; };
  }, [demo, result.session_id]);
  useEffect(() => {
    if (demo) return;
    let active = true;
    apiFetch(`${API}/api/sessions/${result.session_id}/hand-width`, { cache: "no-store" })
      .then(response => response.ok ? response.json() as Promise<HandWidthChatResult & HandWidthVisual> : Promise.reject())
      .then(data => { if (active) setHandWidth(data); })
      .catch(() => undefined);
    return () => { active = false; };
  }, [demo, result.session_id]);
  useEffect(() => {
    if (!showMoment || !videoRef.current || !interval) return;
    videoRef.current.currentTime = reviewSeekMs(interval, moment) / 1000;
    void videoRef.current.play().catch(() => undefined);
  }, [showMoment, video, interval, moment]);
  const allChecks = () => onAllChecks(false);
  return <section className="coach-chat" aria-label="ULIANA Coach conversation">
    <header className="coach-chat-header"><a href={screenPath("/progress")} aria-label="Back to My sessions"><ArrowLeft /></a><h1>ULIANA Coach</h1><details><summary aria-label="More options">•••</summary><a href={screenPath("/progress")}>My sessions</a><button onClick={allChecks}>All checks</button></details></header>
    <div className="coach-chat-messages" aria-live="polite">
      <article className="coach-message"><p>You completed {plural(result.repetition_count ?? 0, "repetition")}. {primary ? "I found one thing worth a look." : "There is no supported issue to review in the available checks."}</p></article>
      {showSecond && primary && <article className="coach-message"><p>{primary.condition === "body_alignment_deviation" ? `In ${count} of ${assessed} assessed reps, the shoulder–hip–ankle line moved outside the assessed range.` : `In ${count} of ${assessed} assessed reps, the visible lowering range moved outside the assessed range.`} Rep {primary.rep_id} shows it most clearly.</p><button onClick={() => setShowMoment(true)} disabled={!interval}><Play /> Show exact moment</button></article>}
      {showMoment && primary && interval && <article className="coach-message coach-moment"><div className="review-video-wrap"><video ref={attachVideo} className="result-video" src={result.annotated_video_url || result.source_video_url} controls playsInline preload="metadata" /><ReviewOverlay video={video} moment={moment} interval={interval} skeletonInVideo={Boolean(result.annotated_video_url)} handWidth={handWidth} /></div><HandWidthComparison result={handWidth} />{!moment && primary.condition === "body_alignment_deviation" && !demo && <p className="review-frame-unavailable">Review frame unavailable from this recording. Landmark quality was insufficient.</p>}{explanation && <><p><strong>Issue</strong>{explanation.issue}</p><p><strong>Evidence</strong>{explanation.evidence}</p><p><strong>Action</strong>{explanation.action}</p></>}<div className="coach-message-actions"><button onClick={() => setShowWhy(true)}>Why this matters</button></div><AudioReviewCue cue={getAudioCueText(primary.condition, primary.result)} momentKey={`${result.session_id}:${primary.rep_id}`} sessionId={result.session_id} video={video} targetMs={reviewSeekMs(interval, moment)} /></article>}
      {showWhy && primary && <article className="coach-message"><p>{why.text}</p><p>Source: <a href={why.source} target="_blank" rel="noreferrer">{why.source}</a></p><small>These sources support the biomechanical criteria. The prototype&apos;s numerical thresholds have not yet been independently validated.</small></article>}
      {showFinal && handWidthCoachMessage(handWidth) && <article className="coach-message"><p>{handWidthCoachMessage(handWidth)}</p></article>}
      {showFinal && <article className="coach-message"><p>{supportedAssessments(result).filter(item => item.result === "condition_detected").length === 1 ? "That’s the only thing to focus on next time. Other available checks looked consistent." : nextSessionCopy(result, reviewIds(result))}</p><div className="coach-message-actions"><a href={`${screenPath("/app")}&upload=1`}>Record another set</a><button onClick={allChecks}>All checks</button></div></article>}
    </div>
    <nav className="coach-chat-nav" aria-label="Session views"><button onClick={allChecks}>All checks</button><button onClick={() => onAllChecks(true)}>Technical</button><a href={`${base}/?screen=sensor`}>Sensor</a></nav>
    <a className="coach-chat-record" href={`${screenPath("/app")}&upload=1`}>Record another set</a>
  </section>;
}

export function WorkoutReport({ result, demo = false }: { result: SessionResult; demo?: boolean }) {
  const [view, setView] = useState<"chat" | "checks">("chat");
  const videoRef = useRef<HTMLVideoElement>(null);
  const [videoElement, setVideoElement] = useState<HTMLVideoElement | null>(null);
  const [moments, setMoments] = useState<ReviewMoment[]>([]);
  const [momentsStatus, setMomentsStatus] = useState<"loading" | "ready" | "error">("loading");
  useEffect(() => { if (demo) return; let active = true; fetch(`${API}/api/sessions/${result.session_id}/review-moments`).then(response => response.ok ? response.json() as Promise<{moments: ReviewMoment[]}> : Promise.reject()).then(data => { if (active) { setMoments(data.moments); setMomentsStatus("ready"); } }).catch(() => { if (active) setMomentsStatus("error"); }); return () => { active = false; }; }, [demo, result.session_id]);
  const { items } = useHistory();
  const representative = representativeObservation(result);
  const [openRep, setOpenRep] = useState<number | null>(representative?.rep_id ?? null);
  const flagged = useMemo(() => reviewIds(result), [result]);
  const feedback = feedbackCopy(result);
  const intervals = result.repetition_intervals ?? [];
  const currentIndex = items.findIndex((item) => item.session_id === result.session_id);
  const older = currentIndex >= 0 ? items.slice(currentIndex + 1).find((item) => (item.profile_id ?? "local-default") === (result.profile_id ?? "local-default") && item.exercise === result.exercise && (item.exercise_variation ?? "standard") === (result.exercise_variation ?? "standard")) : undefined;
  const comparable = older && compatible(result, older) ? older : undefined;
  const seek = (rep: Interval) => { setOpenRep(rep.rep_id); if (videoRef.current) { videoRef.current.currentTime = reviewSeekMs(rep, moments.find(item => item.rep_id === rep.rep_id)) / 1000; void videoRef.current.play(); } };
  const remove = async () => { if (demo || !confirm("Delete this session and its recording?")) return; await apiFetch(`${API}/api/sessions/${result.session_id}`, { method: "DELETE" }); location.href = screenPath("/progress"); };

  const primaryRows = representative ? supportedAssessments(result).filter((item) => item.condition === representative.condition && item.result !== "unavailable") : [];
  const primaryFlags = representative ? primaryRows.filter((item) => item.result === "condition_detected") : [];
  if (view === "chat") return <ChatReport result={result} demo={demo} onAllChecks={(technical = false) => { setView("checks"); if (technical) setTimeout(() => { const drawer = document.querySelector<HTMLDetailsElement>(".measurements-drawer"); if (drawer) { drawer.open = true; drawer.scrollIntoView({ behavior: "smooth" }); } }, 0); }} />;
  return <section className="today-report">
    <div className="checks-return"><button onClick={() => setView("chat")}>← ULIANA Coach</button><span>All checks</span><button onClick={() => { const drawer = document.querySelector<HTMLDetailsElement>(".measurements-drawer"); if (drawer) { drawer.open = true; drawer.scrollIntoView({ behavior: "smooth" }); } }}>Technical</button></div>
    <div className="today-heading"><div><p className="eyebrow">{demo ? "Presentation session" : dateLabel(result.created_at)}</p><h1>Today’s workout</h1><p>Exercise: {PUSH_UP_TYPES[result.exercise_type ?? "standard"]}</p></div>{demo && <span className="preview-label">Pre-recorded example</span>}</div>
    <section className="mobile-result-summary"><p className="eyebrow">Session result</p><h2>{plural(result.repetition_count??0,"repetition")} completed</h2><h3>{feedback.title}</h3>{feedback.rep!=null&&<button onClick={()=>{const rep=intervals.find(item=>item.rep_id===feedback.rep);if(rep)seek(rep)}}><Play/> Watch repetition {feedback.rep}</button>}<p><strong>What to look for</strong>{feedback.support}</p><p><strong>Next session</strong>{nextSessionCopy(result,flagged)}</p></section>
    <section className="result-story" aria-label="Workout summary"><article><span>1 · What happened?</span><h2>{result.repetition_count==null?"Repetition count unavailable":`You completed ${plural(result.repetition_count,"repetition")}.`}</h2><p>{representative ? `ULIANA found the same ${shortCriterion(representative.condition).toLowerCase()} observation in ${primaryFlags.length} of ${plural(primaryRows.length,"assessed repetition")}.` : "No observation was flagged in the supported checks available for this recording."}</p></article><article><span>2 · What should I review?</span><h2>{representative?.rep_id != null ? `Rep ${representative.rep_id} is the clearest example.` : "There is no supported moment to review."}</h2><p>{representative?.rep_id != null ? `The observation appeared in ${primaryFlags.length} of ${plural(primaryRows.length,"assessed repetition")}. Rep ${representative.rep_id} shows it most clearly.` : "Unavailable checks are not treated as positive results."}</p>{representative?.rep_id != null && <button onClick={() => { const rep = intervals.find((item) => item.rep_id === representative.rep_id); if (rep) seek(rep); }}><Play /> Watch the clearest {shortCriterion(representative.condition).toLowerCase()} example — Rep {representative.rep_id}</button>}</article><article><span>3 · What should I do next?</span><h2>Next session</h2><p>{nextSessionCopy(result, flagged)}</p></article></section>
    <div className="today-grid">
      <section className="today-video-card"><div className="section-heading"><div><p className="eyebrow">Review the movement</p><h2>Video review</h2></div></div>{result.annotated_video_url || result.source_video_url ? <><div className="review-video-wrap"><video ref={(element) => { videoRef.current = element; setVideoElement(element); }} className="result-video" src={result.annotated_video_url || result.source_video_url} controls playsInline preload="metadata" /><ReviewOverlay video={videoElement} moment={moments.find(item => item.rep_id === openRep)} interval={intervals.find(item => item.rep_id === openRep)} skeletonInVideo={Boolean(result.annotated_video_url)} /></div>{openRep != null && supportedAssessments(result).some(item => item.rep_id === openRep && item.condition === "body_alignment_deviation" && item.result === "condition_detected") && momentsStatus !== "loading" && !moments.some(item => item.rep_id === openRep) && <p className="review-frame-unavailable">{momentsStatus === "error" ? "Review frame unavailable. Please try again." : "Review frame unavailable from this recording. Landmark quality was insufficient."}</p>}{moments.some(item => item.rep_id === openRep) && <p className="review-overlay-legend"><span>Reference alignment</span> · {result.annotated_video_url ? "Green: pose tracked in the video" : "Green: selected frame pose at the review moment"} · Red ring: observed hip location · Arrow: direction toward the body line</p>}</> : <p className="form-error">Video unavailable. Numerical results remain visible.</p>}<div className="rep-chips" aria-label="Repetition timeline">{intervals.map((rep) => { const assessments = supportedAssessments(result).filter((item) => item.rep_id === rep.rep_id); const observed = assessments.find((item) => item.result === "condition_detected"); const status = observed ? "review" : assessments.some((item) => item.result !== "unavailable") ? "clear" : "unavailable"; return <button key={rep.rep_id} className={`${status}${openRep === rep.rep_id ? " selected" : ""}`} aria-pressed={openRep === rep.rep_id} onClick={() => seek(rep)}><strong>Rep {rep.rep_id}</strong><span>{status === "review" ? `Review: ${shortCriterion(observed!.condition).toLowerCase()}` : status === "clear" ? "Looks consistent" : "Not assessed"}</span></button>; })}</div>{openRep != null && intervals.some((item) => item.rep_id === openRep) && <RepDetails result={result} rep={intervals.find((item) => item.rep_id === openRep)!} representative={representative?.rep_id === openRep} video={videoElement} moment={moments.find(item => item.rep_id === openRep)} onPlay={() => seek(intervals.find((item) => item.rep_id === openRep)!)} />}</section>
      <aside className="today-side"><div className="today-metrics"><article><strong>{result.repetition_count ?? "—"}</strong><span>Complete repetitions</span></article><article><strong>{assessedCriteria(result)}</strong><span>Camera checks available</span></article><article><strong>{flagged.size}</strong><span>Repetitions worth reviewing</span></article><article><strong>{result.duration_seconds == null ? "—" : `${result.duration_seconds.toFixed(1)} s`}</strong><span>Session duration</span></article></div><article className="today-feedback"><p className="eyebrow">Main observation</p><h2>{feedback.title}</h2><p>{feedback.support}</p>{feedback.rep != null && <button className="watch-moment" onClick={() => { const rep = intervals.find((item) => item.rep_id === feedback.rep); if (rep) seek(rep); }}><Play /> Watch the clearest example — Rep {feedback.rep}</button>}<button className="why-link" onClick={() => document.querySelector<HTMLDetailsElement>(".measurements-drawer")?.setAttribute("open", "")}>Open technical details</button></article><article className="next-session-card"><p className="eyebrow">Next session</p><p>{nextSessionCopy(result, flagged)}</p></article><a className="action primary record-again" href={screenPath("/record/push-up")}><Camera /> Record another session</a></aside>
    </div>
    {result.coach_summary && <CoachSummaryCard summary={result.coach_summary} representativeRep={feedback.rep} onWatch={() => { const rep = intervals.find((item) => item.rep_id === feedback.rep); if (rep) seek(rep); }} />}
    <TechniqueSummary result={result} onSeek={seek} />
    <Comparison current={result} previous={comparable} priorSameExercise={older} demo={demo} />
    {demo && <IllustrativeProgress />}
    <Measurements result={result} />
    <div className="report-actions">{!demo&&<a className="action primary" href={screenPath("/record/push-up")}><Camera/> Record another session</a>}<a href={screenPath("/progress")}>My sessions</a>{result.annotated_video_url && <a href={result.annotated_video_url} download><Download /> Download video</a>}{!demo && <button className="danger-action" onClick={() => void remove()}><Trash2 /> Delete session</button>}</div>
  </section>;
}

function CoachSummaryCard({ summary, representativeRep, onWatch }: { summary: CoachSummary; representativeRep?: number; onWatch: () => void }) {
  return <section className="coach-summary-card"><div className="coach-summary-head"><div><p className="eyebrow">Your session summary</p><h2>{summary.headline}</h2></div>{representativeRep != null && <button onClick={onWatch}><Play /> Watch repetition {representativeRep}</button>}</div><p className="coach-lede">{summary.summary}</p><div className="coach-highlights"><p><strong>What went well</strong>{summary.what_went_well}</p><p><strong>Main focus</strong>{summary.main_focus}</p></div><div className="coach-plan"><strong>Next session</strong><ol>{summary.next_session_plan.map((step) => <li key={step}>{step}</li>)}</ol></div><p className="coach-comparison">{summary.comparison_summary}</p><small>Explanation generated from ULIANA’s camera-based measurements.</small></section>;
}

function RepDetails({ result, rep, representative, video, moment, onPlay }: { result: SessionResult; rep: Interval; representative: boolean; video: HTMLVideoElement | null; moment?: ReviewMoment; onPlay: () => void }) {
  const assessments = supportedAssessments(result).filter((item) => item.rep_id === rep.rep_id);
  const observed = assessments.find((item) => item.result === "condition_detected");
  const available = assessments.find((item) => item.result === "adequate");
  const cue = observed ? getAudioCueText(observed.condition, observed.result) : available ? getAudioCueText(available.condition, "consistent") : null;
  const explanation = explainReview(observed);
  const wording = observed?.condition === "push_up_depth_proxy" ? {look: "Watch how far the visible elbow bends near the bottom position.", seen: "During this repetition, the visible elbow-angle proxy moved outside the current experimental range.", next: "Use the same viewpoint and lower through a range you can control."} : {look: "Watch the line from your shoulders through your hips to your ankles.", seen: "During this repetition, the visible body line moved outside the current experimental range for a sustained moment.", next: "Keep your trunk and hips aligned as you lower and return."};
  return <div className="rep-detail"><div><strong>Rep {rep.rep_id}</strong><span>{stamp(rep.start_ms)}–{stamp(rep.end_ms)} · {repDuration(rep).toFixed(1)} s</span></div>{observed ? <div className="review-explainer">{explanation && <><p><strong>Issue</strong>{explanation.issue}</p><p><strong>Evidence</strong>{explanation.evidence}</p><p><strong>Action</strong>{explanation.action}</p></>}<p><strong>What to look for</strong>{wording.look}</p><p><strong>What ULIANA observed</strong>{wording.seen}</p><p><strong>Why this repetition</strong>{representative ? "This repetition contains the clearest supported example of the session’s main observation." : "This repetition contains the same supported observation, but another repetition was selected as the clearest example."}</p><p><strong>Try next time</strong>{wording.next}</p></div> : <p><strong>{assessments.some((item) => item.result !== "unavailable") ? "Looks consistent in this check" : "Not assessed: camera angle or landmark quality was insufficient."}</strong></p>}<AudioReviewCue cue={cue} momentKey={`${result.session_id}:${rep.rep_id}`} sessionId={result.session_id} video={video} targetMs={reviewSeekMs(rep, moment)} /><button className="play-rep" onClick={onPlay}><Play /> Watch exact moment</button></div>;
}

function TechniqueSummary({ result, onSeek }: { result: SessionResult; onSeek: (rep: Interval) => void }) {
  const intervals = result.repetition_intervals ?? [];
  return <section className="technique-summary"><div className="section-heading"><div><p className="eyebrow">Supported camera checks</p><h2>What the camera could assess</h2></div></div><div className="technique-cards">{SUPPORTED.map((id) => { const rows = supportedAssessments(result).filter((item) => item.condition === id); const flaggedRows = rows.filter((item) => item.result === "condition_detected"); const available = rows.filter((item) => item.result !== "unavailable"); const representative = representativeObservation({ ...result, assessments: flaggedRows }); const unavailableState = available.length === 0; const unavailableReason = rows.find((item) => item.result === "unavailable")?.reason; return <article key={id} className={unavailableState ? "unavailable" : flaggedRows.length ? "review" : "clear"}><div><h3>{beginnerCriterion(id)}</h3><span>{unavailableState ? "Couldn’t assess" : flaggedRows.length ? "Worth reviewing" : "Looks consistent in this check"}</span></div><strong>{unavailableState ? friendlyUnavailable(unavailableReason) : flaggedRows.length ? `${flaggedRows.length} of ${plural(available.length,"assessed repetition")} contained this observation` : `${plural(available.length,"assessed repetition")} looked consistent in this check`}</strong><p>{id === "body_alignment_deviation" ? (flaggedRows.length ? "The visible shoulder–hip–ankle line moved outside the current experimental range." : "The visible shoulder–hip–ankle relationship stayed within the current experimental range.") : (flaggedRows.length ? "The visible elbow-angle proxy was outside the current experimental range near the bottom." : "The visible elbow-angle proxy stayed within the current experimental range.")}</p>{representative?.rep_id != null && <button onClick={() => { const rep = intervals.find((item) => item.rep_id === representative.rep_id); if (rep) onSeek(rep); }}><Play /> Watch the clearest example — Rep {representative.rep_id}</button>}<CriterionRationale criterion={id} /></article>; })}</div></section>;
}

function friendlyUnavailable(reason?: string) {
  if (/elbow/i.test(reason ?? "")) return "The elbow was not visible reliably near the bottom position.";
  if (/view/i.test(reason ?? "")) return "The camera viewpoint did not support this check.";
  return "The visible body landmarks were not reliable enough for this check.";
}

function CriterionRationale({ criterion }: { criterion: (typeof SUPPORTED)[number] }) {
  const alignment = criterion === "body_alignment_deviation";
  return <details className="criterion-rationale"><summary>Why this matters</summary><div><p>{alignment ? mobileCopy.alignmentExplanation : mobileCopy.romExplanation}</p><p>{mobileCopy.thresholdsNotValidated}</p><h4>Coaching convention</h4><p>{alignment ? "Keeping the trunk and hips aligned is a common practical coaching instruction. It still requires trainer validation in this product." : "Using a controlled lowering range is a common practical coaching instruction. Individual goals and coaching context can differ."}</p><h4>Scientific rationale</h4><p>{alignment ? "Research indicates that body configuration can affect push-up biomechanics. It does not allow ULIANA to diagnose loading or risk." : "Research treats movement range as a relevant exercise variable. It does not validate one universal range or predict training outcomes for an individual."}</p><h4>Camera observation</h4><p>{alignment ? "ULIANA observes the visible relationship between shoulder, hip and ankle landmarks when the viewpoint and landmark quality support it." : "ULIANA uses visible elbow angle near the bottom position as a camera proxy. It cannot confirm chest-to-floor contact."}</p><h4>Prototype threshold</h4><p>Prototype threshold selected for technical evaluation. Trainer validation is pending.</p><p className="source-links"><a href="https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker" target="_blank" rel="noreferrer">MediaPipe Pose Landmarker documentation</a><a href={alignment ? "https://doi.org/10.1519/SSC.0b013e31826d877b" : "https://doi.org/10.1519/JSC.0000000000004415"} target="_blank" rel="noreferrer">{alignment ? "The Biomechanics of the Push-Up" : "Which ROMs Lead to Rome?"}</a>{alignment && <a href="https://doi.org/10.4085/1062-6050-48.5.08" target="_blank" rel="noreferrer">Scapular Kinematics and Shoulder Elevation in a Traditional Push-Up</a>}</p></div></details>;
}

function Comparison({ current, previous, priorSameExercise, demo }: { current: SessionResult; previous?: SessionResult; priorSameExercise?: SessionResult; demo: boolean }) {
  if (demo) return <section className="comparison-card"><div><p className="eyebrow">Since your previous session</p><h2>Complete another session to compare</h2></div><p>Presentation mode keeps illustrative history separate from real saved sessions.</p></section>;
  if (!previous) return <section className="comparison-card"><div><p className="eyebrow">Since your previous session</p><h2>{priorSameExercise ? "Camera setup changed" : "Comparison not available yet"}</h2></div><p>{priorSameExercise ? "Camera setup changed, so movement observations may not be directly comparable." : "Complete one more session with the same camera setup to unlock comparison."}</p></section>;
  const currentMedian = medianDuration(current), previousMedian = medianDuration(previous);
  const durationDelta = currentMedian != null && previousMedian != null ? currentMedian - previousMedian : null;
  const phrase = durationDelta == null ? "Duration unavailable" : Math.abs(durationDelta) < 0.15 ? "Similar repetition duration" : `${Math.abs(durationDelta).toFixed(1)} s ${durationDelta < 0 ? "shorter" : "longer"} median repetition`;
  const assessed = (value: SessionResult, criterion: string) => supportedAssessments(value).filter((item) => item.condition === criterion && item.result !== "unavailable").length;
  const smallSample = (current.repetition_count ?? 0) < 2 || (previous.repetition_count ?? 0) < 2;
  return <section className="comparison-card"><div className="comparison-title"><p className="eyebrow">Compared with a session from a comparable viewpoint</p><h2>{smallSample ? "Not enough comparable repetitions to describe a technique trend yet." : "Compare the proportions, not only the flag counts."}</h2><p>Completed repetitions: {previous.repetition_count ?? "—"} → {current.repetition_count ?? "—"} · {phrase}</p></div><div className="comparison-table"><span /><strong>Previous</strong><strong>Today</strong><span>Alignment observation</span><b>{reviewIds(previous, "body_alignment_deviation").size} of {assessed(previous, "body_alignment_deviation")}</b><b>{reviewIds(current, "body_alignment_deviation").size} of {assessed(current, "body_alignment_deviation")}</b><span>Lowering-range observation</span><b>{reviewIds(previous, "push_up_depth_proxy").size} of {assessed(previous, "push_up_depth_proxy")}</b><b>{reviewIds(current, "push_up_depth_proxy").size} of {assessed(current, "push_up_depth_proxy")}</b><span>Median repetition</span><b>{medianDuration(previous)?.toFixed(1) ?? "—"} s</b><b>{currentMedian?.toFixed(1) ?? "—"} s</b></div></section>;
}

function Measurements({ result }: { result: SessionResult }) {
  const policy = result.feedback_report;
  const showForCapture = typeof window !== "undefined" && new URLSearchParams(location.search).get("details") === "1";
  const cards = policy?.criterion_cards ?? [];
  const formatThreshold = (threshold: unknown) => threshold && typeof threshold === "object" ? Object.entries(threshold as Record<string, unknown>) : threshold == null ? [] : [["threshold", threshold]];
  return <details className="measurements-drawer" open={showForCapture || undefined}><summary>How this was measured</summary><div className="details-tabs"><section><span className="tab-label">Camera measurements</span><h3>Supported checks in this recording</h3><p><strong>Visible body line:</strong> shoulder, hip and ankle landmarks, including deviation and persistence.</p><p><strong>Lowering range:</strong> visible elbow angle near the bottom as a proxy. It does not confirm chest-to-floor contact.</p><p><strong>Camera viewpoint:</strong> {pretty(result.detected_viewpoint?.value ?? "Unavailable")}</p>{cards.filter((card) => SUPPORTED.includes(card.criterion_id as (typeof SUPPORTED)[number])).slice(0, 2).map((card) => <div className="threshold-table" key={card.criterion_id}><strong>{criterionLabel(card.criterion_id)} · example Rep {card.rep_id ?? "—"}</strong>{card.measurements.map((measurement) => <p key={measurement.name}><span>{pretty(measurement.name)}</span><b>{Number(measurement.value.toFixed(3))} {measurement.unit}</b></p>)}{formatThreshold(card.threshold).map(([name, value]) => <p key={String(name)}><span>{pretty(String(name))}</span><b>{String(value)}</b></p>)}<small>Prototype threshold selected for technical evaluation. Trainer validation is pending.</small></div>)}</section><section><span className="tab-label">Experimental camera checks</span><h3>Not used in your primary feedback</h3>{EXPERIMENTAL.map((id) => <p key={id}><strong>{criterionLabel(id)}</strong><br />Experimental — trainer validation pending</p>)}<p>Neutral head position is a coaching convention, not a validated universal rule. Arm and shoulder configuration can alter observable biomechanics, but this prototype does not detect shoulder conditions. Camera-based hand-placement feedback remains experimental.</p></section><section className="future-module-card"><span className="tab-label">Future product direction</span><h3>Future smart-mat module</h3>{smartMatCriteria.map((label) => <p key={label}><strong>{label}</strong><br />Smart-mat data required; unavailable from camera frames.</p>)}<p>Combined camera and mat analysis, real-time auditory cues, within-set technique-deterioration research and workout-volume recommendations are future directions, not current functionality.</p><p><strong>Future research will investigate whether repeated changes in supported movement observations can provide a reliable indication of within-set technique deterioration.</strong></p></section><section><span className="tab-label">Evidence boundaries</span><h3>What research supports</h3><p>Research indicates that body configuration, movement range and hand or arm position can affect push-up biomechanics. ULIANA translates camera-visible aspects of these movements into experimental review criteria. The current thresholds are prototype decisions and still require trainer validation.</p><p>Hand placement can affect joint loading and muscle involvement, but camera-based hand-placement feedback is not currently supported.</p><p>The cited publications do not validate ULIANA’s numerical thresholds.</p></section></div></details>;
}

function ProgressDashboard() {
  const { items, loading, failed } = useHistory();
  const showEmptyPreview = typeof window !== "undefined" && new URLSearchParams(location.search).get("empty") === "1";
  const visibleItems = showEmptyPreview ? [] : items;
  const visibleLoading = showEmptyPreview ? false : loading;
  const completed=visibleItems.filter(item=>item.status==="completed"), previous=completed.length>1&&compatible(completed[0],completed[1])?completed[1]:undefined;
  const statusLabel=(value:string)=>value==="completed"?"Ready":value==="failed"?"Failed":["created","uploading","queued"].includes(value)?"Queued":"Processing";
  return <section className="progress-dashboard sessions-dashboard">{visibleLoading&&<div className="history-empty">Loading sessions…</div>}{failed&&!showEmptyPreview&&<p className="form-error">The analysis server is unavailable. Please try again later.</p>}{!visibleLoading&&!failed&&!visibleItems.length&&<div className="history-empty"><Camera/><h2>No sessions yet</h2><p>Upload a push-up video to begin.</p><a className="action primary" href={screenPath("/record/push-up")}>Upload push-up video</a></div>}{visibleItems.length>0&&<><p className="session-count">{plural(visibleItems.length,"session")}</p><div className="session-list">{visibleItems.map(item=><article key={item.session_id} className={`session-${item.status}`}><div><strong>{dateLabel(item.created_at)}</strong><span className="session-status">{statusLabel(item.status)}</span><span>{item.status==="completed"?item.exercise_type && item.exercise_type !== "standard" ? `${PUSH_UP_TYPES[item.exercise_type]} · Not assessed in this version` : `${plural(item.repetition_count??0,"repetition")} · ${feedbackCopy(item).title}`:item.error??"Your video is being prepared."}</span></div>{item.status==="completed"&&<a href={screenPath(`/session?id=${item.session_id}`)}>Open result <ChevronRight/></a>}{item.status==="failed"&&<div className="failed-actions"><a href={screenPath("/record/push-up")}>Upload again</a><button onClick={async()=>{if(confirm("Delete this failed session?")){await apiFetch(`${API}/api/sessions/${item.session_id}`,{method:"DELETE"});location.reload()}}}>Delete</button></div>}</article>)}</div>{previous&&<Comparison current={completed[0]} previous={previous} priorSameExercise={previous} demo={false}/>}</>}</section>;
}

function IllustrativeProgress() {
  return <section className="illustrative-progress"><span className="preview-label">Illustrative progress preview — not current-user measurements.</span><div className="mini-progress"><div><b>4</b><span>Session 1</span></div><div><b>5</b><span>Session 2</span></div><div><b>5</b><span>Today</span></div></div><p>A separate preview shows where real saved-session trends appear after comparable recordings exist.</p></section>;
}
