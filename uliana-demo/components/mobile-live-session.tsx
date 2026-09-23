"use client";

import { useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { MatVisualization, SENSOR_LAYOUT } from "@/components/mat-visualization";

export const LIVE_STARTED_KEY = "uliana-live-started-at";
export const LIVE_ENDED_KEY = "uliana-live-ended";

type Channel = { channel_id: string; raw_value: number; delta: number | null; hand: boolean };
type Device = { pairing_id: string; state: string; last_seen_at: string | null; last_sequence: number | null; sample_sequence?: number | null; channels: Channel[]; baseline: Record<string, number> | null };

export function isSensorReceiving(device: Device) {
  const lastSeen = device.last_seen_at ? Date.parse(device.last_seen_at) : NaN;
  return device.state === "Receiving data" && Number.isFinite(lastSeen) && Date.now() - lastSeen <= 10_000;
}

function duration(seconds: number) {
  return `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;
}

export function MobileLiveSession() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const polling = useRef(false);
  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [device, setDevice] = useState<Device | null>(null);
  const [sensorError, setSensorError] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [startedAt] = useState(() => {
    if (typeof window === "undefined") return Date.now();
    const saved = Number(sessionStorage.getItem(LIVE_STARTED_KEY));
    const started = saved > 0 ? saved : Date.now();
    sessionStorage.setItem(LIVE_STARTED_KEY, String(started));
    sessionStorage.removeItem(LIVE_ENDED_KEY);
    return started;
  });

  useEffect(() => {
    let active = true;
    const camera = navigator.mediaDevices?.getUserMedia
      ? navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false })
      : Promise.reject(new Error("Camera unavailable"));
    void camera
      .then(stream => {
        if (!active) { stream.getTracks().forEach(track => track.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) { videoRef.current.srcObject = stream; void videoRef.current.play().catch(() => undefined); }
        setCameraActive(true);
      })
      .catch(() => { if (active) setCameraError("Camera permission was denied or the camera is unavailable."); });
    return () => {
      active = false;
      streamRef.current?.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    };
  }, []);

  useEffect(() => {
    let active = true;
    const update = async () => {
      if (polling.current) return;
      polling.current = true;
      try {
        const response = await apiFetch("/api/sensors", { cache: "no-store" });
        if (!response.ok) throw new Error("Sensor unavailable");
        const payload = await response.json() as { devices: Device[] };
        if (!active) return;
        const next = payload.devices.find(isSensorReceiving) ?? payload.devices[0] ?? null;
        setDevice(previous => previous?.pairing_id === next?.pairing_id &&
          (previous?.sample_sequence ?? previous?.last_sequence) === (next?.sample_sequence ?? next?.last_sequence) ? previous : next);
        setSensorError(false);
      } catch { if (active) setSensorError(true); }
      finally { polling.current = false; }
    };
    void update();
    const pollTimer = window.setInterval(() => void update(), 500);
    const clockTimer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => { active = false; window.clearInterval(pollTimer); window.clearInterval(clockTimer); };
  }, []);

  const receiving = !sensorError && device !== null && isSensorReceiving(device) && now - Date.parse(device.last_seen_at ?? "") <= 10_000;
  const channelData = Object.fromEntries(Array.from({ length: 16 }, (_, channel) => {
    const reading = device?.channels.find(item => item.channel_id === `channel_${channel}`);
    return [channel, { raw: reading?.raw_value ?? 0, delta: reading?.delta ?? 0, hand: reading?.hand ?? false }];
  })) as Record<number, { raw: number; delta: number; hand: boolean }>;

  const stop = () => {
    streamRef.current?.getTracks().forEach(track => track.stop());
    sessionStorage.removeItem(LIVE_STARTED_KEY);
    sessionStorage.setItem(LIVE_ENDED_KEY, "1");
    window.location.assign("/?screen=app&upload=1");
  };

  return <main className="live-session" id="main">
    <header className="live-session-header"><h1>Live session</h1></header>
    <div className="coach-chat-messages live-session-chat" aria-label="Live session chat status">
      <article className="coach-message" role="status">
        <p>Live session started</p>
        <p>{cameraActive ? "Camera active" : cameraError || "Starting camera…"}</p>
        <p>Sensor: {receiving ? "Receiving data" : "Not connected"}</p>
        <p>Session timer: {duration(Math.max(0, Math.floor((now - startedAt) / 1000)))}</p>
      </article>
    </div>
    <div className="live-session-layout">
      <section className="live-camera-panel" aria-label="Live camera preview">
        <video ref={videoRef} autoPlay muted playsInline aria-label="Live camera" />
        {!cameraActive && <p>{cameraError || "Waiting for camera…"}</p>}
      </section>
      <section className="live-mat-panel" aria-label="Live raw sensor mat">
        <h2>Raw experimental sensor signal</h2>
        <MatVisualization sensors={SENSOR_LAYOUT} channelData={channelData} baselineSet={device?.baseline != null} />
        <p>Sequence: {device?.last_sequence ?? 0}</p>
        <p className="sensor-heatmap-disclaimer">Raw experimental sensor signal. Not calibrated. Not used in primary technique result.</p>
      </section>
    </div>
    <div className="live-session-actions"><button type="button" disabled title="Recording is not implemented yet">Start recording</button><button type="button" onClick={stop}>Stop session</button></div>
  </main>;
}

export function LiveChatControls() {
  const [cameraReady, setCameraReady] = useState(false);
  const [sensorReady, setSensorReady] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [ended, setEnded] = useState(false);

  useEffect(() => {
    const endedTimer = window.setTimeout(() => setEnded(sessionStorage.getItem(LIVE_ENDED_KEY) === "1"), 0);
    let active = true;
    const checkSensor = async () => {
      try {
        const response = await apiFetch("/api/sensors", { cache: "no-store" });
        if (!response.ok) throw new Error("Sensor unavailable");
        const payload = await response.json() as { devices: Device[] };
        if (active) setSensorReady(payload.devices.some(isSensorReceiving));
      } catch { if (active) setSensorReady(false); }
    };
    void checkSensor();
    const timer = window.setInterval(() => void checkSensor(), 2000);
    return () => { active = false; window.clearTimeout(endedTimer); window.clearInterval(timer); };
  }, []);

  const enableCamera = async () => {
    setCameraError("");
    if (!navigator.mediaDevices?.getUserMedia) { setCameraError("Camera is unavailable in this browser or connection."); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      stream.getTracks().forEach(track => track.stop());
      setCameraReady(true);
    } catch { setCameraReady(false); setCameraError("Camera permission was denied or the camera is unavailable."); }
  };

  const start = () => {
    if (!cameraReady || !sensorReady) return;
    sessionStorage.setItem(LIVE_STARTED_KEY, String(Date.now()));
    sessionStorage.removeItem(LIVE_ENDED_KEY);
    window.location.assign("/app?screen=live");
  };

  return <div className="live-chat-entry">
    <button type="button" onClick={() => void enableCamera()}>{cameraReady ? "Camera ready" : "Enable camera"}</button>
    <span title="Live session: camera + sensor real-time"><button type="button" disabled={!cameraReady || !sensorReady} onClick={start} title="Live session: camera + sensor real-time">Start live session</button></span>
    <small>Sensor: {sensorReady ? "Receiving data" : "Not connected"}</small>
    {cameraError && <small role="alert">{cameraError}</small>}
    {ended && <div className="live-chat-ended"><p>Live session ended</p><button type="button" disabled title="Recording is not implemented yet">Analyze recording</button></div>}
  </div>;
}
