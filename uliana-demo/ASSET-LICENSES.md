# Asset and licence notes

- The articulated mannequin, exercise mat, phone/tripod, sensing zones, camera overlay, and all other scene geometry are generated procedurally in the project with Three.js. No third-party 3D model or remote runtime asset is used.
- Three.js is used under the MIT License. See `node_modules/three/LICENSE` after dependency installation or https://github.com/mrdoob/three.js/blob/dev/LICENSE.
- Interface icons come from Lucide, which is included in the project dependencies and distributed under the ISC License. See https://lucide.dev/license.
- `public/uliana-scene-fallback.svg` and `public/favicon.svg` are original project assets created for this demo.

## Revised studio simulation

- `components/scene/studio.ts` creates an original continuous, profiled human surface around the articulated pose solver. Fitted shirt, trousers, hands, head/hair and trainers are authored locally; no downloaded human model, rig, texture, or runtime service is used.
- Three.js `RoundedBoxGeometry` uses the same MIT licence as Three.js. No additional 3D framework was installed.
- `public/uliana-studio-poster.png` is an offline Blender render of the exact scene meshes and camera exported from the implementation. It is the current fallback. The older SVG remains unused.
- Images and the review movie in `scene-checks/` are original renders of those same meshes. Blender approximates the lighting; these are not browser screenshots. Blender is used only as a temporary offline verification tool, not a site dependency. Its GPL licence does not apply to rendered output (https://www.blender.org/about/license/).
