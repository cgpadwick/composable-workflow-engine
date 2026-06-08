#!/usr/bin/env python3
"""Set up the workspace ML environment.

GPU present  -> clone cgpadwick/ml-frameworks and `poetry install --no-root` the
                chosen CUDA stack into the workspace venv (curated, pinned stack).
No GPU       -> lean CPU fallback: torch (cpu wheels) + the same tabular/EDA toolkit.
Idempotent: once `import torch` works in the venv, re-running is a fast no-op.

Invoked by the flow's `setup` command:
    python3 "{flow_dir}/setup_env.py" --workspace "{workspace}" --venv "{venv}" --stack "{ml_stack}"
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ML_FRAMEWORKS_URL = "https://github.com/cgpadwick/ml-frameworks.git"
CPU_TORCH_INDEX = "https://download.pytorch.org/whl/cpu"
# CPU-fallback base — mirrors the ml-frameworks base stack (minus CUDA).
CPU_TOOLKIT = ["numpy<2.0.0", "scipy", "pandas", "scikit-learn", "joblib",
               "matplotlib", "seaborn", "tqdm", "pydantic", "pyyaml", "rich", "pytest"]


def run(cmd, **kw):
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run(cmd, check=True, **kw)


def have_gpu() -> bool:
    if os.environ.get("CWE_FORCE_CPU"):           # escape hatch for testing
        return False
    if not shutil.which("nvidia-smi"):
        return False
    return subprocess.run(["nvidia-smi"], capture_output=True).returncode == 0


def torch_ok(py: Path) -> bool:
    if not py.exists():
        return False
    return subprocess.run([str(py), "-c", "import torch, sklearn, pytest"],
                          capture_output=True).returncode == 0


def torch_report(py: Path) -> str:
    return subprocess.run(
        [str(py), "-c", "import torch; print(torch.__version__, 'cuda', torch.cuda.is_available())"],
        capture_output=True, text=True).stdout.strip()


def install_gpu_stack(venv: Path, pip: Path, stack: str, extras: str, cache: Path):
    """Clone ml-frameworks and poetry-install the chosen stack into `venv`."""
    cache.mkdir(parents=True, exist_ok=True)
    repo = cache / "ml-frameworks"
    if repo.exists():
        run(["git", "-C", str(repo), "pull", "--ff-only", "--quiet"])
    else:
        run(["git", "clone", "--depth", "1", ML_FRAMEWORKS_URL, str(repo)])
    stack_dir = repo / "stacks" / stack
    if not stack_dir.is_dir():
        avail = ", ".join(p.name for p in (repo / "stacks").iterdir())
        sys.exit(f"unknown ml-frameworks stack {stack!r}; available: {avail}")
    run([str(pip), "install", "--quiet", "poetry"])
    # virtualenvs.create=false + VIRTUAL_ENV on the workspace venv makes poetry
    # install the stack into OUR venv rather than spinning up its own.
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(venv)
    env["PATH"] = f"{venv / 'bin'}{os.pathsep}" + env.get("PATH", "")
    env["POETRY_VIRTUALENVS_CREATE"] = "false"
    extra_flags = [f for e in extras.split() for f in ("-E", e)]
    run([str(venv / "bin" / "poetry"), "install", "--no-root", *extra_flags],
        cwd=str(stack_dir), env=env)


def install_cpu_fallback(pip: Path):
    run([str(pip), "install", "--quiet", "torch", "torchvision",
         "--index-url", CPU_TORCH_INDEX])
    run([str(pip), "install", "--quiet", *CPU_TOOLKIT])


def main():
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--venv", default=".venv")
    ap.add_argument("--stack", default="pytorch-cu121")
    ap.add_argument("--extras", default="")        # e.g. "training vision"
    ap.add_argument("--cache", default=str(Path.home() / ".cache" / "cwe"))
    args = ap.parse_args()

    ws = Path(args.workspace).resolve()
    ws.mkdir(parents=True, exist_ok=True)
    venv = Path(args.venv)
    if not venv.is_absolute():
        venv = ws / venv
    py = venv / "bin" / "python"

    if torch_ok(py):
        print("setup ok (cached):", torch_report(py))
        return

    if not py.exists():
        run([sys.executable, "-m", "venv", str(venv)])
    pip = venv / "bin" / "pip"
    run([str(pip), "install", "--quiet", "--upgrade", "pip"])

    if have_gpu():
        print("GPU detected -> ml-frameworks stack:", args.stack)
        install_gpu_stack(venv, pip, args.stack, args.extras, Path(args.cache))
    else:
        print("no GPU -> CPU fallback (torch cpu wheels + toolkit)")
        install_cpu_fallback(pip)

    print("setup ok:", torch_report(py))


if __name__ == "__main__":
    main()
