# Ezhou CoLight Checkpoint

This folder contains one trained CoLight PyTorch checkpoint for the Ezhou SUMO scenario.

- Scenario: `ezhou`
- Checkpoint: `test/model/200_0.pt`
- Road network: `runtime/data/raw_data/ezhou/ezhou.net.xml`
- Traffic flow: `runtime/data/raw_data/ezhou/ezhou.rou.xml`
- SUMO config: `runtime/data/raw_data/ezhou/ezhou.sumocfg`
- Simulation config: `runtime/configs/sim/ezhou.cfg`
- Agent config: `runtime/configs/tsc/colight_pytorch_agent.yml`

Only this final checkpoint is committed. Intermediate checkpoints and training outputs should stay local.
