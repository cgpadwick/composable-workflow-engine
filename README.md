# Composable Workflow Engine

A **deterministic** composable agentic workflow engine. Control flow (loops, retries,
polling, exit conditions) is owned by code — not by an LLM's judgment — while individual
steps still use LLMs to do the work.

Built on [PocketFlow](https://github.com/The-Pocket/PocketFlow) (graph + shared-store),
plus a lightweight first-class harness (file CRUD + exec + git tools) that LLM steps drive
through a native, provider-agnostic agent loop. Workflows are authored in YAML and hydrated
into runnable flows. Existing Claude-format markdown skills are imported as-is.

## Why

Composing skills into agent files inside existing harnesses (Claude Code, Gemini, Codex,
Copilot, Windsurf) works but is non-deterministic: the harness, not your spec, decides
control flow — and it decides badly (e.g. a poll step launched in the background that never
returns). The same workflow run twice gives different results; swapping models changes
behavior entirely. This engine makes the LLM choose only *content*, never *control flow*.

## Status

Early design. See [`docs/plan.md`](docs/plan.md) for the architecture and build milestones.
