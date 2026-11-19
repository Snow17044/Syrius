"""Exécute les tests d'un petit projet dans un dossier temporaire, avec limites (temps, mémoire, environnement vidé)."""
from __future__ import annotations

import os
import re
import resource
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

TIMEOUT = 20


@contextmanager
def project(files: dict):
    d = Path(tempfile.mkdtemp(prefix="coder_"))
    try:
        for p, t in files.items():
            f = d / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(t, encoding="utf-8")
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _limits():
    resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT, TIMEOUT))
    resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 22, 1 << 22))


def run_tests(root, timeout: int = TIMEOUT) -> tuple[bool, str, int]:
    """(tout passe, sortie courte, nombre de tests réussis)."""
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(root),
           "PYTHONPATH": str(root), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "--no-header", "-p", "no:cacheprovider"],
                           cwd=root, env=env, capture_output=True, text=True, timeout=timeout, preexec_fn=_limits)
    except subprocess.TimeoutExpired:
        return False, "temps dépassé", 0
    out = (r.stdout + r.stderr).replace(str(root), ".").strip()
    out = re.sub(r" in [\d.]+s( \([^)]*\))?", "", out)  # durées et dossiers temporaires varient : sortie stable
    m = re.search(r"(\d+) passed", out)
    return r.returncode == 0, out[-1500:], int(m.group(1)) if m else 0
