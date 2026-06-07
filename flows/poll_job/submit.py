"""Simulate submitting a batch job. Prints a job id (captured by the flow) and
seeds a counter file controlling how many polls report RUNNING before COMPLETE."""
JOB_ID = 4242
RUNNING_POLLS = 2

with open(f"job_{JOB_ID}.count", "w") as f:
    f.write(str(RUNNING_POLLS))

print(f"submitted job {JOB_ID}")
