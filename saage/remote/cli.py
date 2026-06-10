"""argparse wiring for `saage remote ...` — see docs/remote_handoff_plan.md."""
from __future__ import annotations

import argparse
import sys

from . import observe
from .creds import (CredsError, add_target, cred_path, ensure_ssh_key,
                    get_target, list_targets, storage_config)
from .handoff import HandoffError, handoff
from .sshio import SSHError
from .state import find_run
from .target import PreflightError, SshTarget
from .workspace import DirtyWorkspace, WorkspaceError

_ERRORS = (CredsError, HandoffError, PreflightError, WorkspaceError,
           DirtyWorkspace, SSHError, FileNotFoundError)


def add_parser(sub: argparse._SubParsersAction) -> None:
    remote = sub.add_parser("remote", help="hand a flow off to a remote node")
    rsub = remote.add_subparsers(dest="remote_command", required=True)

    rsub.add_parser("init", help="create the saage ssh key + credentials file")

    add = rsub.add_parser("add-target", help="register an SSH-able node")
    add.add_argument("name")
    add.add_argument("--host", required=True)
    add.add_argument("--user", default=None)
    add.add_argument("--port", type=int, default=22)
    add.add_argument("--hourly-usd", type=float, default=None,
                     help="rented box? status/ps will show running cost")
    add.add_argument("--no-check", action="store_true",
                     help="skip the ssh reachability check")

    ho = rsub.add_parser("handoff", help="package + push + run a flow on a target")
    ho.add_argument("flow", metavar="flow.yaml")
    ho.add_argument("--target", required=True, help="a registered target name")
    ho.add_argument("--set", dest="overrides", metavar="KEY=VALUE", action="append",
                    default=[], help="passed through to `saage run` on the node")
    ho.add_argument("--env", dest="env", metavar="KEY=VALUE", action="append",
                    default=[], help="extra env for the run (e.g. SAAGE_FORCE_CPU=1)")
    ho.add_argument("--workspace-mode", choices=["auto", "ephemeral", "package"],
                    default="auto",
                    help="auto: package the flow's workspace iff it is a git repo")
    ho.add_argument("--dirty", choices=["abort", "commit"], default="abort",
                    help="uncommitted workspace changes: abort (default) or "
                         "snapshot-commit them onto the run branch")
    ho.add_argument("--max-run-days", type=float, default=12.0,
                    help="watchdog: stop the run (never the box) after this long")
    ho.add_argument("--sync-interval", type=int, default=300,
                    help="seconds between artifact/heartbeat collections")
    ho.add_argument("--need-gpu", action="store_true",
                    help="fail preflight if the target has no working GPU")

    st = rsub.add_parser("status", help="phase, heartbeat, ledger, log tail")
    st.add_argument("run", nargs="?", default=None, help="run id or prefix (default: latest)")

    lg = rsub.add_parser("logs", help="engine log from the node")
    lg.add_argument("run", nargs="?", default=None)
    lg.add_argument("--lines", type=int, default=100)
    lg.add_argument("--live", action="store_true", help="follow (ssh tail -f)")

    rsub.add_parser("ps", help="all targets: sessions vs local state (orphan detector)")

    kl = rsub.add_parser("kill", help="stop a run (never the box)")
    kl.add_argument("run", help="run id or prefix")

    ft = rsub.add_parser("fetch", help="pull artifacts/ + log back from the node")
    ft.add_argument("run", nargs="?", default=None)
    ft.add_argument("--dest", default=None, help="default: ./results/<run_id>/")
    ft.add_argument("--bucket", action="store_true",
                    help="pull from the R2 mirror instead of the node "
                         "(automatic when the node is unreachable)")


def _parse_kv(items: list[str], what: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise CredsError(f"bad {what} {item!r}: expected KEY=VALUE")
        out[key] = value
    return out


def dispatch(args: argparse.Namespace) -> int:
    try:
        return _dispatch(args)
    except _ERRORS as exc:
        print(f"saage remote: {exc}", file=sys.stderr)
        return 1


def _dispatch(args: argparse.Namespace) -> int:
    cmd = args.remote_command
    if cmd == "init":
        key = ensure_ssh_key()
        path = cred_path()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# saage remote credentials — chmod 600\n")
            path.chmod(0o600)
        print(f"ssh key    {key}")
        print(f"creds      {path}")
        print(f"pubkey     {key.with_suffix('.pub').read_text().strip()}")
        print("add the pubkey to the target's ~/.ssh/authorized_keys, then:")
        print("  saage remote add-target <name> --host <host> [--user <user>]")
        storage = storage_config()
        if storage:
            from .observe import _bucket_client
            probe = "saage-init-probe"
            client = _bucket_client(storage)
            client.put_object(Bucket=storage.bucket, Key=probe, Body=b"ok")
            client.delete_object(Bucket=storage.bucket, Key=probe)
            print(f"storage    s3://{storage.bucket} @ {storage.endpoint} — writable ✓")
        else:
            print("storage    (none — artifacts stay on the node; add a [storage] "
                  "section for an R2 mirror)")
        return 0

    if cmd == "add-target":
        ensure_ssh_key()
        path = add_target(args.name, args.host, args.user, args.port, args.hourly_usd)
        print(f"target {args.name!r} added to {path}")
        if not args.no_check:
            warnings = SshTarget(get_target(args.name)).preflight()
            for w in warnings:
                print(f"warning: {w}")
            print(f"target {args.name!r} is reachable and ready")
        return 0

    if cmd == "handoff":
        rs = handoff(
            flow=args.flow,
            target=get_target(args.target),
            set_args=_parse_kv(args.overrides, "--set"),
            extra_env=_parse_kv(args.env, "--env"),
            workspace_mode=args.workspace_mode,
            dirty=args.dirty,
            max_run_days=args.max_run_days,
            sync_interval=args.sync_interval,
            need_gpu=args.need_gpu,
        )
        print(f"run {rs.run_id} handed off — `saage remote status {rs.run_id}`")
        return 0

    if cmd == "status":
        return observe.status(args.run)
    if cmd == "logs":
        return observe.logs(args.run, lines=args.lines, live=args.live)
    if cmd == "ps":
        return observe.ps()
    if cmd == "kill":
        return observe.kill(args.run)
    if cmd == "fetch":
        return observe.fetch(args.run, args.dest, via_bucket=args.bucket)
    raise CredsError(f"unknown remote command {cmd!r}")
