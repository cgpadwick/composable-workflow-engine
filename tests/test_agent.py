from cwe_testkit import call, resp

from cwe.agent import run_agent
from cwe.llm import LLMResponse, ScriptedProvider
from cwe.tools import file_tools


def test_loop_executes_tool_then_finishes(tmp_path):
    tools = file_tools(tmp_path)
    provider = ScriptedProvider([
        resp(calls=[call("write_file", path="out.txt", content="hi")]),
        resp("all done"),
    ])
    result = run_agent(provider, "sys", "write a file", tools)
    assert result == "all done"
    assert (tmp_path / "out.txt").read_text() == "hi"


def test_unknown_tool_is_reported_not_raised(tmp_path):
    # tool errors are surfaced back to the model, not raised
    provider = ScriptedProvider([
        resp(calls=[call("nope")]),
        resp("recovered"),
    ])
    assert run_agent(provider, "sys", "task", file_tools(tmp_path)) == "recovered"


def test_max_steps_bounds_the_loop(tmp_path):
    # a provider that always calls a tool must still terminate
    always = ScriptedProvider([
        resp(calls=[call("read_file", path="missing")]) for _ in range(50)
    ])
    out = run_agent(always, "sys", "task", file_tools(tmp_path), max_steps=3)
    assert always.i == 3            # stopped at the bound
    assert out == ""
