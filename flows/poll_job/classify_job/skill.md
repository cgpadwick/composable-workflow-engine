---
name: classify_job
description: |
  Latest scheduler output:
  {{ results['poll']['stdout'] }}

  Decide the job state from the scheduler output above.
tools: []
---
SKILL_ID: classify

You monitor a batch job. Given the scheduler output, decide the state and end
your reply with exactly one of: `ACTION: running`, `ACTION: complete`, or
`ACTION: failed`.
