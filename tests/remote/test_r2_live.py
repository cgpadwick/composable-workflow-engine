"""Live R2 roundtrip — needs real keys in ~/.saage/credentials.toml [storage]
(or SAAGE_STORAGE_* env overrides). Run with:

    SAAGE_R2_TESTS=1 pytest tests/remote/test_r2_live.py -v

Touches only keys under tests/saage-selftest/ in the bucket and cleans up.
"""
from __future__ import annotations

import os

import pytest

from saage.remote.creds import storage_config
from saage.remote.observe import _bucket_client, _fetch_from_bucket
from saage.remote.r2push import plan_uploads

pytestmark = pytest.mark.skipif(
    not os.environ.get("SAAGE_R2_TESTS"),
    reason="live R2 test; set SAAGE_R2_TESTS=1 with [storage] configured",
)


@pytest.fixture
def storage():
    s = storage_config()      # real ~/.saage creds on purpose — this is a live test
    if s is None:
        pytest.skip("no [storage] configured in credentials.toml")
    return s


def test_roundtrip_upload_download_delete(storage, tmp_path):
    client = _bucket_client(storage)
    run_id = "saage-selftest"
    prefix = storage.run_prefix(run_id)

    run_dir = tmp_path / "run"
    (run_dir / "artifacts").mkdir(parents=True)
    (run_dir / "artifacts" / "experiments.jsonl").write_text('{"step": 1}\n')
    (run_dir / "status.json").write_text('{"phase":"done","rc":0,"updated":"x"}')

    pairs = plan_uploads(run_dir, prefix)
    assert len(pairs) == 2
    for local, key in pairs:
        client.upload_file(str(local), storage.bucket, key)
    try:
        dest = tmp_path / "fetched"
        dest.mkdir()
        got = _fetch_from_bucket(storage, run_id, dest)
        assert sorted(got) == ["experiments.jsonl", "status.json"]
        assert (dest / "experiments.jsonl").read_text() == '{"step": 1}\n'
    finally:
        for _, key in pairs:
            client.delete_object(Bucket=storage.bucket, Key=key)
