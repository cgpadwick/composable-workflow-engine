import json

import pytest

from saage.remote.state import RunState, find_run, list_runs


def test_update_is_a_merge_and_atomic(saage_home):
    rs = RunState.create("run-1")
    rs.update(phase="pushing", target="spark")
    rs.update(phase="running")
    state = rs.state()
    assert state["phase"] == "running"
    assert state["target"] == "spark"          # earlier field survived the merge
    assert state["run_id"] == "run-1"
    assert "updated_at" in state
    assert not (rs.dir / "state.json.tmp").exists()


def test_events_append_only(saage_home):
    rs = RunState.create("run-1")
    rs.event("a", x=1)
    rs.event("b")
    events = rs.events()
    assert [e["event"] for e in events] == ["a", "b"]
    assert events[0]["x"] == 1
    assert all("ts" in e for e in events)


def test_manifest_roundtrip(saage_home):
    rs = RunState.create("run-1")
    rs.write_manifest({"flow": "f.yaml", "secrets_pushed": ["KEY_NAME"]})
    assert rs.manifest()["flow"] == "f.yaml"


def test_find_run_by_prefix_and_latest(saage_home):
    a = RunState.create("greenfield-20260609-aaaa")
    a.update(phase="done", started_at="2026-06-09T01:00:00Z")
    b = RunState.create("greenfield-20260610-bbbb")
    b.update(phase="running", started_at="2026-06-10T01:00:00Z")

    assert find_run("greenfield-20260609").run_id == a.run_id
    assert find_run(None).run_id == b.run_id            # latest by started_at
    with pytest.raises(FileNotFoundError, match="ambiguous"):
        find_run("greenfield-2026")
    with pytest.raises(FileNotFoundError, match="no run matching"):
        find_run("zzz")


def test_list_runs_skips_dirs_without_state(saage_home):
    RunState.create("empty-no-state")                   # dir exists, no state.json
    rs = RunState.create("real")
    rs.update(phase="running")
    assert [r.run_id for r in list_runs()] == ["real"]
