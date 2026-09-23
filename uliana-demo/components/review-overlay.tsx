"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { HandWidthVisual } from "@/components/mobile-video-review";

export type ReviewMoment = { rep_id: number; timestamp_ms: number; shoulder: Point; hip: Point; ankle: Point; target: Point; image_width_px: number; image_height_px: number };
type Point = { x: number; y: number };
export function reviewSeekMs(rep: { start_ms: number; bottom_ms?: number }, moment?: ReviewMoment) {
  return moment?.timestamp_ms ?? rep.bottom_ms ?? rep.start_ms;
}
type RepInterval = { start_ms: number; end_ms: number };
export function handWidthGuideXs(result: HandWidthVisual | null) {
  if (!result || result.hand_width_cm === null || result.shoulder_width_cm <= 0 || !result.expected_shoulders) return null;
  const leftShoulder = result.expected_shoulders.left_x;
  const rightShoulder = result.expected_shoulders.right_x;
  const center = (leftShoulder + rightShoulder) / 2;
  const handSpan = Math.abs(rightShoulder - leftShoulder) * result.hand_width_cm / result.shoulder_width_cm;
  return { leftShoulder, rightShoulder, leftHand: center - handSpan / 2, rightHand: center + handSpan / 2 };
}
export function ReviewOverlay({ video, moment, interval, skeletonInVideo = false, handWidth = null }: { video: HTMLVideoElement | null; moment?: ReviewMoment; interval?: RepInterval; skeletonInVideo?: boolean; handWidth?: HandWidthVisual | null }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [time, setTime] = useState(0);
  useEffect(() => {
    if (!video) return;
    const update = () => setTime(video.currentTime * 1000);
    video.addEventListener("timeupdate", update);
    video.addEventListener("seeked", update);
    update();
    return () => { video.removeEventListener("timeupdate", update); video.removeEventListener("seeked", update); };
  }, [video]);
  const draw = useCallback(() => {
    const element = canvas.current;
    if (!element || !video) return;
    const rect = video.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    const width = Math.round(rect.width * ratio);
    const height = Math.round(rect.height * ratio);
    if (element.width !== width) element.width = width;
    if (element.height !== height) element.height = height;
    const context = element.getContext("2d");
    if (!context) return;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, rect.width, rect.height);
    if (!moment) return;
    const inRepetition = Boolean(interval && time >= interval.start_ms && time <= interval.end_ms);
    const atReviewMoment = Math.abs(time - moment.timestamp_ms) <= 700;
    if (!inRepetition && !atReviewMoment) return;
    const sourceWidth = video.videoWidth || moment.image_width_px;
    const sourceHeight = video.videoHeight || moment.image_height_px;
    if (!sourceWidth || !sourceHeight) return;
    const scale = Math.min(rect.width / sourceWidth, rect.height / sourceHeight);
    const visibleWidth = sourceWidth * scale, visibleHeight = sourceHeight * scale;
    const offsetX = (rect.width - visibleWidth) / 2, offsetY = (rect.height - visibleHeight) / 2;
    const point = (p: Point) => ({ x: offsetX + p.x * visibleWidth, y: offsetY + p.y * visibleHeight });
    const shoulder = point(moment.shoulder), hip = point(moment.hip), ankle = point(moment.ankle), target = point(moment.target);
    context.lineCap = "round";
    context.lineJoin = "round";
    // The annotated video has the actual pose for each frame. A saved frame is only shown at its own moment.
    if (!skeletonInVideo && atReviewMoment) {
      context.save(); context.globalAlpha = 0.9;
      context.beginPath(); context.moveTo(shoulder.x, shoulder.y); context.lineTo(hip.x, hip.y); context.lineTo(ankle.x, ankle.y);
      context.strokeStyle = "#75937b"; context.lineWidth = 2.5; context.stroke();
      context.restore();
    }

    // A dark solid rail keeps the warm dashed reference distinct from the pose line.
    context.beginPath(); context.moveTo(shoulder.x, shoulder.y); context.lineTo(ankle.x, ankle.y);
    context.strokeStyle = "#493a32"; context.lineWidth = 5; context.stroke();
    context.setLineDash([7, 5]);
    context.strokeStyle = "#f8e6d0"; context.lineWidth = 2.5; context.stroke();
    context.setLineDash([]);

    context.font = "600 10px system-ui, sans-serif";
    const caption = "Reference alignment";
    const labelWidth = context.measureText(caption).width + 14;
    const clearance = (x: number, y: number, p: { x: number; y: number }) =>
      Math.hypot(Math.max(x - p.x, 0, p.x - x - labelWidth), Math.max(y - p.y, 0, p.y - y - 18));
    const labelPositions = [0.1, 0.9].flatMap(fraction => {
      const anchorX = shoulder.x + (ankle.x - shoulder.x) * fraction;
      const anchorY = shoulder.y + (ankle.y - shoulder.y) * fraction;
      return [-34, 12].map(verticalOffset => {
        const x = Math.max(6, Math.min(rect.width - labelWidth - 6, anchorX - labelWidth / 2));
        const y = Math.max(6, Math.min(rect.height - 55, anchorY + verticalOffset));
        return { x, y, clearance: Math.min(clearance(x, y, hip), clearance(x, y, target)) };
      });
    });
    const labelPosition = labelPositions.reduce((best, candidate) => candidate.clearance > best.clearance ? candidate : best);
    const labelX = labelPosition.x;
    const labelY = labelPosition.y;
    context.save(); context.globalAlpha = 0.67;
    context.fillStyle = "#493a32";
    context.beginPath(); context.roundRect(labelX, labelY, labelWidth, 18, 5); context.fill();
    context.fillStyle = "#fff3e4";
    context.fillText(caption, labelX + 7, labelY + 12);
    context.restore();

    const atHandWidthMoment = Math.abs(time - moment.timestamp_ms) <= 500;
    const guides = handWidthGuideXs(handWidth);
    if (atHandWidthMoment && guides) {
      const leftShoulderX = offsetX + guides.leftShoulder * visibleWidth;
      const rightShoulderX = offsetX + guides.rightShoulder * visibleWidth;
      const leftHandX = offsetX + guides.leftHand * visibleWidth;
      const rightHandX = offsetX + guides.rightHand * visibleWidth;
      const guide = (x: number, label: string, color: string, dashed: boolean, labelY: number) => {
        context.save(); context.globalAlpha = .78;
        context.beginPath(); context.moveTo(x, offsetY + 5); context.lineTo(x, offsetY + visibleHeight - 5);
        context.setLineDash(dashed ? [5, 4] : []); context.strokeStyle = color; context.lineWidth = 2; context.stroke();
        context.setLineDash([]); context.font = "700 10px system-ui, sans-serif"; context.textAlign = "center";
        const labelWidth = context.measureText(label).width + 8;
        const labelX = Math.max(offsetX + labelWidth / 2, Math.min(offsetX + visibleWidth - labelWidth / 2, x));
        context.fillStyle = "rgba(255,250,243,.86)"; context.fillRect(labelX - labelWidth / 2, labelY - 10, labelWidth, 13);
        context.fillStyle = color; context.fillText(label, labelX, labelY); context.restore();
      };
      guide(leftShoulderX, "Shoulder L", "#8D6E63", true, offsetY + 15);
      guide(rightShoulderX, "Shoulder R", "#8D6E63", true, offsetY + 15);
      guide(leftHandX, "Hand L", "#1976D2", false, offsetY + visibleHeight - 9);
      guide(rightHandX, "Hand R", "#1976D2", false, offsetY + visibleHeight - 9);
    }

    if (!atReviewMoment) return;

    const markerRadius = Math.max(9, Math.min(15, rect.width * 0.037));
    context.strokeStyle = "#ee6b5d"; context.lineWidth = 3.5;
    context.beginPath(); context.arc(hip.x, hip.y, markerRadius, 0, Math.PI * 2); context.stroke();
    const dx = target.x - hip.x, dy = target.y - hip.y, length = Math.hypot(dx, dy);
    if (length > 3) {
      // The stored target is the nearest point on the shoulder–ankle line.
      context.beginPath(); context.moveTo(hip.x, hip.y); context.lineTo(target.x, target.y);
      context.strokeStyle = "#493a32"; context.lineWidth = 7; context.stroke();
      context.strokeStyle = "#ee6b5d"; context.lineWidth = 3.5; context.stroke();
      const angle = Math.atan2(dy, dx);
      const headLength = Math.min(12, Math.max(7, length * 0.35));
      const headWidth = Math.max(5, headLength * 0.7);
      const baseX = target.x - headLength * Math.cos(angle);
      const baseY = target.y - headLength * Math.sin(angle);
      context.beginPath(); context.moveTo(target.x, target.y);
      context.lineTo(baseX + headWidth * Math.sin(angle), baseY - headWidth * Math.cos(angle));
      context.lineTo(baseX - headWidth * Math.sin(angle), baseY + headWidth * Math.cos(angle));
      context.closePath(); context.fillStyle = "#ee6b5d"; context.fill();
      context.strokeStyle = "#493a32"; context.lineWidth = 1.5; context.stroke();
    }
  }, [handWidth, interval, moment, skeletonInVideo, time, video]);
  useEffect(() => { draw(); const observer = new ResizeObserver(draw); if (video) observer.observe(video); return () => observer.disconnect(); }, [draw, video]);
  return <canvas ref={canvas} className="review-video-overlay" aria-hidden="true" />;
}
