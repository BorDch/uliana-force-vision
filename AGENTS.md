# ULIANA repository instructions

## Frozen product goal

Build and validate one vertical slice:

> One push-up, two force channels, one camera, one quality score, and one reliable corrective cue.

Do not broaden the MVP to other exercises, rehabilitation, injury prediction, a native mobile app, a smart mat, or custom model training unless the user explicitly changes the frozen goal.

## Technical principles

- Preserve the working browser simulator while integrating real inputs.
- Keep device input, analysis logic, and UI output separated by typed JSON contracts.
- Use pretrained pose estimation before considering custom training.
- Prefer interpretable metrics and rules for the first prototype.
- Treat thresholds and score weights as experimental configuration.
- Abstain from feedback when pose or sensor confidence is insufficient.
- Never present the prototype as a medical device or injury-risk estimator.
- Store synchronized raw observations so later modeling remains possible.
- Use deterministic synthetic data and participant-wise evaluation for later ML experiments.

## Required verification

Before reporting completion:

- Validate JavaScript and JSON syntax.
- Exercise normal, asymmetric, low-confidence, and sensor-error states.
- Confirm the dashboard remains responsive.
- Report exactly what was tested and any assumptions that remain unvalidated.
