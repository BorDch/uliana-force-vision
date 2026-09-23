"use client";

import { ArrowRight, CheckCircle2, Play } from "lucide-react";

const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export function UlianaHero() {
  return (
    <section id="top" className="consumer-hero" aria-labelledby="hero-title">
      <div className="consumer-hero-copy" data-reveal>
        <p className="section-kicker">ULIANA</p>
        <h1 id="hero-title">Train alone.<br />Don’t review alone.</h1>
        <p className="consumer-hero-lede">Turn one phone recording into a clear push-up review: see how many repetitions you completed, what went well, which exact repetition deserves attention, and what to focus on next.</p>
        <div className="consumer-hero-actions">
          <a className="landing-button landing-button-primary" href={`${base}/?screen=demo`}>Explore a sample review <ArrowRight aria-hidden="true" /></a>
          <a className="landing-button landing-button-secondary" href="#pilot">Join the pilot</a>
        </div>
        <p className="consumer-hero-caption">From a continuous recording to repetition-by-repetition feedback and progress you can follow.</p>
      </div>
      <div className="sample-window" aria-label="Prepared ULIANA sample review" data-reveal>
        <div className="sample-window-bar"><span>Prepared sample</span><span>Camera review</span></div>
        <div className="sample-video-wrap">
          <video src={`${base}/demo/demo-annotated.mp4`} muted playsInline autoPlay loop preload="metadata" aria-label="Annotated sample push-up recording" />
          <span className="sample-rep-badge"><Play aria-hidden="true" /> Rep 1 of 5</span>
        </div>
        <div className="sample-summary">
          <p>Your session summary</p><h2>One clear focus for your next session</h2>
          <div className="sample-summary-row"><CheckCircle2 aria-hidden="true" /><span><b>What went well</b>No issue was detected in the available range-of-motion check.</span></div>
          <a href={`${base}/?screen=demo`}>Watch repetition 1 <ArrowRight aria-hidden="true" /></a>
        </div>
      </div>
    </section>
  );
}
