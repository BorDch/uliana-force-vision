# Raw sensor simulator

Start the mobile backend on port 8001. Sign in to the PWA, open Experimental sensor, create a pairing token for `esp32-demo-01`, then run:

```sh
python sensor_simulator/run.py --token 'TOKEN' --device-id esp32-demo-01 --count 10 --interval 1
```

`--drop-sequence 3` skips sequence 3; the next accepted response reports `missing_sequences: 1`. `--malformed` sends invalid JSON. `--session-id UUID` links samples to an owned workout. All output is labelled `SIMULATED`; values are deterministic raw ADC-like numbers, not calibrated quantities.
