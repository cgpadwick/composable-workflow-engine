"""Thin subprocess wrappers around ssh/rsync.

Every byte the remote machinery moves to or from a node goes through SSHConn,
so the key, options, and timeouts live in exactly one place. BatchMode keeps
everything non-interactive: a target that would prompt for a password fails
fast instead of hanging a handoff.
"""
from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


class SSHError(RuntimeError):
    """An ssh/rsync invocation failed."""


@dataclass
class SSHConn:
    host: str
    user: str | None = None
    key: Path | None = None
    port: int = 22
    connect_timeout: int = 10

    @property
    def dest(self) -> str:
        return f"{self.user}@{self.host}" if self.user else self.host

    def _opts(self) -> list[str]:
        opts = [
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"ConnectTimeout={self.connect_timeout}",
            "-o", "ServerAliveInterval=30",
            "-p", str(self.port),
        ]
        if self.key:
            opts += ["-i", str(self.key), "-o", "IdentitiesOnly=yes"]
        return opts

    def run(self, command: str, *, input: str | None = None, timeout: int = 120,
            check: bool = True) -> subprocess.CompletedProcess:
        """Run `command` on the node through the login shell."""
        argv = ["ssh", *self._opts(), self.dest, command]
        try:
            proc = subprocess.run(argv, input=input, capture_output=True,
                                  text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise SSHError(f"ssh {self.dest} timed out after {timeout}s: {command}") from exc
        if check and proc.returncode != 0:
            raise SSHError(
                f"ssh {self.dest} exited {proc.returncode}: {command}\n"
                f"{(proc.stderr or proc.stdout).strip()}"
            )
        return proc

    def capture(self, command: str, *, timeout: int = 120) -> str:
        return self.run(command, timeout=timeout).stdout

    def ok(self, command: str, *, timeout: int = 60) -> bool:
        try:
            return self.run(command, timeout=timeout, check=False).returncode == 0
        except SSHError:
            return False

    def write_file(self, remote_path: str, content: str, *, mode: str = "600",
                   timeout: int = 60) -> None:
        """Write `content` to the node over stdin — never via argv (ps-visible)."""
        quoted = shlex.quote(remote_path)
        self.run(
            f"install -m {mode} /dev/null {quoted} && cat > {quoted}",
            input=content, timeout=timeout,
        )

    # -- rsync ---------------------------------------------------------------

    def _rsh(self) -> str:
        return shlex.join(["ssh", *self._opts()])

    def rsync_to(self, src: Path, remote_dest: str, *, excludes: tuple[str, ...] = (),
                 delete: bool = False, timeout: int = 900) -> None:
        """rsync a local file or dir to `remote_dest` (relative to the node $HOME)."""
        argv = ["rsync", "-az", *(f"--exclude={e}" for e in excludes)]
        if delete:
            argv.append("--delete")
        argv += ["-e", self._rsh(), str(src), f"{self.dest}:{remote_dest}"]
        self._rsync(argv, timeout)

    def rsync_from(self, remote_src: str, dest: Path, *, timeout: int = 900) -> None:
        argv = ["rsync", "-az", "-e", self._rsh(), f"{self.dest}:{remote_src}", str(dest)]
        self._rsync(argv, timeout)

    @staticmethod
    def _rsync(argv: list[str], timeout: int) -> None:
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise SSHError(f"rsync timed out after {timeout}s") from exc
        if proc.returncode != 0:
            raise SSHError(f"rsync exited {proc.returncode}:\n{proc.stderr.strip()}")
