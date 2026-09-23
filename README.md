# ULIANA Prototype Lab

Interactive toy simulation for the frozen IW prototype:

> One push-up, two force channels, one camera, one quality score, and one reliable corrective cue.

## What it demonstrates

- Synthetic left/right force signals and a synchronized push-up cycle
- Pose-derived elbow angle, body-line deviation, and phase
- Interpretable quality scoring
- Confidence-aware abstention when the camera input is unreliable
- Live result packets for a future controller, mobile app, or API
- Session-result export as JSON

## Run locally

Serve the `dist` directory with any static HTTP server:

```bash
python -m http.server 8000 --directory dist
```

Then open `http://localhost:8000`.

## Full website and application-only service

The presentation build keeps recordings and results on the laptop and uses the frozen
`configs/video_processing.json` configuration (SHA-256
`c996926a052622815eb3acb08684a9e3176d39d0d95129f65d9e855bf7f331d9`). It does not perform
live analysis.

One-time setup:

```bash
.venv-video/bin/python -m pip install -e '.[video,demo]'
```

Start the complete website, including the public product story, prepared sample, Presentation mode,
and functional application:

```bash
./scripts/start_demo.sh
```

Start only the functional training workflow:

```bash
./scripts/start_app.sh
```

Both modes use the same frontend components, backend, saved sessions, Coach Summary, and frozen
camera-analysis pipeline. Application-only mode opens the Train dashboard directly at
`http://127.0.0.1:8000/`, with no query parameter. Both launchers bind to `0.0.0.0` and print a LAN
URL that can be opened from a phone on the same network. Gallery upload works over local HTTP;
some mobile browsers require a secure context for direct camera recording, in which case the app
shows a message and gallery upload remains available.

The script prints both `http://127.0.0.1:8000/` and the laptop's local-network URL. Connect the
phone and laptop to the same Wi-Fi and open the printed phone URL. Native camera/file capture does
not require HTTPS. The prerecorded demonstration remains available from **Demo** if a new recording
cannot be processed during the presentation.

### Installable mobile pilot (separate from the demo)

The mobile PWA uses port `8001`, its own frontend build, SQLite authentication, and an isolated
runtime store. It reuses the existing push-up analysis pipeline but does not expose sessions from
`data/demo_sessions` or unassigned legacy directories. Generate and export a pilot invitation code:

```bash
export ULIANA_PILOT_CODE="$(openssl rand -base64 24)"
export ULIANA_TRUST_PROXY=1   # only when running behind the local ngrok process
```

```bash
tmux new-session -s uliana-mobile
./scripts/start_mobile.sh
```

Override defaults with `ULIANA_MOBILE_PORT`, `ULIANA_MOBILE_DATA_DIR`, `ULIANA_AUTH_DB`,
`ULIANA_BACKUP_DIR`, or `ULIANA_MOBILE_WEB_DIR`. The default database is
`data/mobile_pilot/mobile.sqlite3`; owned files are under `data/mobile_pilot/users/<user-id>/sessions`.
In another terminal, expose the same frontend/API origin over HTTPS:

```bash
ngrok http 8001
```

Do not put the temporary ngrok URL into the frontend or manifest. An installed PWA belongs to its
origin; after an ngrok address changes, remove and add the Home Screen app again if the old icon
opens the expired address. Some ngrok plans/configurations allow only one active agent session or
endpoint. Check `ngrok config check` and the account dashboard before starting a second tunnel; if
it is unavailable, keep the port-8000 demo tunnel running and test mobile over the LAN, or schedule
the mobile tunnel separately.

On iPhone, open the HTTPS address in Safari, tap **Share**, then **Add to Home Screen**. On Android,
use **Install app** when Chrome offers it; otherwise use the browser menu and choose **Install app**
or **Add to Home screen**. Analysis still runs on the laptop and is not available offline.

Back up the live SQLite database and JSON results without videos:

```bash
ULIANA_BACKUP_RETENTION_DAYS=14 ./scripts/backup_mobile_data.sh
```

Include videos only after the script reports and checks the required free space:

```bash
ULIANA_BACKUP_INCLUDE_VIDEO=1 ./scripts/backup_mobile_data.sh
```

To restore manually, stop the mobile server, preserve the current runtime directory, verify the
backup with `sqlite3 <backup>/mobile.sqlite3 'PRAGMA integrity_check;'`, then copy the database and
extract `session-data.tar.gz` (and the explicit video archive, if present) into a new empty runtime
directory. Point `ULIANA_MOBILE_DATA_DIR` and `ULIANA_AUTH_DB` at that directory before restarting.
The application never restores a backup automatically.

Uploaded recordings are normalized to H.264 MP4 with FFmpeg and stored under the ignored
`data/demo_sessions/` directory. Delete them from the session report or remove that directory after
the presentation.

The session report always includes a deterministic Coach Summary derived only from the saved camera
results. An optional local Ollama model can rephrase those same validated facts; any invalid output,
timeout or provider error falls back to the deterministic summary:

```bash
ULIANA_LLM_ENABLED=1
ULIANA_LLM_PROVIDER=local
ULIANA_LLM_MODEL=<configured-model>
ULIANA_LLM_TIMEOUT_SECONDS=8
```

No model is downloaded automatically, and the original video is never sent to the formatter. Leave
`ULIANA_LLM_ENABLED` unset or set it to `0` for the presentation-safe default.

### Versioned assessment and feedback policy

The presentation API attaches a deterministic `feedback_report` to completed camera sessions. Its
decision-to-language mapping is versioned separately from the frozen ML configuration in
`configs/assessment_policy.v1.json` and `configs/feedback_policy.v1.json`. Scientific references are
controlled local entries in `configs/scientific_references.v1.json`; they support measurement topics,
not the numerical engineering thresholds or algorithm validity.

| Criterion | Presentation status | Evidence source |
|---|---|---|
| Complete movement cycles | Supported | Frozen repetition intervals |
| Body alignment deviation | Supported for reliable side/oblique evidence | Shoulder–hip–ankle angle, normalized displacement and persistence |
| Push-up depth proxy | Supported for reliable side/oblique evidence | Bottom-window observable elbow angle |
| Elbow-to-torso flare | Not assessed | No released classifier |
| Head/neck alignment | Not assessed | No released classifier |
| Hand placement | Not assessed | No released classifier |
| Pressure distribution | Requires calibrated smart-mat data | Never inferred from camera-only sessions |

## Reproducible toy experiments

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
.venv/bin/python scripts/run_toy_experiments.py
.venv/bin/python scripts/generate_demo_session.py
```

The experiment uses a fixed seed and writes its tables, plots, report and replay file to
`artifacts/toy_experiments/`. Synthetic-label results validate implementation behaviour only;
they do not establish real-world effectiveness or a medical claim. Configuration thresholds
and score weights are experimental assumptions in `configs/toy_experiment.json`.

To replay generated packets, serve the repository root (`.venv/bin/python -m http.server 8000`), open
`http://localhost:8000/dist/`, click **Replay JSONL**, and choose
`artifacts/toy_experiments/sample_session.jsonl`. The ordinary live simulation remains the default.

## Integration contract

- `schemas/device-packet.schema.json`: expected packet from the physical controller
- `schemas/analysis-result.schema.json`: result consumed by the customer app

The current browser simulator can be replaced by a USB, Bluetooth, or HTTP adapter without changing the analysis-result structure.

## Stable offline contracts and dataset layout

The legacy device and dashboard schemas remain supported. New offline processing communicates through:

- `video-observation.schema.json`: one timestamped frame, pose landmarks, quality flags and a
  conservative `side`, `front`, `oblique` or `unknown` viewpoint;
- `pressure-observation.schema.json`: one timestamped cell/channel from an arbitrary pressure mat;
- `session-result.schema.json`: camera-only, pressure-only diagnostic or synchronized multimodal results;
- `metadata.schema.json`: anonymized collection metadata and hardware context.

Pressure is not restricted to two named channels. A later configuration may derive left/right palm
regions from cell coordinates or a channel-region map. Uncalibrated observations retain raw values
and use `null`—never zero—for unavailable force.

Collected data uses this participant/session layout:

```text
data/
  raw/<participant_id>/<session_id>/
    video.mp4
    pressure.csv        # optional
    metadata.json
  annotations/<participant_id>/<session_id>/
    repetitions.csv    # optional
    conditions.csv     # optional
  processed/<participant_id>/<session_id>/
  reports/<participant_id>/<session_id>/
```

`pressure.csv` columns are:

```text
timestamp_ms,timestamp_source,sensor_id,channel_id,row,column,raw_value,calibrated_force_n,calibration_status,quality_flags
```

Row, column and calibrated force may be empty. Row and column must either both be present or both
be empty. Uncalibrated, expired, invalid and unknown calibration states require an empty calibrated
force field.

Annotation definitions are:

```text
repetitions.csv: rep_id,start_ms,bottom_ms,end_ms,quality_notes
conditions.csv:  rep_id,condition,label,annotator_id,confidence,notes
```

Condition labels are `adequate`, `condition_detected`, `unavailable`, `uncertain` or `not_visible`;
not every condition is observable from every viewpoint. Uncertain and not-visible annotations are
never converted to adequate. Run validation on the complete raw tree or one session:

```bash
python scripts/validate_dataset.py data/raw
python scripts/validate_dataset.py data/raw/anon-p001/session-001
```

Errors make the command fail. Warnings identify processable sessions with unavailable or suspect
assessments, and informational messages identify absent optional data. A camera-only session omits
`pressure.csv`; a multimodal session includes it and declares pressure hardware and sampling rate.

Participant IDs must be anonymized. Consent documents must not be stored in this repository, and
all sessions, views and derivatives from one participant must remain in the same development/test
partition. Schema stability validates interfaces and provenance only; it is not scientific,
clinical or trainer validation.

## Pressure calibration and synchronization

Canonical ingestion preserves `raw_value` in the device's documented native units; raw ADC counts
or other signals are not Newtons. Optional per-channel linear calibration uses
`force_n = max(0, (raw_value - tare_raw) * newtons_per_raw_unit)`. Each calibration identifies its
sensor/channel, valid raw interval, creation and expiry times, and reference-load notes. Parameters
may differ by cell. Out-of-range values receive a warning, and existing calibrated values are
preserved unless overwrite is explicitly requested. The example calibration configuration is a
format example, not hardware evidence.

Grid coordinates enable force-weighted centre-of-pressure calculations when all contributing cells
are calibrated. Raw-signal-weighted centres are opt-in and labelled non-physical. Palm regions are
optional channel lists, such as `{"left_palm":["cell_00"],"right_palm":["cell_01"]}`. Region
imbalance is `abs(left-right)/(left+right)*100` and is available only when both regions are present,
calibrated and sufficiently covered. It is descriptive, not automatic evidence of poor technique.

Supported clock relationships are shared relative clocks, configured constant offset, one shared
synchronization event, multiple anchors with linear offset/drift estimation, and explicitly
unavailable alignment. Alignment is never inferred from coincident-looking timestamps alone.
Interpolation uses valid bracketing samples within a configured maximum gap; stream boundaries use
bounded nearest matching. Invalid, saturated and excessive-gap values remain unavailable.

```bash
python scripts/inspect_pressure_session.py data/raw/anon-p001/session-001 \
  --calibration configs/pressure_calibration.example.json
python scripts/inspect_pressure_session.py data/raw/anon-p001/session-001 --json report.json
```

Hardware integration still requires the native format, raw units/ranges, traceable per-cell loads,
grid mapping, clock/rollover behavior, sampling and drop semantics, error/saturation codes, and the
physical synchronization procedure.

## Conservative video diagnostics

The stable video pipeline emits one `VideoObservation` per decoded frame with raw and causally
smoothed normalized landmarks, visibility/presence, source-relative timestamps, image dimensions,
quality codes and viewpoint evidence. MediaPipe remains lazy-loaded and configured for one person.
Its monocular `world_landmarks`, when available, are retained as model estimates—not validated 3D
motion capture.

Viewpoints are geometric descriptions:

- `side`: narrow projected shoulder/hip width plus side visibility or depth separation;
- `front`: wide projected body width with balanced left/right visibility and depth;
- `oblique`: intermediate projected width;
- `unknown`: missing, weak or contradictory evidence.

Distances are pixel/aspect-ratio corrected and normalized by torso length. Decisions use multiple
features, aggregate valid frames, and require dwell time before changing, so filenames never supply
ground truth and frame-level labels do not flicker. For side segments, the observable anatomical
side is aggregated and fixed as left, right or ambiguous.

Landmark coordinates use a causal One Euro filter driven by actual timestamps. Visibility and
presence are not smoothed. Missing detections are not interpolated, and filter state resets after a
configured pose gap. Raw landmarks remain available for diagnostics.

| Viewpoint | Phase | Depth | Body alignment | Elbow flare | Visual symmetry |
|---|---|---|---|---|---|
| Side | supported | supported | supported | unavailable | unavailable |
| Front | limited | unavailable | unavailable | limited | supported |
| Oblique | limited | limited | limited | limited | limited |
| Unknown | limited | unavailable | unavailable | unavailable | unavailable |

“Limited” is only a capability marker; it does not authorize an assessment without a later
condition-specific reliability check.

```bash
python scripts/inspect_video_session.py data/raw/anon-p001/session-001/video.mp4 \
  --session-id session-001 --output-dir data/processed/anon-p001/session-001
```

For side recordings, place the camera approximately perpendicular to the movement plane. For front
recordings, center it on the participant's longitudinal axis. Oblique recordings should be labelled
as such rather than described as side or front. Keep the full body in frame, avoid occlusion, use a
fixed camera and stable lighting, and record the intended viewpoint manually in metadata. This is an
adaptive multi-angle prototype, not validated 360-degree analysis.

### Camera-only repetition and condition analysis

`analyze_camera_session.py` selects a phase signal independently from later condition assessments.
Candidates include left/right and bilateral elbow angles, shoulder-to-wrist distance, and
mid-shoulder motion relative to the wrists. Side views prefer the stable observable anatomical
side; front views require bilateral or relative motion; oblique and unknown views use stricter
confidence multipliers. No count is emitted when coverage, range, smoothness, timing, or confidence
gates fail.

Provisional phase settings require 70% valid frames, 35° elbow or 0.12 normalized-distance range,
normalized roughness at most 0.35, 80 ms phase dwell, and a 500–6000 ms complete cycle. Top/bottom
thresholds are 78% and 30% of the selected segment range with 8% hysteresis. State resets after a
250 ms pose gap or viewpoint change. These are experimental implementation settings, not universal
anatomical standards.

`body_alignment_deviation` combines shoulder–hip–ankle angular deviation and perpendicular hip
distance from the shoulder–ankle line. Detection requires deviation above 8° or normalized distance
above 0.08 for at least 25% of the repetition and 250 ms; a one-frame maximum cannot trigger it.
Signed displacement is retained only as neutral descriptive evidence.

`push_up_depth_proxy` uses the minimum observable elbow angle in a reliably segmented repetition.
The provisional 110° threshold is a camera proxy for measured range, not proof that the chest
touched the floor.

```bash
python scripts/analyze_camera_session.py \
  --video-observations data/processed/anon-p001/session-001/video_observations.jsonl \
  --video-summary data/processed/anon-p001/session-001/video_summary.json \
  --output-dir data/reports/anon-p001/session-001 \
  --video data/raw/anon-p001/session-001/video.mp4

python scripts/evaluate_camera_sessions.py \
  --manifest data/annotations/viewpoint_smoke_manifest.csv \
  --results-root data/reports --annotations-root data/annotations
```

Count, alignment and depth reliability are independent. Camera-only results use
`pressure_features: null` and synchronization status `not_applicable`. Evaluation reports metrics
only where manual references exist; uncertain and not-visible labels remain excluded.

## Phase 2A: offline recorded video

MediaPipe's supported wheels do not target this machine's default Python 3.14. Keep the Phase 1
environment and create a separate Python 3.11 environment:

```bash
PYENV_VERSION=3.11.15 python -m venv .venv-video
.venv-video/bin/pip install -e '.[dev,video]'
curl -L -o models/pose_landmarker_full.task \
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task
sha256sum models/pose_landmarker_full.task
```

The checksum of the actual model used is also written to `provenance.json`. Copy a consented
side-view recording to `data/raw/pushups/`, add its provenance to
`data/annotations/videos.csv`, and run:

```bash
.venv-video/bin/python scripts/analyze_video.py \
  --video data/raw/pushups/p001_side_01.mp4 \
  --model models/pose_landmarker_full.task \
  --output artifacts/real_video/p001_side_01

.venv-video/bin/python scripts/evaluate_real_videos.py \
  --manifest data/annotations/videos.csv \
  --annotations data/annotations/repetitions.csv
```

The analyzer caches `landmarks.jsonl`, records per-frame geometry/reliability in `frames.jsonl`,
writes repetition boundaries and a summary, and produces `annotated.mp4`. MediaPipe is used in
VIDEO mode with source-derived increasing timestamps. The anatomical side is chosen once from
the calibration frames and is not switched frame-to-frame. Angles are image-plane estimates with
aspect-ratio correction; monocular world coordinates are not treated as motion-capture data.

Camera-only analysis does not invent hand forces. Because schema version 1.0 requires numeric
force and balance fields, it cannot truthfully represent camera-only partial results. Consequently,
the default run emits diagnostics but no dashboard replay. `--simulated-force` optionally writes
`replay.jsonl` for integration demonstrations; its session ID and dashboard status explicitly say
that force is simulated, and it must not be used as real force/fusion validation.

Missing/low-quality pose frames make assessment unavailable. A gap longer than the configured
limit resets an incomplete state-machine cycle, so missing motion cannot complete a repetition or
retain stale advice. Overlay MP4 is constant-frame-rate at the decoder-reported average FPS;
exact source/VFR timestamps remain in JSONL, and the sidecar records this conversion limitation.

## Prototype assumptions

The scoring weights and 10% asymmetry limit are experimental settings. They require calibration and trainer validation. This prototype is not a medical device and does not estimate injury risk.

## Milestone 5: unified recorded-session analysis

The unified command accepts a consented session directory containing `metadata.json`, optional
`video.mp4`, optional canonical `pressure.csv`, and optional `annotations.json`. It keeps camera
and pressure availability independent and only assigns pressure evidence to a repetition when an
explicit clock relationship is configured in metadata.

```bash
python scripts/analyze_session.py data/raw/<participant>/<session> \
  --output-dir data/reports/<participant>/<session> \
  --video-config configs/video_processing.json \
  --pressure-config configs/pressure_quality.json \
  --calibration configs/pressure_calibration.json
```

Use `--cached-video-observations` with `--cached-video-summary`, or
`--cached-pressure-observations`, for deterministic replay. Supply `--cache-manifest` to require
input, configuration, and model hashes to match; a mismatch is rejected unless `--force` is
explicit. `--json-only` suppresses video rendering. The report directory contains the stable
observations, synchronized timeline, session result, replay packets, provenance, and—when a real
source video is available—`annotated.mp4`.

Pressure balance is a descriptive comparison of configured palm regions. Physical force and
impulse are emitted only for calibrated samples. Centre-of-pressure stability remains unavailable
until a complete calibrated grid and a trainer-derived threshold exist. Sensor quality is
diagnostic and is never turned into a technique cue. The three neutral cue candidates are selected
by reliability, persistence, configured priority, repetition history, and cooldown, with no more
than one cue selected at a time.

```bash
python scripts/evaluate_sessions.py data/reports \
  --annotations data/annotations/repetitions.csv \
  --output data/reports/evaluation.json
```

Without matching manual labels, evaluation is explicitly marked
`prototype_smoke_test_not_model_validation`. Complementary camera and pressure measurements are
not evidence that fusion improves accuracy.

### Optional Kokoro audio cue for mobile review

The mobile review uses a private, CSRF-protected `POST /api/tts/synthesize` endpoint. It synthesizes WAV with Kokoro-82M (`KPipeline(lang_code='a')`, voice `af_heart`), then plays it after the user enables **Audio cue during review**. The first synthesis may download model files into `.kokoro-cache/` and take longer; later requests reuse a persistent worker. The mobile UI caches generated clips by cue text. Requests are limited to 500 characters and are not saved in SQLite. The endpoint is available only in `ULIANA_MODE=mobile`; an optional `session_id` must belong to the signed-in user.

The TTS worker uses a separate Python 3.11 virtual environment, while the existing mobile backend and CV environment remain unchanged. On Linux, install the CPU-only PyTorch wheel first to avoid CUDA downloads:

```sh
PYENV_VERSION=3.11.15 python -m venv .venv-tts
.venv-tts/bin/python -m pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu
.venv-tts/bin/python -m pip install -e '.[tts]'
.venv-tts/bin/python -m spacy download en_core_web_sm
ULIANA_PILOT_CODE='your-private-invite' scripts/start_mobile.sh
```

If your Python 3.11 installation is not managed by pyenv, use its full executable path for the first command. The backend starts without the optional TTS environment, but the audio control reports **Audio unavailable** until it is installed. An HTTPS tunnel for phone access can be started separately with `ngrok http 8001`. Port 8000 is unaffected.

The red review marker uses saved per-frame landmarks and the original frozen alignment assessment. It is shown only when a trustworthy frame from the same anatomical side supports the flag. If no such frame exists, the UI says the review frame is unavailable. No new CV thresholds or predictions are introduced.
