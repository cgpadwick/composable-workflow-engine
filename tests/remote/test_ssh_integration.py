"""Integration tests: real handoffs to localhost over real ssh.

Gated: they need a local sshd plus the saage key authorized for the current
user (what `saage remote init` + add-target set up). Run with:

    SAAGE_SSH_TESTS=1 pytest tests/remote/test_ssh_integration.py -v

They use command-only flows (provider: local) — no LLM key, no API cost.
"""
from __future__ import annotations

import getpass
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from saage.cli import main as saage_main
from saage.remote.creds import cred_path, get_target
from saage.remote.handoff import handoff
from saage.remote.target import SshTarget

from .conftest import git

pytestmark = pytest.mark.skipif(
    not os.environ.get("SAAGE_SSH_TESTS"),
    reason="needs local sshd + authorized saage key; set SAAGE_SSH_TESTS=1",
)

REAL_KEY = Path("~/.saage/ssh/saage_ed25519").expanduser()


@pytest.fixture
def localbox(saage_home):
    """Register a 'localbox' target pointing at localhost with the real key."""
    if not REAL_KEY.exists():
        pytest.skip(f"no saage ssh key at {REAL_KEY} (run `saage remote init`)")
    cred_path().write_text(
        f'[targets.localbox]\nhost = "localhost"\nuser = "{getpass.getuser()}"\n'
        f'key = "{REAL_KEY}"\n'
    )
    cred_path().chmod(0o600)
    target = get_target("localbox")
    cleanup: list[str] = []
    yield target, cleanup
    node = SshTarget(target)
    for run_id in cleanup:
        node.conn.run(f"tmux kill-session -t saage-{run_id} 2>/dev/null", check=False)
        node.conn.run(f"rm -rf $HOME/.saage_runs/{run_id}", check=False)


def _flow(tmp_path: Path, name: str, body: str) -> Path:
    d = tmp_path / name
    d.mkdir()
    (d / "flow.yaml").write_text(body)
    return d / "flow.yaml"


def _wait_phase(node: SshTarget, run_id: str, want: set[str], timeout: int = 300) -> dict:
    deadline = time.monotonic() + timeout
    status: dict = {}
    while time.monotonic() < deadline:
        status = node.read_status(run_id)
        if status.get("phase") in want:
            return status
        time.sleep(3)
    raise AssertionError(f"run {run_id} never reached {want}; last status: {status}")


def test_full_handoff_lifecycle(localbox, tmp_path, capsys):
    """handoff -> done -> status/ps/fetch, all against a real node (localhost)."""
    target, cleanup = localbox
    flow = _flow(tmp_path, "tiny", """\
provider: { type: local, model: none }
shared: { msg: hello-from-handoff }
workflow:
  - id: write
    type: command
    run: 'echo "{{ msg }}" > out.txt'
  - id: ledger
    type: command
    run: 'echo "{\\"step\\": 1, \\"kept\\": true}" > experiments.jsonl && echo FLOWDONE'
""")
    rs = handoff(flow=str(flow), target=target, sync_interval=5)
    cleanup.append(rs.run_id)
    node = SshTarget(target)

    status = _wait_phase(node, rs.run_id, {"done", "failed"}, timeout=300)
    log = node.tail_log(rs.run_id, lines=50)
    assert status["phase"] == "done", f"run failed; node log:\n{log}"

    # the flow really ran in the node-side workspace
    out = node.conn.capture(f"cat $HOME/.saage_runs/{rs.run_id}/ws/out.txt")
    assert out.strip() == "hello-from-handoff"
    # the sidecar collected the ledger into artifacts/ (the "bucket" dir)
    ledger = node.conn.capture(
        f"cat $HOME/.saage_runs/{rs.run_id}/artifacts/experiments.jsonl")
    assert json.loads(ledger)["kept"] is True
    # secrets were deleted when the run finished
    assert not node.conn.ok(f"test -f $HOME/.saage_runs/{rs.run_id}/run_env")

    # status reconciles the final phase back into local state
    assert saage_main(["remote", "status", rs.run_id]) == 0
    assert rs.state()["phase"] == "done"
    text = capsys.readouterr().out
    assert "done" in text

    # ps shows the finished run without complaints
    assert saage_main(["remote", "ps"]) == 0
    ps_out = capsys.readouterr().out
    assert rs.run_id in ps_out
    assert "ORPHAN" not in ps_out

    # fetch pulls artifacts + log back
    dest = tmp_path / "results"
    assert saage_main(["remote", "fetch", rs.run_id, "--dest", str(dest)]) == 0
    assert (dest / "experiments.jsonl").exists()
    assert (dest / "saage.log").exists()


def test_kill_stops_run_and_cleans_secrets(localbox, tmp_path):
    target, cleanup = localbox
    flow = _flow(tmp_path, "sleeper", """\
provider: { type: local, model: none }
workflow:
  - { id: nap, type: command, run: "sleep 600" }
""")
    rs = handoff(flow=str(flow), target=target, sync_interval=5)
    cleanup.append(rs.run_id)
    node = SshTarget(target)
    _wait_phase(node, rs.run_id, {"running"}, timeout=120)

    assert saage_main(["remote", "kill", rs.run_id]) == 0
    assert rs.state()["phase"] == "killed"
    assert node.read_status(rs.run_id).get("phase") == "killed"
    assert not node.session_alive(rs.run_id)
    assert not node.conn.ok(f"test -f $HOME/.saage_runs/{rs.run_id}/run_env")


def test_busy_target_refuses_second_handoff(localbox, tmp_path):
    target, cleanup = localbox
    flow = _flow(tmp_path, "sleeper2", """\
provider: { type: local, model: none }
workflow:
  - { id: nap, type: command, run: "sleep 600" }
""")
    rs = handoff(flow=str(flow), target=target, sync_interval=5)
    cleanup.append(rs.run_id)
    node = SshTarget(target)
    _wait_phase(node, rs.run_id, {"running"}, timeout=120)

    from saage.remote.target import PreflightError
    with pytest.raises(PreflightError, match="already has a saage run"):
        handoff(flow=str(flow), target=target)
    saage_main(["remote", "kill", rs.run_id])


def test_brownfield_workspace_roundtrip(localbox, tmp_path):
    """Packaged workspace: clone run branch on node, flow commits, push-back."""
    target, cleanup = localbox

    ws = tmp_path / "brown_ws"
    ws.mkdir()
    git(ws, "init", "-q", "-b", "main")
    (ws / "config.yaml").write_text("epochs: 8\n")
    git(ws, "add", "-A")
    git(ws, "commit", "-q", "-m", "initial")
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(ws, "remote", "add", "origin", str(bare))

    flow = _flow(tmp_path, "brown", f"""\
provider: {{ type: local, model: none }}
workspace: {ws}
workflow:
  - id: tune
    type: command
    run: 'echo "lr: 0.001" >> config.yaml && git -c user.email=s@l -c user.name=s commit -qam "saage: experiment 1"'
  - id: ledger
    type: command
    run: 'echo "{{\\"exp\\": 1}}" > experiments.jsonl'
""")
    rs = handoff(flow=str(flow), target=target, sync_interval=5)
    cleanup.append(rs.run_id)
    node = SshTarget(target)

    status = _wait_phase(node, rs.run_id, {"done", "failed"}, timeout=300)
    assert status["phase"] == "done", node.tail_log(rs.run_id, lines=50)

    run_branch = rs.manifest()["workspace"]["run_branch"]
    # the node cloned the run branch, the flow committed, start.sh pushed back:
    # the experiment commit must now be on the run branch in origin
    log_out = subprocess.run(
        ["git", "-C", str(bare), "log", "--oneline", run_branch],
        capture_output=True, text=True, check=True).stdout
    assert "saage: experiment 1" in log_out
    # the user's local checkout never moved
    assert (ws / "config.yaml").read_text() == "epochs: 8\n"
