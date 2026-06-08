---
name: train
description: |
  Run training to completion and confirm it produced a checkpoint. Task: {{ task }}
tools: [read_file, run_command, edit_file, write_file]
---
SKILL_ID: train

You are the training operator AND the training-log analyzer. The venv is
auto-activated for commands.

1. Run `python train.py` (use the script's defaults; keep epochs small/fast).
2. Read the command output and `logs/training.log`. Decide whether training
   SUCCEEDED: it completed without a crash, loss/accuracy are not NaN, validation
   accuracy improved, and `checkpoints/best.pt` now exists.
3. If it FAILED (traceback, NaN, OOM, no checkpoint), diagnose from the log, fix the
   code (`edit_file`), and rerun — up to a few attempts.
4. When training has succeeded and `checkpoints/best.pt` exists, finish with a
   one-line summary including the best validation accuracy you saw.
