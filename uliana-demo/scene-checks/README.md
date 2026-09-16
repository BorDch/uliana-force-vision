# Simulation verification

The PNGs in this directory were rendered offline with Blender from the exact meshes and perspective cameras created by `components/scene/studio.ts`. Lighting is an approximation of the web studio. These images are **not WebGL/browser screenshots**.

Inspected: desktop top, middle and bottom; mobile top and bottom. The current poster is the inspected desktop top image. The phone is outside the body silhouette, the full mat remains visible, and hands stay on the two zones.

`constraints.json` reports 121 samples of the motion, checking constant upper/lower arm lengths, the rigid shoulder–hip–ankle line, fixed wrist/ankle positions, surface clearance above the mat, and elbow angles. Projection checks cover top/middle/bottom, four aspect ratios, and the permitted rotation limits. Geometry remains within 84% of the half-frame extent, leaving at least 8% edge clearance.

The cycle is 4.6 seconds: 0.5 s top, 1.4 s lowering, 0.3 s bottom, 1.4 s rising, 1.0 s top. Quintic easing has zero first and second derivatives at stroke boundaries. The last/first poses are identical.

`uliana-studio-loop.mp4` was generated from 138 offline-rendered frames of the same geometry/pose solver, repeated twice: 9.2 seconds, 480×422, 30 fps, 276 frames. The first and last source frames are pixel-identical. It is a review movie with approximate studio lighting, not a WebGL capture or a substitute for browser performance testing.

Performance: approximately 18k triangles, 34 primary geometry/material draw groups, one 2048px shadow map, pixel ratio capped at 1.5. CPU geometry update was about 1–4 ms per pose on this host (including concurrent offline rendering); this is **not a browser FPS measurement**.

TypeScript and the production build passed. Local HTTP checks verify the page and the poster asset. Browser automation was blocked because its security policy could not be verified. Therefore actual desktop/mobile DOM screenshots, play/pause/drag interactions, GPU frame rate, offscreen/tab suspension, reduced-motion emulation and forced WebGL failure remain unverified in the browser. Their implementation was inspected; the static fallback asset was rendered and visually inspected. Do not describe those runtime checks as passed.

## Changed files

- `components/uliana-scene.tsx`: renderer lifecycle, responsive camera integration, input, motion preference, poster fallback and capture handle.
- `components/uliana-hero.tsx`: immediate scene controls and concept caption only.
- `components/scene/studio.ts`: original human surface, materials, studio, phone, mat, sensing zones and camera composition.
- `components/scene/push-up-rig.ts`: fixed contacts, rigid plank axis, arm IK and cycle timing.
- `components/scene/scene.css`: scene-scoped styles only.
- `public/uliana-studio-poster.png`: current fallback from the revised geometry.
- `scripts/export-scene-checks.mjs`, `scripts/render-scene-checks.py`: numerical checks and offline renders.
- `ASSET-LICENSES.md`, `EXPORT.md`, `README.md`, `scene-checks/`: implementation notes and verification artifacts.

No landing-page sections, routes, product headings, ML code, recorded-session results or pressure-processing logic were changed.
