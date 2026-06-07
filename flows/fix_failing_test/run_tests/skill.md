---
name: run_tests
description: Run the test suite and report whether it passes.
tools: [run_command, read_file]
---
SKILL_ID: runtests

Run `python -B -m pytest -q` in the workspace (the `-B` avoids stale bytecode
between edits). If every test passes, end your reply with `ACTION: pass`.
Otherwise summarize the failure and end with `ACTION: fail`.
