"""Simulate a scheduler status query (like squeue). Reports RUNNING until the
counter seeded by submit.py is exhausted, then COMPLETE."""
import sys

job_id = sys.argv[1]
path = f"job_{job_id}.count"

try:
    remaining = int(open(path).read().strip())
except FileNotFoundError:
    remaining = 0

if remaining > 0:
    open(path, "w").write(str(remaining - 1))
    print("RUNNING")
else:
    print("COMPLETE")
