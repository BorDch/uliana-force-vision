# Exporting the scene poster and loop

The revised animation has a 4.6-second cycle. The checked poster and offline review renders use the actual mesh geometry and camera, rendered with Blender; they are not browser screenshots. Automated browser access was blocked by the browser policy. The following procedure records the actual WebGL canvas locally when browser access is available.

1. Run `npm run dev` and open the local URL in Chrome or Edge.
2. Open Developer Tools, choose **Console**, paste the poster snippet below, and press Enter. It downloads `uliana-scene-poster.png` from the raised pose.

```js
window.__ULIANA_CAPTURE__.renderPoster();
window.__ULIANA_CAPTURE__.canvas.toBlob((blob) => {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "uliana-scene-poster.png";
  link.click();
  URL.revokeObjectURL(link.href);
}, "image/png");
```

3. Paste the loop snippet below. It renders two deterministic 4.6-second cycles (9.2 seconds total), captures them at 30 fps, and downloads `uliana-scene-loop.webm`. Keep the tab visible during recording. The capture routine drives the pose explicitly, so the UI play/pause state does not change the export.

```js
const capture = window.__ULIANA_CAPTURE__;
const stream = capture.canvas.captureStream(0);
const track = stream.getVideoTracks()[0];
const chunks = [];
const recorder = new MediaRecorder(stream, { mimeType: "video/webm;codecs=vp9" });
recorder.ondataavailable = (event) => event.data.size && chunks.push(event.data);
recorder.onstop = () => {
  const blob = new Blob(chunks, { type: "video/webm" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "uliana-scene-loop.webm";
  link.click();
  URL.revokeObjectURL(link.href);
};
recorder.start();
for (let frame = 0; frame < 276; frame++) {
  capture.renderAt(frame / 30);
  track.requestFrame();
  await new Promise(resolve => setTimeout(resolve, 1000 / 30));
}
recorder.stop();
stream.getTracks().forEach(track => track.stop());
capture.resume();
```

4. Optional MP4 conversion:

```bash
ffmpeg -i uliana-scene-loop.webm -an -c:v libx264 -pix_fmt yuv420p -movflags +faststart uliana-scene-loop.mp4
```

For repeatable offline geometry checks (Node 22.15+ and Blender 4.5):

```bash
node scripts/export-scene-checks.mjs
blender -b --python scripts/render-scene-checks.py -- scene-checks/desktop-top.json scene-checks/desktop-middle.json scene-checks/desktop-bottom.json scene-checks/mobile-top.json scene-checks/mobile-bottom.json
```

The local page also supports `?scenePose=top`, `?scenePose=middle`, `?scenePose=bottom`, and `?sceneFallback=1` for visual review. These are inspection switches on the existing page, not new routes. Reduced motion uses the browser/OS preference and holds the top pose.
