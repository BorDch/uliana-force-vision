import { useId } from "react";

export interface SensorLayout {
  channel: number;
  x: number; // Percent from the left edge.
  y: number; // Percent from the top edge.
  group: "right" | "left";
}

export interface MatVisualizationProps {
  sensors: SensorLayout[];
  channelData: Record<number, { raw: number; delta: number; hand: boolean }>;
  baselineSet: boolean;
  expectedShoulders?: { left_x: number; right_x: number };
  onSensorClick?: (channel: number) => void;
}

// Channel map from Albert's photo; positions are approximate percentages.
export const SENSOR_LAYOUT: SensorLayout[] = [
  { channel: 13, x: 25, y: 10, group: "left" },
  { channel: 15, x: 12, y: 30, group: "left" },
  { channel: 9, x: 38, y: 30, group: "left" },
  { channel: 14, x: 12, y: 50, group: "left" },
  { channel: 8, x: 38, y: 50, group: "left" },
  { channel: 10, x: 12, y: 70, group: "left" },
  { channel: 12, x: 38, y: 70, group: "left" },
  { channel: 11, x: 25, y: 90, group: "left" },
  { channel: 1, x: 75, y: 10, group: "right" },
  { channel: 4, x: 62, y: 30, group: "right" },
  { channel: 0, x: 88, y: 30, group: "right" },
  { channel: 7, x: 62, y: 50, group: "right" },
  { channel: 2, x: 88, y: 50, group: "right" },
  { channel: 6, x: 62, y: 70, group: "right" },
  { channel: 3, x: 88, y: 70, group: "right" },
  { channel: 5, x: 75, y: 90, group: "right" },
];

type Point = { x: number; y: number };
type Zone = { group: SensorLayout["group"]; kind: "none" | "one" | "many"; points: Point[] };

export function heatmapZones(sensors: SensorLayout[], channelData: MatVisualizationProps["channelData"]): Zone[] {
  return (["left", "right"] as const).map(group => {
    const points = sensors.filter(sensor => sensor.group === group && channelData[sensor.channel]?.hand === true)
      .map(({ x, y }) => ({ x, y: y / 2 }));
    return { group, kind: points.length === 0 ? "none" : points.length === 1 ? "one" : "many", points };
  });
}

function convexHull(points: Point[]): Point[] {
  const sorted = [...points].sort((a, b) => a.x - b.x || a.y - b.y);
  const cross = (a: Point, b: Point, c: Point) =>
    (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
  const lower: Point[] = [];
  const upper: Point[] = [];
  for (const point of sorted) {
    while (lower.length > 1 && cross(lower[lower.length - 2], lower[lower.length - 1], point) <= 0) lower.pop();
    lower.push(point);
  }
  for (const point of sorted.reverse()) {
    while (upper.length > 1 && cross(upper[upper.length - 2], upper[upper.length - 1], point) <= 0) upper.pop();
    upper.push(point);
  }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

export function MatVisualization({ sensors, channelData, baselineSet, expectedShoulders, onSensorClick }: MatVisualizationProps) {
  const id = useId().replaceAll(":", "");
  const zones = baselineSet ? heatmapZones(sensors, channelData) : [];
  return <div className="sensor-mat" role="group" aria-label="Approximate layout of 16 raw sensor channels">
    <svg className="sensor-mat-heatmap" viewBox="0 0 100 50" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <clipPath id={`${id}-left`}><rect x="5" y="0" width="40" height="50" /></clipPath>
        <clipPath id={`${id}-right`}><rect x="55" y="0" width="40" height="50" /></clipPath>
        <radialGradient id={`${id}-orange`}><stop offset="0%" stopColor="#FF9800" stopOpacity=".85" /><stop offset="100%" stopColor="#FF9800" stopOpacity="0" /></radialGradient>
      </defs>
      <rect width="100" height="50" fill={baselineSet ? "#4CAF50" : "#808080"} opacity=".42" />
      {zones.map(zone => <g key={zone.group} data-group={zone.group} clipPath={`url(#${id}-${zone.group})`}>
        {zone.kind === "one" && <circle cx={zone.points[0].x} cy={zone.points[0].y} r="13" fill={`url(#${id}-orange)`} />}
        {zone.kind === "many" && (() => {
          const hull = convexHull(zone.points);
          if (hull.length < 3) {
            const [first, last] = [hull[0], hull[hull.length - 1]];
            return <>
              <defs><linearGradient id={`${id}-${zone.group}-red`} gradientUnits="userSpaceOnUse" x1={first.x} y1={first.y} x2={last.x} y2={last.y}>
                <stop offset="0%" stopColor="#E53935" stopOpacity=".15" /><stop offset="50%" stopColor="#E53935" stopOpacity=".85" /><stop offset="100%" stopColor="#E53935" stopOpacity=".15" />
              </linearGradient></defs>
              <line x1={first.x} y1={first.y} x2={last.x} y2={last.y} stroke={`url(#${id}-${zone.group}-red)`} strokeWidth="14" strokeLinecap="round" />
            </>;
          }
          return <polygon points={hull.map(point => `${point.x},${point.y}`).join(" ")} fill="#E53935" fillOpacity=".5" stroke="#E53935" strokeOpacity=".34" strokeWidth="7" strokeLinejoin="round" />;
        })()}
      </g>)}
      {expectedShoulders && <g className="sensor-shoulder-guides">
        <line x1={expectedShoulders.left_x * 100} y1="0" x2={expectedShoulders.left_x * 100} y2="50" />
        <line x1={expectedShoulders.right_x * 100} y1="0" x2={expectedShoulders.right_x * 100} y2="50" />
        <text x={expectedShoulders.left_x * 100} y="48">Shoulder L</text>
        <text x={expectedShoulders.right_x * 100} y="48">Shoulder R</text>
      </g>}
    </svg>
    <span className="sensor-mat-group sensor-mat-group-right">Right</span>
    <span className="sensor-mat-group sensor-mat-group-left">Left</span>
    {sensors.map(sensor => {
      const reading = channelData[sensor.channel];
      const raw = reading?.raw ?? 0;
      const active = baselineSet && reading?.hand === true;
      const className = `sensor-mat-dot ${active ? "sensor-mat-active" : "sensor-mat-inactive"}`;
      const label = `C${sensor.channel}: raw ${raw}, delta ${baselineSet ? reading?.delta ?? "unavailable" : "unavailable"}, ${active ? "active" : "no touch"}`;
      const style = { left: `${sensor.x}%`, top: `${sensor.y}%` };
      return onSensorClick ?
        <button type="button" className={className} key={sensor.channel} style={style} onClick={() => onSensorClick(sensor.channel)} aria-label={label} title={label}>C{sensor.channel}<small>{raw}</small></button> :
        <span className={className} key={sensor.channel} style={style} aria-label={label} title={label}>C{sensor.channel}<small>{raw}</small></span>;
    })}
    <span className="sensor-mat-position-note">{baselineSet ? "Sensor positions are approximate." : "Waiting for calibrated sensor activity."}</span>
  </div>;
}
