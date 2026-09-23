"use client";

import { Download, Pause, Play, RotateCcw, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { demoReps, setSummary, type DemoRep } from "@/lib/demo-session";

const assetBasePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

function linePath(values: number[], width = 520, height = 170) {
  const step = width / (values.length - 1);
  return values
    .map((value, index) => `${index === 0 ? "M" : "L"}${(index * step).toFixed(1)} ${(height - (value / 100) * height).toFixed(1)}`)
    .join(" ");
}

function statusLabel(status: DemoRep["status"]) {
  if (status === "strong") return "Clear pattern";
  if (status === "review") return "Review";
  return "Consistent";
}

function SignalChart({ rep, kind }: { rep: DemoRep; kind: "movement" | "hands" }) {
  const values = kind === "movement" ? rep.movement : rep.leftSignal;
  const second = kind === "hands" ? rep.rightSignal : null;

  return (
    <svg className="review-chart" viewBox="0 0 520 190" role="img" aria-label={kind === "movement" ? `Movement trace for repetition ${rep.id}` : `Relative left and right hand signals for repetition ${rep.id}`}>
      <path className="review-chart-grid" d="M0 18H520M0 61H520M0 104H520M0 147H520M0 189H520" />
      <path className={kind === "movement" ? "review-movement-line" : "review-left-line"} d={linePath(values)} />
      {second ? <path className="review-right-line" d={linePath(second)} /> : null}
    </svg>
  );
}

export function SessionDashboard() {
  const [selectedId, setSelectedId] = useState(2);
  const [playing, setPlaying] = useState(() => {
    if (typeof window === "undefined") return false;
    return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  });
  const [playhead, setPlayhead] = useState(0);
  const animationRef = useRef<number | null>(null);
  const lastFrameRef = useRef<number | null>(null);
  const repButtonRefs = useRef<Record<number, HTMLButtonElement | null>>({});
  const rep = demoReps[selectedId - 1];

  const selectRep = (id: number) => {
    setSelectedId(id);
    setPlayhead(0);
  };

  const handleRepKeys = (event: KeyboardEvent<HTMLDivElement>) => {
    const keys = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"];
    if (!keys.includes(event.key)) return;
    event.preventDefault();
    let next = selectedId;
    if (event.key === "Home") next = demoReps[0].id;
    else if (event.key === "End") next = demoReps[demoReps.length - 1].id;
    else {
      const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1;
      next = ((selectedId - 1 + step + demoReps.length) % demoReps.length) + 1;
    }
    selectRep(next);
    repButtonRefs.current[next]?.focus();
  };

  useEffect(() => {
    const tick = (time: number) => {
      if (lastFrameRef.current !== null) {
        const elapsed = time - lastFrameRef.current;
        setPlayhead((value) => (value + elapsed / 28) % 100);
      }
      lastFrameRef.current = time;
      animationRef.current = requestAnimationFrame(tick);
    };
    animationRef.current = requestAnimationFrame(tick);
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [playing]);

  const bodyOffset = useMemo(() => {
    const normalized = Math.sin((playhead / 100) * Math.PI);
    return Math.round(normalized * 10);
  }, [playhead]);

  const downloadSummary = () => {
    const text = [
      "ULIANA — demo session summary",
      "Illustrative dashboard data; not a measured force report.",
      "",
      `Set: ${setSummary.reps} push-up repetitions`,
      `Pace: ${setSummary.pace}`,
      `Movement: ${setSummary.movement}`,
      `Hand-zone pattern: ${setSummary.load}`,
      "",
      ...demoReps.map((item) => `Rep ${item.id} · ${statusLabel(item.status)} · ${item.duration} · ${item.note}`),
    ].join("\n");

    const file = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(file);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "uliana-demo-session-summary.txt";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section id="session-review" className="review-section" aria-labelledby="review-title">
      <div className="review-intro">
        <div data-reveal="self">
          <div className="section-kicker light-kicker">Demo workspace</div>
          <h2 id="review-title">Read the whole set.<br />Then inspect one rep.</h2>
        </div>
        <p data-reveal="self">
          A calm review surface for recorded sessions: movement on one side, two localised hand-zone signals on the other, and plain-language observations in between.
        </p>
      </div>

      <div className="review-shell" data-reveal>
        <header className="review-header">
          <div className="review-session-title">
            <span className="demo-badge"><Sparkles aria-hidden="true" /> Illustrative — not measured data</span>
            <div>
              <h3>Push-up set · session 01</h3>
              <p>Fixed-view recording · {demoReps.length} repetitions · {setSummary.pace}</p>
            </div>
          </div>
          <Button variant="outline" className="download-button" onClick={downloadSummary}>
            <Download aria-hidden="true" /> Download summary
          </Button>
        </header>

        <div className="set-strip" aria-label={`Values for repetition ${rep.id} of ${demoReps.length}`}>
          <div><span>Rep {rep.id} of {demoReps.length} · tempo</span><strong>{rep.duration}</strong></div>
          <div><span>Range in this rep</span><strong>{rep.depth}</strong></div>
          <div><span>Hand-zone pattern</span><strong>{rep.balanceDetail}</strong></div>
        </div>

        <div className="review-workspace">
          <div className="recording-panel">
            <div className="recording-stage">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`${assetBasePath}/uliana-studio-poster.webp`}
                alt="Abstract simulated push-up scene used as a placeholder for a recorded camera view"
                width={740}
                height={650}
                loading="lazy"
                decoding="async"
              />
              <div className="recording-shade" />
              <div className="recording-label">Illustrative clip · not a measured recording</div>
              <div className="pose-trace" aria-hidden="true" style={{ transform: `translateY(${bodyOffset}px)` }}>
                <span className="joint joint-shoulder" />
                <span className="joint joint-hip" />
                <span className="joint joint-knee" />
                <span className="trace-line trace-torso" />
                <span className="trace-line trace-leg" />
              </div>
              <Button
                size="icon"
                className="recording-play"
                onClick={() => setPlaying((value) => !value)}
                aria-label={playing ? "Pause illustrative clip" : "Play illustrative clip"}
              >
                {playing ? <Pause /> : <Play />}
              </Button>
            </div>

            <div className="playback-row">
              <button className="mini-control" onClick={() => { setPlayhead(0); setPlaying(false); }} aria-label="Restart clip">
                <RotateCcw aria-hidden="true" />
              </button>
              <Slider
                min={0}
                max={100}
                step={1}
                value={[playhead]}
                onValueChange={(value) => { setPlayhead(value[0] ?? 0); setPlaying(false); }}
                aria-label="Illustrative clip position"
              />
              <span>{(playhead * 0.028).toFixed(1)} / 2.8 s</span>
            </div>

            <div
              className="rep-picker"
              role="radiogroup"
              aria-label="Choose a repetition"
              onKeyDown={handleRepKeys}
            >
              {demoReps.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  ref={(node) => { repButtonRefs.current[item.id] = node; }}
                  className={`rep-button rep-${item.status}`}
                  data-active={item.id === selectedId}
                  role="radio"
                  aria-checked={item.id === selectedId}
                  tabIndex={item.id === selectedId ? 0 : -1}
                  onClick={() => selectRep(item.id)}
                >
                  <span>{item.id}</span>
                  <small>{item.status === "review" ? "Review" : item.duration}</small>
                  <i className="rep-underline" aria-hidden="true" />
                </button>
              ))}
            </div>
            <p className="rep-hint">
              Click a repetition, or use ← → / Home / End to move through the set. All values here are illustrative.
            </p>
          </div>

          <div className="insight-panel">
            <div className="insight-heading">
              <div>
                <span aria-live="polite">Repetition {rep.id} of {demoReps.length}</span>
                <h3>{statusLabel(rep.status)}</h3>
              </div>
              <span className={`status-pill status-${rep.status}`}>{rep.duration}</span>
            </div>
            <p className="rep-note">{rep.note}</p>

            <Tabs defaultValue="overview" className="review-tabs">
              <TabsList aria-label="Dashboard views">
                <TabsTrigger value="overview">Overview</TabsTrigger>
                <TabsTrigger value="movement">Movement</TabsTrigger>
                <TabsTrigger value="hands">Hand zones</TabsTrigger>
              </TabsList>

              <TabsContent value="overview">
                <div className="qualitative-grid">
                  <article><span>Range</span><strong>{rep.depth}</strong><p>Compared with this set</p></article>
                  <article><span>Body line</span><strong>{rep.alignment}</strong><p>Across the repetition</p></article>
                  <article><span>Hand zones</span><strong>{rep.balance}</strong><p>{rep.balanceDetail}</p></article>
                  <article><span>Tempo</span><strong>{rep.duration}</strong><p>Down · pause · return</p></article>
                </div>
                <div className="tempo-block">
                  <div className="panel-label"><span>Phase split</span><span>Relative time</span></div>
                  <div className="tempo-bar" aria-label={`Lowering ${rep.tempo[0]}%, pause ${rep.tempo[1]}%, return ${rep.tempo[2]}%`}>
                    <span style={{ width: `${rep.tempo[0]}%` }} />
                    <span style={{ width: `${rep.tempo[1]}%` }} />
                    <span style={{ width: `${rep.tempo[2]}%` }} />
                  </div>
                  <div className="tempo-legend"><span>Lower</span><span>Pause</span><span>Return</span></div>
                </div>
              </TabsContent>

              <TabsContent value="movement">
                <div className="chart-heading"><span>Vertical movement pattern</span><span>Top → bottom → top</span></div>
                <SignalChart rep={rep} kind="movement" />
                <p className="chart-note">Shape-normalised trace for reviewing timing and range within this demo set.</p>
              </TabsContent>

              <TabsContent value="hands">
                <div className="chart-heading"><span>Illustrative hand-zone signals</span><span className="chart-legend"><i /> Left <i /> Right</span></div>
                <SignalChart rep={rep} kind="hands" />
                <div className="balance-row">
                  <span>Left {rep.leftShare}%</span>
                  <div><i style={{ width: `${rep.leftShare}%` }} /><i style={{ width: `${rep.rightShare}%` }} /></div>
                  <span>Right {rep.rightShare}%</span>
                </div>
                <p className="chart-note">Relative illustrative signals only. These are not calibrated force measurements.</p>
              </TabsContent>
            </Tabs>
          </div>
        </div>

        <footer className="review-disclaimer">
          Illustrative demo data in the badge above: these numbers are bundled with the page, not measured from a recording.
          Connect evaluated pipeline outputs before presenting a session result. Downloading the summary writes the same illustrative values to a text file.
        </footer>
      </div>
    </section>
  );
}
