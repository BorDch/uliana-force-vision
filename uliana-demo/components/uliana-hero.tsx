"use client";

import { ArrowDown, Pause, Play, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { UlianaScene } from "@/components/uliana-scene";

export function UlianaHero() {
  const [available, setAvailable] = useState(false);
  const [reduced, setReduced] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [resetKey, setResetKey] = useState(0);

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(preference.matches);
    if (!preference.matches) setPlaying(true);
    const handleChange = () => { setPlaying(!preference.matches); setReduced(preference.matches); };
    preference.addEventListener("change", handleChange);
    return () => preference.removeEventListener("change", handleChange);
  }, []);

  return (
    <section id="top" className="hero-shell" aria-labelledby="hero-title">
      <header className="site-header">
        <a className="brand" href="#top" aria-label="ULIANA home">
          <span className="brand-mark" aria-hidden="true">U<span>·</span></span>
          <span className="brand-name">ULIANA</span>
        </a>
        <div className="header-note">Skoltech Team 10</div>
      </header>

      <div className="hero-layout">
        <div className="hero-copy">
          <div className="eyebrow"><span /> Movement, made visible</div>
          <h1 id="hero-title">See your movement.<br />Understand your load.</h1>
          <p>
            Video shows the movement. Localised hand signals add another view. ULIANA brings both into one recorded-session review.
          </p>
        </div>

        <div className="scene-column">
          <div className="scene-card">
            <div className="scene-topbar">
              <TooltipProvider>
                <div className="scene-actions">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="scene-icon-button"
                        disabled={!available || reduced}
                        onClick={() => setPlaying((value) => !value)}
                        aria-label={playing ? "Pause movement" : "Play movement"}
                      >
                        {playing ? <Pause /> : <Play />}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>{playing ? "Pause movement" : "Play movement"}</TooltipContent>
                  </Tooltip>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="scene-icon-button"
                        disabled={!available}
                        onClick={() => setResetKey((value) => value + 1)}
                        aria-label="Reset scene view"
                      >
                        <RotateCcw />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>Reset view</TooltipContent>
                  </Tooltip>
                </div>
              </TooltipProvider>
            </div>

            <UlianaScene playing={playing} resetKey={resetKey} onAvailable={setAvailable} />

            <div className="drag-hint" aria-hidden="true" style={{ visibility: available ? 'visible' : 'hidden' }}>
              <span className="drag-icon">↔</span> Drag to rotate
            </div>
          </div>
          <p className="scene-caption">Product concept — simulated movement and sensor response.</p>
        </div>

        <div className="hero-actions">
          <Button asChild size="lg" className="primary-cta">
            <a href="#session-review">Review a demo session <ArrowDown aria-hidden="true" /></a>
          </Button>
          <Button asChild variant="ghost" size="lg" className="secondary-cta">
            <a href="#problem">Why ULIANA</a>
          </Button>
        </div>

        <p className="hero-footnote">Recorded-video analysis · paired illustrative sensing</p>
      </div>
    </section>
  );
}
