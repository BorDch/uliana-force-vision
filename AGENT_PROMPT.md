# Prompt for the coding agent

You are working in the ULIANA prototype repository. Start by reading `README.md`, `AGENTS.md`, both JSON schemas in `schemas/`, and the current static dashboard in `dist/`.

## Objective

Develop a demonstrable, reliable vertical slice for the Skoltech Innovation Workshop:

> One participant performs push-ups using two force-sensing handles and one camera. The system synchronizes both streams, recognizes repetitions, calculates balance, depth and body alignment, and provides one understandable real-time correction only when the measurements are reliable.

The existing browser dashboard is the toy simulation and must remain usable throughout development.

## Frozen scope

Implement only:

1. Left and right force input.
2. Pretrained pose landmarks from a camera or recorded video.
3. Timestamp synchronization.
4. Push-up phase and repetition detection.
5. Per-repetition metrics and an interpretable quality score.
6. Confidence-aware feedback and abstention.
7. Session logging and delivery of results to the existing dashboard.

Do not add other exercises, rehabilitation functionality, injury prediction, native mobile applications, authentication, cloud infrastructure, custom neural-network training, Apple Watch support, EMG sensors, or a pressure-sensitive mat.

## Expected architecture

Create a small Python package with independently replaceable components:

- `uliana/sources/simulator.py`: deterministic synthetic force and pose source.
- `uliana/sources/serial_force.py`: parser for newline-delimited controller packets matching `schemas/device-packet.schema.json`.
- `uliana/sources/pose.py`: adapter for MediaPipe or MoveNet landmarks.
- `uliana/fusion.py`: timestamp alignment and synchronized samples.
- `uliana/metrics.py`: force asymmetry, elbow angle, body-line error and phase metrics.
- `uliana/state_machine.py`: push-up phase and repetition detection with hysteresis.
- `uliana/scoring.py`: configurable, interpretable scoring and feedback priority.
- `uliana/reliability.py`: pose-confidence, sensor-range, missing-data and drift checks.
- `uliana/session.py`: raw-sample and per-repetition logging.
- `uliana/api.py`: a minimal local HTTP or WebSocket bridge that sends analysis results to the dashboard.
- `tests/`: focused tests for scoring, phase transitions, packet parsing and abstention.

Preserve the schemas as the boundary between the controller, analytics and customer interface. If a schema must change, update the schema, examples, dashboard and tests together.

## Initial definitions

Use these only as configurable prototype assumptions:

```text
asymmetry_percent = abs(left_force - right_force) / (left_force + right_force) * 100
quality = 0.4 * balance_score + 0.3 * depth_score + 0.3 * alignment_score
```

Feedback priority:

1. If sensor input is missing, outside its valid range or unstable: abstain and request calibration.
2. If pose confidence is insufficient: abstain and request camera repositioning.
3. If persistent force asymmetry exceeds the configured experimental limit: request a left/right shift.
4. If body-line error exceeds its configured limit: request body alignment.
5. Otherwise confirm a good repetition.

Never react to one noisy sample. Apply smoothing and require a deviation to persist for a configurable time window. Keep raw and filtered values available for debugging.

## Simulation requirements

Before using hardware, create deterministic scenarios with a fixed random seed:

- Balanced repetitions.
- Persistent left overload.
- Persistent right overload.
- Poor body alignment.
- Low pose confidence.
- Missing and delayed force samples.
- Sensor saturation or implausible values.

The simulation must produce the same output contract as the real pipeline. Add a simple switch between simulated and real input without changing downstream analysis code.

## Acceptance criteria

The prototype is complete only when:

- The existing dashboard still runs and shows live synthetic data.
- A complete `UP → DOWN → UP` movement creates exactly one repetition.
- Left/right asymmetry is calculated safely, including a near-zero total-force case.
- Low-confidence camera input results in abstention rather than technique advice.
- Missing or invalid sensor data results in an explicit non-ready state.
- At least one replayable session is logged with synchronized raw samples and repetition summaries.
- The dashboard consumes analysis results conforming to `schemas/analysis-result.schema.json`.
- Tests cover the principal normal and failure scenarios.
- Setup and run instructions are reproducible on another laptop.

Engineering targets such as force error below 5%, feedback latency below 500 ms and a 10% asymmetry limit are hypotheses, not validated scientific facts. Keep them configurable and label them accordingly.

## Working method

Implement the smallest end-to-end slice first: simulator → analysis → result packet → dashboard. Then replace one simulated source at a time. Do not rewrite the dashboard unnecessarily or expand the product scope.

After each meaningful phase:

1. Run the relevant checks.
2. Keep the application runnable.
3. Record assumptions and unresolved risks.

At the end, provide:

- A concise summary of implemented behavior.
- The files created or changed.
- Exact commands to run the simulator and dashboard.
- Test results.
- Remaining blockers for real sensor and camera integration.
