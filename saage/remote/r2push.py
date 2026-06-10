"""Node-side artifact mirror: push the run dir's artifacts to R2/S3.

Invoked by the sidecar in start.sh (and once more by stop.sh) as

    venv/bin/python -m saage.remote.r2push

inside the run dir, with connection details in the environment (sourced from
the per-run run_env):

    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
    SAAGE_R2_ENDPOINT   https://<account>.r2.cloudflarestorage.com
    SAAGE_R2_BUCKET     saage-data
    SAAGE_R2_PREFIX     runs/<run_id>

Uploads artifacts/* plus status.json and saage.log. Files are small (ledgers,
reports, logs — checkpoints stay on the node in v1), so it re-uploads
unconditionally rather than tracking mtimes. Failures must never break the
run: callers invoke it with `|| true` and it exits 0 unless misconfigured.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def plan_uploads(run_dir: Path, prefix: str) -> list[tuple[Path, str]]:
    """(local file, bucket key) pairs for everything worth mirroring."""
    pairs: list[tuple[Path, str]] = []
    artifacts = run_dir / "artifacts"
    if artifacts.is_dir():
        for p in sorted(artifacts.iterdir()):
            if p.is_file():
                pairs.append((p, f"{prefix}/artifacts/{p.name}"))
    for name in ("status.json", "saage.log"):
        p = run_dir / name
        if p.is_file():
            pairs.append((p, f"{prefix}/{name}"))
    return pairs


def main() -> int:
    endpoint = os.environ.get("SAAGE_R2_ENDPOINT")
    bucket = os.environ.get("SAAGE_R2_BUCKET")
    prefix = os.environ.get("SAAGE_R2_PREFIX")
    if not (endpoint and bucket and prefix):
        print("r2push: SAAGE_R2_* not configured", file=sys.stderr)
        return 1
    try:
        import boto3
    except ModuleNotFoundError:
        print("r2push: boto3 not installed in this venv", file=sys.stderr)
        return 1

    client = boto3.client("s3", endpoint_url=endpoint, region_name="auto")
    pairs = plan_uploads(Path.cwd(), prefix)
    for local, key in pairs:
        client.upload_file(str(local), bucket, key)
    print(f"r2push: {len(pairs)} file(s) -> s3://{bucket}/{prefix}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
