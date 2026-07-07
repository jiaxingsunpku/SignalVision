# Output Data Snapshot

This repository keeps generated training output out of git by default.

The only committed output artifact is the minimal Ezhou traffic-signal control checkpoint needed for integration smoke tests:

- Checkpoint: `runtime/data/output_data/tsc/sumo_colight_pytorch_agent/ezhou/test/model/200_0.pt`
- Model config: `runtime/configs/tsc/colight_pytorch_agent.yml`
- Simulation config: `runtime/configs/sim/ezhou.cfg`
- Road network: `runtime/data/raw_data/ezhou/ezhou.net.xml`
- Traffic flow: `runtime/data/raw_data/ezhou/ezhou.rou.xml`

Full training logs, datasets, replay files, and intermediate checkpoints are intentionally omitted.
