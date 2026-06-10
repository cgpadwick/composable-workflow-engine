"""Observe and manage handed-off runs: status / logs / ps / kill / fetch.

Local state records *intent*; the node records *truth* (status.json heartbeat,
tmux session liveness). Status reads both and reconciles — when the node says
the run finished, the local phase is updated to match.
"""
from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .creds import get_target, list_targets
from .state import RunState, find_run, list_runs
from .target import SshTarget

log = logging.getLogger("saage.remote")

# node phases that mean "the run is over"
_FINAL = {"done", "failed", "timeout", "killed"}


def _node_for(rs: RunState) -> SshTarget:
    return SshTarget(get_target(rs.state()["target"]))


def _age(iso: str) -> str:
    try:
        then = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return "?"
    secs = int((datetime.now(timezone.utc) - then).total_seconds())
    if secs < 120:
        return f"{secs}s"
    if secs < 7200:
        return f"{secs // 60}m"
    return f"{secs / 3600:.1f}h"


def refresh(rs: RunState) -> tuple[dict, dict]:
    """Pull node truth and fold final phases back into local state."""
    state = rs.state()
    node = _node_for(rs)
    node_status = node.read_status(rs.run_id)
    node_phase = node_status.get("phase")
    if node_phase in _FINAL and state.get("phase") not in _FINAL:
        state = rs.update(phase=node_phase)
        rs.event("phase_from_node", phase=node_phase)
    return state, node_status


def status(run_ref: str | None) -> int:
    rs = find_run(run_ref)
    state, node_status = refresh(rs)
    node = _node_for(rs)
    alive = node.session_alive(rs.run_id)
    heartbeat = node_status.get("updated")

    info = state.get("node", {})
    cost = ""
    if info.get("hourly_usd"):
        started = state.get("started_at", "")
        try:
            t0 = datetime.strptime(started, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            hours = (datetime.now(timezone.utc) - t0).total_seconds() / 3600
            cost = f"   ~${hours * info['hourly_usd']:.2f} so far — remember: terminating the box is on you"
        except ValueError:
            pass

    print(f"run        {rs.run_id}")
    print(f"target     {state.get('target')} ({info.get('host')})")
    print(f"phase      {state.get('phase')}"
          + (f"   (node: {node_status.get('phase')}, heartbeat {_age(heartbeat)} ago)"
             if heartbeat else "   (no status.json from node yet)"))
    print(f"session    {'alive' if alive else 'gone'}")
    print(f"started    {state.get('started_at', '?')}{cost}")
    if heartbeat and node_status.get("phase") == "running" and not alive:
        print("⚠  node status says running but the tmux session is gone — "
              "the run likely died; check `saage remote logs`")
    exp = node.conn.run(
        f"wc -l < $HOME/{node.run_dir(rs.run_id)}/artifacts/experiments.jsonl",
        check=False)
    if exp.returncode == 0 and exp.stdout.strip().isdigit():
        print(f"ledger     {exp.stdout.strip()} experiment record(s)")
    tail = node.tail_log(rs.run_id, lines=5)
    if tail.strip():
        print("log tail:")
        for line in tail.rstrip().splitlines():
            print(f"  {line}")
    return 0


def logs(run_ref: str | None, *, lines: int = 100, live: bool = False) -> int:
    rs = find_run(run_ref)
    node = _node_for(rs)
    path = f"$HOME/{node.run_dir(rs.run_id)}/saage.log"
    if live:
        conn = node.conn
        argv = ["ssh", *conn._opts(), conn.dest, f"tail -n {int(lines)} -f {path}"]
        return subprocess.call(argv)        # stream straight to the terminal
    out = node.conn.run(f"tail -n {int(lines)} {path}", check=False)
    print(out.stdout, end="")
    return 0 if out.returncode == 0 else 1


def reconcile(local_runs: list[dict], sessions_by_target: dict[str, list[str]]) -> list[dict]:
    """Pure intent-vs-truth diff (unit-testable). Local runs are state dicts;
    sessions are tmux session names per target. Returns display rows."""
    rows = []
    claimed: set[tuple[str, str]] = set()
    for state in local_runs:
        target = state.get("target", "?")
        session = state.get("tmux_session", "")
        alive = session in sessions_by_target.get(target, [])
        claimed.add((target, session))
        phase = state.get("phase", "?")
        note = ""
        if phase == "running" and not alive:
            note = "⚠ no session on node — run died or box rebooted"
        if phase in _FINAL and alive:
            note = "⚠ session still alive but run is final — investigate"
        rows.append({"run_id": state.get("run_id", "?"), "phase": phase,
                     "target": target, "alive": alive, "note": note})
    for target, sessions in sessions_by_target.items():
        for session in sessions:
            if (target, session) not in claimed:
                rows.append({"run_id": "(unknown)", "phase": "-", "target": target,
                             "alive": True,
                             "note": f"⚠ ORPHAN session {session} — not in local state"})
    return rows


def ps() -> int:
    sessions_by_target: dict[str, list[str]] = {}
    for name, target in list_targets().items():
        node = SshTarget(target)
        try:
            sessions_by_target[name] = node.sessions()
        except Exception as exc:                      # unreachable box: report, keep going
            log.warning("target %s unreachable: %s", name, exc)
            sessions_by_target[name] = []
    local = []
    for rs in list_runs():
        try:
            state, _ = refresh(rs)
        except Exception:
            state = rs.state()
        local.append(state)
    rows = reconcile(local, sessions_by_target)
    if not rows:
        print("no runs, no sessions.")
        return 0
    fmt = "{:<34} {:<10} {:<10} {:<7} {}"
    print(fmt.format("RUN", "PHASE", "TARGET", "ALIVE", "NOTE"))
    for r in rows:
        print(fmt.format(r["run_id"], r["phase"], r["target"],
                         "yes" if r["alive"] else "no", r["note"]))
    return 0


def kill(run_ref: str) -> int:
    rs = find_run(run_ref)
    node = _node_for(rs)
    node.stop(rs.run_id)
    rs.update(phase="killed")
    rs.event("killed")
    print(f"run {rs.run_id} stopped (the box is untouched — only the run was killed)")
    return 0


def fetch(run_ref: str | None, dest: str | None = None) -> int:
    rs = find_run(run_ref)
    node = _node_for(rs)
    out = Path(dest) if dest else Path.cwd() / "results" / rs.run_id
    out.mkdir(parents=True, exist_ok=True)
    rdir = node.run_dir(rs.run_id)
    node.conn.rsync_from(f"{rdir}/artifacts/", out)
    for f in ("saage.log", "status.json"):
        try:
            node.conn.rsync_from(f"{rdir}/{f}", out)
        except Exception:
            pass
    rs.event("fetched", dest=str(out))
    got = sorted(p.name for p in out.iterdir())
    print(f"fetched {len(got)} file(s) → {out}")
    for name in got:
        print(f"  {name}")
    return 0
