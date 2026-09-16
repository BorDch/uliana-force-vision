"use client";

import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { createStudio, INITIAL_PITCH, INITIAL_YAW } from './scene/studio';
import { CYCLE_SECONDS, depthAt } from './scene/push-up-rig';
import './scene/scene.css';

const assetBasePath = process.env.NEXT_PUBLIC_BASE_PATH ?? '';

type Props = { playing: boolean; resetKey: number; onAvailable: (available: boolean) => void };
type Capture = { canvas: HTMLCanvasElement; reset: () => void; renderPoster: () => void; renderAt: (seconds: number) => void; resume: () => void; cycleSeconds: number };
declare global { interface Window { __ULIANA_CAPTURE__?: Capture } }

export function UlianaScene({ playing, resetKey, onAvailable }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const playingRef = useRef(playing);
  const refreshRef = useRef<(() => void) | null>(null);
  const resetRef = useRef<(() => void) | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => { playingRef.current = playing; refreshRef.current?.(); }, [playing]);
  useEffect(() => { resetRef.current?.(); }, [resetKey]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let renderer: THREE.WebGLRenderer;
    const params = new URLSearchParams(window.location.search);
    try {
      if (params.get('sceneFallback') === '1') throw new Error('Requested poster');
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'default' });
    } catch {
      onAvailable(false);
      return;
    }
    const studio = createStudio();
    const canvas = renderer.domElement;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.VSMShadowMap;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', 'A person performs a controlled push-up on a cream mat, with two palm sensing zones and a phone on a tripod.');
    canvas.setAttribute('tabindex', '0');
    canvas.setAttribute('aria-keyshortcuts', 'ArrowLeft ArrowRight ArrowUp ArrowDown Home');
    canvas.setAttribute('title', 'Drag horizontally or use arrow keys to rotate; Home resets the view.');
    host.appendChild(canvas);

    let elapsed = 0, lastTime = 0, frame = 0;
    let visible = false, lost = false, disposed = false, forcedPose: number | null = null;
    let yaw = INITIAL_YAW, pitch = INITIAL_PITCH;
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let reduced = motion.matches;
    const preset = params.get('scenePose');
    if (preset) forcedPose = preset === 'bottom' ? 2.05 : preset === 'middle' ? 1.2 : 0;

    const canRender = () => visible && !document.hidden && !lost && !disposed;
    const render = (now: number) => {
      frame = 0;
      if (!canRender()) { lastTime = 0; return; }
      const delta = lastTime ? Math.min((now - lastTime) / 1000, .05) : 0;
      lastTime = now;
      if (playingRef.current && !reduced && forcedPose === null) elapsed = (elapsed + delta) % CYCLE_SECONDS;
      studio.update(depthAt(reduced ? 0 : forcedPose ?? elapsed));
      renderer.render(studio.scene, studio.camera);
      if (playingRef.current && !reduced && forcedPose === null) frame = requestAnimationFrame(render);
    };
    const refresh = () => {
      if (canRender() && !frame) frame = requestAnimationFrame(render);
    };
    const stop = () => { cancelAnimationFrame(frame); frame = 0; lastTime = 0; };
    refreshRef.current = refresh;
    const compose = () => studio.compose(host.clientWidth / Math.max(host.clientHeight, 1), yaw, pitch);
    resetRef.current = () => { yaw = INITIAL_YAW; pitch = INITIAL_PITCH; compose(); refresh(); };
    const resize = new ResizeObserver(() => {
      if (!host.clientWidth || !host.clientHeight) return;
      renderer.setSize(host.clientWidth, host.clientHeight, false);
      compose();refresh();
    });
    resize.observe(host);
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible) refresh(); else stop();
    }, { threshold: .02 });
    observer.observe(host);
    const visibility = () => { if (document.hidden) stop(); else refresh(); };
    document.addEventListener('visibilitychange', visibility);
    const motionChanged = () => { reduced = motion.matches; elapsed = 0; stop(); refresh(); };
    motion.addEventListener('change', motionChanged);

    let pointer: { id: number; x: number; y: number; yaw: number; pitch: number; touch: boolean } | null = null;
    const down = (event: PointerEvent) => {
      if (!event.isPrimary || event.button !== 0) return;
      pointer = { id: event.pointerId, x: event.clientX, y: event.clientY, yaw, pitch, touch: event.pointerType === 'touch' };
      canvas.setPointerCapture(event.pointerId);
    };
    const move = (event: PointerEvent) => {
      if (!pointer || pointer.id !== event.pointerId) return;
      const dx = event.clientX - pointer.x, dy = event.clientY - pointer.y;
      if (pointer.touch && Math.abs(dy) > Math.abs(dx)) return;
      yaw = THREE.MathUtils.clamp(pointer.yaw - dx * .004, INITIAL_YAW - .50, INITIAL_YAW + .50);
      pitch = THREE.MathUtils.clamp(pointer.pitch + (pointer.touch ? 0 : dy * .0025), .35, .72);
      compose();refresh();
    };
    const up = (event: PointerEvent) => {
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
      pointer = null;
    };
    const keyboard = (event: KeyboardEvent) => {
      if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(event.key)) return;
      event.preventDefault();
      if (event.key === 'Home') { resetRef.current?.(); return; }
      yaw = THREE.MathUtils.clamp(yaw + (event.key === 'ArrowLeft' ? .06 : event.key === 'ArrowRight' ? -.06 : 0), INITIAL_YAW-.50, INITIAL_YAW+.50);
      pitch = THREE.MathUtils.clamp(pitch + (event.key === 'ArrowUp' ? .035 : event.key === 'ArrowDown' ? -.035 : 0), .35,.72);
      compose();refresh();
    };
    const contextLost = (event: Event) => {
      event.preventDefault();lost = true;stop();setReady(false);onAvailable(false);
    };
    canvas.addEventListener('pointerdown',down);
    canvas.addEventListener('pointermove',move);
    canvas.addEventListener('pointerup',up);
    canvas.addEventListener('pointercancel',up);
    canvas.addEventListener('keydown',keyboard);
    canvas.addEventListener('webglcontextlost',contextLost);

    window.__ULIANA_CAPTURE__ = {
      canvas, cycleSeconds: CYCLE_SECONDS,
      reset: () => { forcedPose=null;elapsed=0;lastTime=0;refresh(); },
      renderPoster: () => { stop(); forcedPose=0;studio.update(0);renderer.render(studio.scene,studio.camera); },
      renderAt: seconds => { stop();forcedPose=seconds;studio.update(depthAt(seconds));renderer.render(studio.scene,studio.camera); },
      resume: () => { forcedPose=null;lastTime=0;refresh(); },
    };
    renderer.setSize(host.clientWidth,host.clientHeight,false);
    compose();studio.update(0);renderer.render(studio.scene,studio.camera);
    setReady(true);onAvailable(true);
    return () => {
      disposed=true;stop();resize.disconnect();observer.disconnect();
      document.removeEventListener('visibilitychange',visibility);
      motion.removeEventListener('change',motionChanged);
      canvas.removeEventListener('pointerdown',down);canvas.removeEventListener('pointermove',move);
      canvas.removeEventListener('pointerup',up);canvas.removeEventListener('pointercancel',up);
      canvas.removeEventListener('keydown',keyboard);canvas.removeEventListener('webglcontextlost',contextLost);
      delete window.__ULIANA_CAPTURE__;
      studio.dispose();renderer.dispose();canvas.remove();refreshRef.current=null;resetRef.current=null;
    };
  }, [onAvailable]);

  return <div className={`scene-viewport uliana-studio ${ready ? 'studio-ready' : ''}`} ref={hostRef}>
    <img className="studio-poster" src={`${assetBasePath}/uliana-studio-poster.png`} alt="ULIANA concept: a person holding a raised push-up over two sensing zones, with a phone beside the mat." aria-hidden={ready} />
  </div>;
}
