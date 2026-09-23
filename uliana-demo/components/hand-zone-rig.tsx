"use client";

import { useEffect, useRef } from "react";

type Props = {
  className?: string;
  /** Accessible description of the animation. */
  label: string;
  /** Rep cycle in seconds; matches the studio simulation cycle length. */
  cycleSeconds?: number;
};

const ACCENT = "#ad573f";
const ACCENT_SOFT = "rgba(173, 87, 63, 0.28)";
const INK = "#3a3d3a";
const INK_SOFT = "rgba(58, 61, 58, 0.34)";
const MAT = "rgba(120, 104, 90, 0.34)";

/**
 * A small, dependency-free canvas anchor for the hero and thesis sections.
 *
 * Left: a side-view push-up rig. Right: the two hand zones with a relative
 * pulse that follows the same rep cycle. The loop is periodic (raised cosine),
 * so the first and last frames match. Work is skipped while the canvas is
 * offscreen, while the tab is hidden, and entirely when the visitor prefers
 * reduced motion (a single static frame is drawn instead).
 */
export function HandZoneRig({ className, label, cycleSeconds = 4.6 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let reduced = motion.matches;
    let disposed = false;
    let frame = 0;
    let running = false;
    let visible = false;
    let elapsed = 0;
    let lastTime = 0;
    let width = 0;
    let height = 0;
    let ratio = 1;

    const resize = () => {
      ratio = Math.min(window.devicePixelRatio || 1, 1.5);
      width = canvas.clientWidth || 300;
      height = canvas.clientHeight || 140;
      canvas.width = Math.max(1, Math.round(width * ratio));
      canvas.height = Math.max(1, Math.round(height * ratio));
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      draw();
    };

    const draw = () => {
      const w = width;
      const h = height;
      context.clearRect(0, 0, w, h);
      const phase = reduced ? 0.18 : (elapsed / cycleSeconds) % 1;
      const press = 0.5 - 0.5 * Math.cos(Math.PI * 2 * phase);
      const eased = press * press * (3 - 2 * press);

      // Mat
      context.strokeStyle = MAT;
      context.lineWidth = 1.5;
      context.beginPath();
      context.moveTo(w * 0.02, h * 0.86);
      context.lineTo(w * 0.6, h * 0.86);
      context.stroke();

      // Straight body line: shoulder to ankle. Hip and knee sit along it.
      const shoulder = { x: w * 0.2, y: h * (0.46 + eased * 0.14) };
      const ankle = { x: w * 0.55, y: h * 0.82 };
      const along = (t: number) => ({
        x: shoulder.x + (ankle.x - shoulder.x) * t,
        y: shoulder.y + (ankle.y - shoulder.y) * t,
      });
      const hip = along(0.42);
      const knee = along(0.76);
      const wrist = { x: w * 0.115, y: h * 0.82 };

      // Arm: straight at the top of the rep, bent at the bottom.
      const mid = { x: (shoulder.x + wrist.x) / 2, y: (shoulder.y + wrist.y) / 2 };
      const control = { x: mid.x - w * 0.12 * eased, y: mid.y - h * 0.06 * (1 - eased) };

      context.strokeStyle = INK;
      context.lineWidth = 4;
      context.lineCap = "round";
      context.lineJoin = "round";
      context.beginPath();
      context.moveTo(wrist.x, wrist.y);
      context.quadraticCurveTo(control.x, control.y, shoulder.x, shoulder.y);
      context.stroke();

      context.lineWidth = 5;
      context.beginPath();
      context.moveTo(shoulder.x, shoulder.y);
      context.lineTo(ankle.x, ankle.y);
      context.stroke();

      context.lineWidth = 3;
      context.strokeStyle = INK_SOFT;
      context.beginPath();
      context.moveTo(hip.x, hip.y);
      context.lineTo(knee.x, knee.y);
      context.stroke();

      // Head at the shoulder end of the body line.
      const headAngle = Math.atan2(ankle.y - shoulder.y, ankle.x - shoulder.x);
      context.fillStyle = ACCENT;
      context.beginPath();
      context.arc(
        shoulder.x - Math.cos(headAngle) * w * 0.03,
        shoulder.y - Math.sin(headAngle) * w * 0.03 - h * 0.02,
        Math.max(5, w * 0.024),
        0,
        Math.PI * 2,
      );
      context.fill();

      for (const joint of [shoulder, hip, knee]) {
        context.fillStyle = "#fffaf2";
        context.strokeStyle = ACCENT;
        context.lineWidth = 1.5;
        context.beginPath();
        context.arc(joint.x, joint.y, 2.6, 0, Math.PI * 2);
        context.fill();
        context.stroke();
      }

      // Hand zones: two front-view pads with a pulse that follows the rep.
      const pulse = 0.5 - 0.5 * Math.cos(Math.PI * 2 * phase + Math.PI * 0.35);
      const zones = [
        { x: w * 0.72, y: h * 0.5, share: 0.5 + 0.05 * Math.sin(Math.PI * 2 * phase) },
        { x: w * 0.9, y: h * 0.5, share: 0.5 - 0.05 * Math.sin(Math.PI * 2 * phase) },
      ];
      zones.forEach((zone, index) => {
        const localPulse = index === 0 ? pulse : 1 - pulse;
        context.fillStyle = ACCENT_SOFT;
        context.beginPath();
        context.ellipse(zone.x, zone.y, w * 0.062, h * 0.13, 0, 0, Math.PI * 2);
        context.fill();
        context.strokeStyle = ACCENT;
        context.lineWidth = 1.5;
        context.beginPath();
        context.ellipse(zone.x, zone.y, w * 0.062, h * 0.13, 0, 0, Math.PI * 2);
        context.stroke();
        context.globalAlpha = 0.3 + 0.6 * localPulse;
        context.beginPath();
        context.ellipse(
          zone.x,
          zone.y,
          w * 0.062 + localPulse * w * 0.03,
          h * 0.13 + localPulse * h * 0.045,
          0,
          0,
          Math.PI * 2,
        );
        context.stroke();
        context.globalAlpha = 1;

        // Relative share bar. Illustrative split, not a measured force value.
        const barY = h * 0.79;
        context.strokeStyle = INK_SOFT;
        context.lineWidth = 3;
        context.beginPath();
        context.moveTo(zone.x - w * 0.05, barY);
        context.lineTo(zone.x + w * 0.05, barY);
        context.stroke();
        context.strokeStyle = ACCENT;
        context.beginPath();
        context.moveTo(zone.x - w * 0.05, barY);
        context.lineTo(zone.x - w * 0.05 + w * 0.1 * (zone.share / 0.6), barY);
        context.stroke();
      });

      // Phase tick so the loop reads as one rep rather than a drifting blur.
      context.strokeStyle = INK_SOFT;
      context.lineWidth = 2;
      context.beginPath();
      context.moveTo(w * 0.02, h * 0.94);
      context.lineTo(w * 0.02 + w * 0.6 * phase, h * 0.94);
      context.stroke();
    };

    const loop = (time: number) => {
      frame = 0;
      if (!running) return;
      const delta = lastTime ? Math.min((time - lastTime) / 1000, 0.05) : 0;
      lastTime = time;
      elapsed += delta;
      draw();
      frame = requestAnimationFrame(loop);
    };

    const start = () => {
      if (running || reduced || disposed) return;
      running = true;
      lastTime = 0;
      if (!frame) frame = requestAnimationFrame(loop);
    };
    const stop = () => {
      running = false;
      lastTime = 0;
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
    };
    const sync = () => {
      if (visible && !document.hidden) start();
      else stop();
    };
    const onPreference = () => {
      reduced = motion.matches;
      if (reduced) {
        stop();
        elapsed = 0;
        draw();
      } else {
        sync();
      }
    };

    const observer = new IntersectionObserver((entries) => {
      visible = entries.some((entry) => entry.isIntersecting);
      sync();
    }, { rootMargin: "80px" });
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(canvas);
    observer.observe(canvas);
    document.addEventListener("visibilitychange", sync);
    motion.addEventListener("change", onPreference);

    resize();
    visible = true;
    sync();

    return () => {
      disposed = true;
      stop();
      resizeObserver.disconnect();
      observer.disconnect();
      document.removeEventListener("visibilitychange", sync);
      motion.removeEventListener("change", onPreference);
    };
  }, [cycleSeconds]);

  return <canvas ref={canvasRef} className={className} role="img" aria-label={label} />;
}
