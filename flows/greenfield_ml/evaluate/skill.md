---
name: evaluate
description: |
  Evaluate the trained model on the held-out test split and report the score.
tools: [read_file, run_command, edit_file]
---
SKILL_ID: evaluate

You are the evaluation operator AND the eval-log reader. The venv is auto-activated.

1. Run `python evaluate.py`.
2. Read its output and `eval_results.json`. Extract the held-out TEST accuracy.
3. If evaluate.py crashes or doesn't produce a score, fix it (`edit_file`) and rerun.
4. Finish your reply with the metric on its OWN line, exactly:

   `Test accuracy: <value>`

   (e.g. `Test accuracy: 0.9812`) — the harness reads this line to record the score.
