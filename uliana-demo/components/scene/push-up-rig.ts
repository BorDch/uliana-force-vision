import * as THREE from 'three';

export const CYCLE_SECONDS = 4.6;
export const MAT_TOP = 0.06;
export const UPPER_ARM = 0.325;
export const FOREARM = 0.31;
export const BODY_LENGTH = 1.49;
const v = (x: number, y: number, z = 0) => new THREE.Vector3(x, y, z);

// Quintic easing: zero velocity and acceleration at both ends of every stroke.
const ease = (t: number) => t * t * t * (t * (t * 6 - 15) + 10);
export function depthAt(seconds: number) {
  const t = ((seconds % CYCLE_SECONDS) + CYCLE_SECONDS) % CYCLE_SECONDS;
  if (t < 0.5) return 0;
  if (t < 1.9) return ease((t - 0.5) / 1.4);
  if (t < 2.2) return 1;
  if (t < 3.6) return 1 - ease((t - 2.2) / 1.4);
  return 0;
}

function elbowFor(shoulder: THREE.Vector3, wrist: THREE.Vector3, side: number) {
  const delta = wrist.clone().sub(shoulder);
  const distance = delta.length();
  if (distance > UPPER_ARM + FOREARM || distance < Math.abs(UPPER_ARM - FOREARM)) {
    throw new Error('Unreachable push-up arm constraint');
  }
  const axis = delta.normalize();
  const along = (UPPER_ARM ** 2 - FOREARM ** 2 + distance ** 2) / (2 * distance);
  const radius = Math.sqrt(UPPER_ARM ** 2 - along ** 2);
  const pole = v(1, 0, side * 0.85);
  pole.addScaledVector(axis, -pole.dot(axis)).normalize();
  return shoulder.clone().addScaledVector(axis, along).addScaledVector(pole, radius);
}

export function poseAt(depth: number) {
  const ankleCenter = v(1.25, 0.205);
  const shoulderY = THREE.MathUtils.lerp(0.730, 0.46, depth);
  const vertical = shoulderY - ankleCenter.y;
  const shoulder = v(ankleCenter.x - Math.sqrt(BODY_LENGTH ** 2 - vertical ** 2), shoulderY);
  const axis = ankleCenter.clone().sub(shoulder).normalize();
  const normal = v(-axis.y, axis.x);
  const point = (along: number, up = 0, z = 0) => shoulder.clone().addScaledVector(axis, along).addScaledVector(normal, up).add(v(0, 0, z));
  const sides = [-1, 1].map(side => {
    const shoulderJoint = point(0.025, 0, side * 0.185);
    const wrist = v(0.065, MAT_TOP + 0.071, side * 0.29);
    const elbow = elbowFor(shoulderJoint, wrist, side);
    const hip = point(0.63, 0, side * 0.10);
    const knee = point(1.06, 0, side * 0.10);
    const ankle = point(BODY_LENGTH, 0, side * 0.10);
    const toe = v(1.43, MAT_TOP + 0.028, side * 0.10);
    return { side, shoulder: shoulderJoint, elbow, wrist, hip, knee, ankle, toe };
  });
  return { shoulder, axis, normal, point, sides };
}

export type Pose = ReturnType<typeof poseAt>;
