from __future__ import annotations

import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from engine.registry import Registry
from engine.state import GameState

from .loader import ModLoadError, find_new_mods, load_mod_file
from .prompt import build_prompt

DEFAULT_TIMEOUT_SEC = 180


@dataclass
class _Job:
    prompt: str
    mod_filename: str
    started_at: float = field(default_factory=time.time)
    proc: Optional[subprocess.Popen] = None
    stdout: str = ""
    stderr: str = ""
    returncode: Optional[int] = None
    error: Optional[str] = None
    finished: bool = False
    log_path: Optional[str] = None


class ResearchRunner:
    def __init__(self, *, state: GameState, registry: Registry, mod_dir: Path,
                 use_stub: bool = False, repo_root: Path,
                 timeout_sec: int = DEFAULT_TIMEOUT_SEC):
        self.state = state
        self.registry = registry
        self.mod_dir = mod_dir
        self.use_stub = use_stub
        self.repo_root = repo_root
        self.timeout_sec = timeout_sec
        self.loaded_files: set[str] = set()
        self._job: Optional[_Job] = None
        self._thread: Optional[threading.Thread] = None

    # ---------- public API (called from main thread) ----------

    def start(self, prompt: str) -> None:
        if self._job is not None and not self._job.finished:
            return  # already running
        fname = _safe_filename(prompt) + ".py"
        self._job = _Job(prompt=prompt, mod_filename=fname)
        self._thread = threading.Thread(target=self._run_job, args=(self._job,), daemon=True)
        self._thread.start()

    def poll(self) -> None:
        job = self._job
        if job is None or not job.finished:
            return
        # One-shot: consume result, clear job, apply to state.
        self._job = None
        r = self.state.research
        r.log_path = job.log_path
        try:
            if job.error:
                raise RuntimeError(job.error)
            new_files = find_new_mods(self.mod_dir, self.loaded_files)
            if not new_files:
                raise RuntimeError("Claude did not produce a mod file")
            # Load the most recent new file (by mtime).
            target = max(new_files, key=lambda p: p.stat().st_mtime)
            registered = load_mod_file(target, self.registry)
            self.loaded_files.add(target.name)
            r.status = "done"
            r.last_result_name = registered[0] if registered else "(unnamed)"
            r.error = None
            print(f"[research] OK: {r.last_result_name} (mod: {target}; log: {job.log_path})")
        except ModLoadError as e:
            r.status = "error"
            r.error = f"bad mod: {e}"
            print(f"[research] FAILED: {r.error} (log: {job.log_path})", file=sys.stderr)
        except Exception as e:
            r.status = "error"
            r.error = str(e)[:200]
            print(f"[research] FAILED: {r.error} (log: {job.log_path})", file=sys.stderr)

    # ---------- worker thread ----------

    def _run_job(self, job: _Job) -> None:
        try:
            if self.use_stub:
                self._write_stub_mod(job)
            else:
                self._run_claude(job)
        except Exception as e:
            job.error = f"runner crashed: {e}"
        finally:
            job.finished = True

    def _run_claude(self, job: _Job) -> None:
        claude_path = shutil.which("claude")
        if claude_path is None:
            job.error = "claude CLI not found on PATH"
            self._write_log(job, cmd=None)
            return
        # Sandbox: run Claude with cwd=mod_dir so the workspace IS the sandbox.
        # No `--add-dir`: that widens scope, and we want it narrow. Claude sees
        # only the mod_dir; the ModAPI contract is embedded in the prompt.
        #
        # Pass the prompt via stdin, not argv. The Windows `claude.CMD` wrapper
        # re-parses argv through cmd.exe, which mangles multi-line prompts.
        prompt_text = build_prompt(job.prompt, job.mod_filename)
        cmd = [
            claude_path, "-p",
            "--permission-mode", "acceptEdits",
            "--allowedTools", "Write,Edit,Read",
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(self.mod_dir),
                # shell=False is fine because shutil.which resolves claude.cmd on Windows.
            )
        except Exception as e:
            job.error = f"failed to spawn claude: {e}"
            self._write_log(job, cmd=cmd)
            return
        job.proc = proc
        try:
            out, err = proc.communicate(input=prompt_text, timeout=self.timeout_sec)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            job.error = "claude timed out"
        job.stdout = out or ""
        job.stderr = err or ""
        job.returncode = proc.returncode
        if not job.error and proc.returncode != 0:
            tail = (err or out or "").strip().splitlines()[-3:]
            job.error = f"claude exited {proc.returncode}: " + " | ".join(tail)
        self._write_log(job, cmd=cmd)

    def _write_log(self, job: _Job, cmd: Optional[list[str]]) -> None:
        try:
            log_path = self.mod_dir / "_research.log"
            with log_path.open("a", encoding="utf-8") as f:
                f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
                f.write(f"PROMPT: {job.prompt}\n")
                f.write(f"FILE:   {job.mod_filename}\n")
                if cmd is not None:
                    # Truncate the embedded prompt arg so the log stays readable.
                    pretty = []
                    for i, a in enumerate(cmd):
                        if i > 0 and cmd[i - 1] == "-p" and len(a) > 200:
                            pretty.append(a[:200] + f"... [{len(a)} chars]")
                        else:
                            pretty.append(a)
                    f.write(f"CMD:    {pretty}\n")
                f.write(f"RC:     {job.returncode}\n")
                if job.error:
                    f.write(f"ERROR:  {job.error}\n")
                f.write("---- STDOUT ----\n")
                f.write(job.stdout or "(empty)\n")
                f.write("\n---- STDERR ----\n")
                f.write(job.stderr or "(empty)\n")
            job.log_path = str(log_path)
        except Exception:
            pass

    def _write_stub_mod(self, job: _Job) -> None:
        """Generate a simple mod locally — for dev iteration without calling Claude."""
        path = self.mod_dir / job.mod_filename
        name = " ".join(w.capitalize() for w in re.findall(r"[A-Za-z0-9]+", job.prompt))[:32] or "Invention"
        shape = "circle"
        desc = f"A stub unit inspired by: {job.prompt}"
        src = f'''def register(api):
    api.register_unit(
        name={name!r},
        attack=3, defense=3, move=1, cost=40,
        shape={shape!r}, color=(180, 120, 60),
        description={desc!r},
    )
'''
        path.write_text(src, encoding="utf-8")
        job.stdout = f"stub wrote {path}"
        job.returncode = 0
        self._write_log(job, cmd=None)
        # Simulate thinking time so progress spinner is visible.
        time.sleep(1.0)


def _safe_filename(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")[:40]
    return slug or "research"
