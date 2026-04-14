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
        except ModLoadError as e:
            r.status = "error"
            r.error = f"bad mod: {e}"
        except Exception as e:
            r.status = "error"
            r.error = str(e)[:200]

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
            return
        mod_path = self.mod_dir / job.mod_filename
        prompt_text = build_prompt(job.prompt, str(mod_path).replace("\\", "/"))
        cmd = [
            claude_path, "-p", prompt_text,
            "--add-dir", str(self.mod_dir),
            "--permission-mode", "acceptEdits",
            "--allowedTools", "Write", "Edit", "Read",
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(self.repo_root),
                # shell=False is fine because shutil.which resolves claude.cmd on Windows.
            )
        except Exception as e:
            job.error = f"failed to spawn claude: {e}"
            return
        job.proc = proc
        try:
            out, err = proc.communicate(timeout=self.timeout_sec)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            job.error = "claude timed out"
        job.stdout = out or ""
        job.stderr = err or ""
        job.returncode = proc.returncode
        if not job.error and proc.returncode != 0:
            tail = (err or out or "").strip().splitlines()[-5:]
            job.error = "claude exited non-zero: " + " | ".join(tail)

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
        # Simulate thinking time so progress spinner is visible.
        time.sleep(1.0)


def _safe_filename(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")[:40]
    return slug or "research"
