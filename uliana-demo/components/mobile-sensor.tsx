"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { MatVisualization, SENSOR_LAYOUT } from "@/components/mat-visualization";

type Channel = { channel_id: string; raw_value: number; delta: number | null; hand: boolean };
type Device = { pairing_id: string; device_id: string; state: string; last_seen_at: string | null; last_sequence: number | null; sample_sequence?: number | null; channels: Channel[]; baseline?: Record<string, number> };
export type HandWidthResult = {
  shoulder_width_cm: number;
  hand_width_cm: number | null;
  deviation_cm: number | null;
  classification: "aligned" | "slightly wide" | "slightly narrow" | "too wide" | "too narrow" | null;
  sensor_camera_agree: boolean | null;
  expected_shoulders: { left_x: number; right_x: number } | null;
};

function sameReadings(previous: Device[], next: Device[]) {
  return previous.length === next.length && previous.every((device, index) => {
    const incoming = next[index];
    return device.pairing_id === incoming.pairing_id &&
      (device.sample_sequence ?? device.last_sequence) === (incoming.sample_sequence ?? incoming.last_sequence);
  });
}

function BatchFreshness({ device, networkLost }: { device: Device; networkLost: boolean }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const received = device.last_seen_at ? Date.parse(device.last_seen_at) : NaN;
  const age = Number.isFinite(received) ? Math.max(0, Math.floor((now - received) / 1000)) : null;
  const state = networkLost || (age !== null && age > 10) ? "Connection lost" :
    device.state === "Not connected" ? "Not connected" : !device.last_sequence ? "Waiting" : "Receiving data";
  return <>
    <p role="status">{state}</p>
    <p>Last batch: {age === null ? "Unavailable" : `${age} seconds ago`}</p>
    <p>Sequence: {device.last_sequence ?? 0}</p>
  </>;
}

export function HandWidthStatus({ result }: { result: HandWidthResult | null }) {
  if (!result?.classification || result.hand_width_cm === null || result.deviation_cm === null) {
    return <p className="hand-width-status hand-width-unassessed">Hand width: not assessed</p>;
  }
  const difference = Math.abs(result.deviation_cm);
  const relation = result.deviation_cm >= 0 ? "wider" : "narrower";
  const tone = result.classification === "aligned" ? "aligned" : result.classification.startsWith("slightly") ? "slightly" : "too";
  return <div className={`hand-width-status hand-width-${tone}`} role="status">
    <p>Hand width: {result.hand_width_cm} cm ({difference} cm {relation} than shoulders)</p>
    {result.sensor_camera_agree === false && <p>⚠ Camera and sensor disagree.</p>}
  </div>;
}

function SensorMat({ device, handWidth }: { device: Device; handWidth: HandWidthResult | null }) {
  const [selectedChannel, setSelectedChannel] = useState(8);
  const readings = new Map(device.channels.map(channel => [channel.channel_id, channel]));
  const channelData = Object.fromEntries(Array.from({ length: 16 }, (_, channel) => {
    const id = `channel_${channel}`;
    const reading = readings.get(id);
    return [channel, { raw: reading?.raw_value ?? 0, delta: reading?.delta ?? 0, hand: reading?.hand ?? false }];
  })) as Record<number, { raw: number; delta: number; hand: boolean }>;
  const selected = channelData[selectedChannel];
  const selectedReading = readings.get(`channel_${selectedChannel}`);
  return <div>
    <strong>Raw experimental sensor signal</strong>
    <p className="sensor-heatmap-note">Delta is the absolute change from the ESP32 calibration baseline. Calibrate with the mat untouched.</p>
    <MatVisualization sensors={SENSOR_LAYOUT} channelData={channelData} baselineSet={device.baseline !== null && device.baseline !== undefined} expectedShoulders={handWidth?.expected_shoulders ?? undefined} handWidth={handWidth ?? undefined} onSensorClick={setSelectedChannel} />
    <HandWidthStatus result={handWidth} />
    <p className="sensor-mat-reading" aria-live="polite">C{selectedChannel} · raw {selected.raw} · delta {selectedReading?.delta ?? "unavailable"} · {selectedReading?.delta == null ? "waiting for ESP32 baseline" : selected.hand ? "[HAND]" : "no touch"}</p>
    <div className="sensor-heatmap-legend" aria-label="Sensor activity legend">
      <span><i className="sensor-heatmap-none" />Green · no active sensor</span>
      <span><i className="sensor-heatmap-one" />Orange · 1 active sensor</span>
      <span><i className="sensor-heatmap-many" />Red · 2+ active sensors</span>
    </div>
    <p className="sensor-heatmap-disclaimer">Raw experimental sensor signal. Not calibrated. Not used in primary technique result.</p>
  </div>;
}

export function ExperimentalSensor() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [networkLost, setNetworkLost] = useState(false);
  const [deviceId, setDeviceId] = useState("esp32-demo-01");
  const [token, setToken] = useState("");
  const [pairing, setPairing] = useState(false);
  const [expiresInMinutes, setExpiresInMinutes] = useState(15);
  const [sessionId, setSessionId] = useState("");
  const [handWidth, setHandWidth] = useState<HandWidthResult | null>(null);
  const [error, setError] = useState("");
  const polling = useRef(false);
  const mounted = useRef(false);

  const refresh = useCallback(async () => {
    if (polling.current || !mounted.current) return;
    polling.current = true;
    try {
      const response = await apiFetch("/api/sensors", { cache: "no-store" });
      if (!response.ok) throw new Error("Sensor status unavailable.");
      const next = ((await response.json()) as { devices: Device[] }).devices;
      if (!mounted.current) return;
      setDevices(previous => sameReadings(previous, next) ? previous : next);
      setNetworkLost(false);
    } catch {
      if (mounted.current) setNetworkLost(true);
    } finally {
      polling.current = false;
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    const first = window.setTimeout(() => void refresh(), 0);
    const interval = window.setInterval(() => void refresh(), 500);
    return () => { mounted.current = false; window.clearTimeout(first); window.clearInterval(interval); };
  }, [refresh]);

  useEffect(() => {
    const linkedSession = sessionId.trim();
    if (!linkedSession) return;
    let active = true;
    let requesting = false;
    const refreshHandWidth = async () => {
      if (requesting) return;
      requesting = true;
      try {
        const response = await apiFetch(`/api/sessions/${encodeURIComponent(linkedSession)}/hand-width`, { cache: "no-store" });
        if (!response.ok) throw new Error("Hand width unavailable");
        const result = await response.json() as HandWidthResult;
        if (active) setHandWidth(result);
      } catch { if (active) setHandWidth(null); }
      finally { requesting = false; }
    };
    void refreshHandWidth();
    const interval = window.setInterval(() => void refreshHandWidth(), 500);
    return () => { active = false; window.clearInterval(interval); };
  }, [sessionId]);

  const pair = async () => {
    if (pairing) return;
    setPairing(true);
    setToken("");
    try {
      const response = await apiFetch("/api/sensors/pairings", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: deviceId, workout_session_id: sessionId.trim() || null }),
      });
      if (!response.ok) throw new Error(((await response.json()) as { detail?: string }).detail ?? "Pairing failed.");
      const created = (await response.json()) as { token: string; expires_in_seconds: number };
      setToken(created.token);
      setExpiresInMinutes(Math.round(created.expires_in_seconds / 60));
      setError("");
      void refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Pairing failed.");
    } finally { setPairing(false); }
  };

  const revoke = async (id: string) => {
    const response = await apiFetch(`/api/sensors/pairings/${id}`, { method: "DELETE" });
    if (!response.ok) setError("Could not revoke this pairing.");
    else { setToken(""); void refresh(); }
  };

  return <main className="sensor-page">
    <Link href="/?screen=app">← Back to training</Link>
    <header><p className="eyebrow">Optional connection</p><h1>Experimental sensor</h1><p>Live experimental sensor connection. Raw readings are separate from camera conclusions.</p></header>
    <section className="sensor-panel">
      <h2>Pair an ESP32 or simulator</h2>
      <label>Device ID <input value={deviceId} onChange={event => setDeviceId(event.target.value)} maxLength={64} /></label>
      <button disabled={pairing} onClick={() => void pair()}>Create pairing token</button>
      <label>Workout session ID (optional) <input value={sessionId} onChange={event => setSessionId(event.target.value)} placeholder="Paste current session ID" /></label>
      <p>Enter your current workout session ID before pairing to link incoming raw readings. The backend checks session ownership.</p>
      {token && <div className="sensor-token"><strong>Copy this token now. It is shown only once.</strong><code>{token}</code><p>Expires in {expiresInMinutes} minutes. Put it in the device configuration, never in the browser URL.</p></div>}
    </section>
    {error && <p role="alert">{error}</p>}
    {networkLost && <p role="alert">Connection lost. Trying to reconnect.</p>}
    <section className="sensor-panel">
      <h2>Connection status</h2>
      {devices.length === 0 ? <p>{networkLost ? "Connection lost" : "Not connected"}</p> : devices.map(device => <article key={device.pairing_id}>
        <h3>{device.device_id}</h3>
        <BatchFreshness device={device} networkLost={networkLost} />
        {device.channels.length === 16 ? <SensorMat device={device} handWidth={sessionId.trim() ? handWidth : null} /> : <p>Sensor data unavailable</p>}
        <button onClick={() => void revoke(device.pairing_id)}>Revoke pairing</button>
      </article>)}
    </section>
    <p className="sensor-boundary">Experimental sensor readings are not part of the primary technique result until calibration and validation are complete. The current camera pipeline does not measure pressure, force, weight distribution, contact position or left/right hand loading. The product is not a medical device. The current workflow is post-session review, not live coaching.</p>
    <details><summary>Connection instructions</summary><p>Connect the ESP32 and laptop to the same Wi-Fi. Send telemetry to the laptop LAN address on port 8001. LAN HTTP is a prototype-only transport; restrict it to your local network. Your phone may use an HTTPS tunnel to view this PWA.</p></details>
  </main>;
}
