"""Calls the pinned Parse Judge TypeScript adapters and judge through a small Node bridge."""

import contextlib
import fcntl
import json
import os
import random
import re
import subprocess
import tempfile
import time
from pathlib import Path

from . import PARSEJUDGE_COMMIT, PARSEJUDGE_REPO
from .datasets import CACHE

BRIDGE_SRC = Path(__file__).resolve().parent.parent / "bridge" / "parsejudge-bridge.ts"


def parsejudge_dir() -> Path:
    """Checkout of parsejudge at PARSEJUDGE_COMMIT with dependencies installed (PARSEJUDGE_DIR overrides)."""
    if os.environ.get("PARSEJUDGE_DIR"):
        root = Path(os.environ["PARSEJUDGE_DIR"])
    else:
        root = CACHE / f"parsejudge-{PARSEJUDGE_COMMIT[:12]}"
        if not (root / ".ready").exists():
            if not root.exists():
                subprocess.run(["git", "clone", "-q", PARSEJUDGE_REPO, str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "checkout", "-q", PARSEJUDGE_COMMIT], check=True)
            subprocess.run(
                ["pnpm", "install", "--frozen-lockfile"], cwd=root, check=True, capture_output=True
            )
            (root / ".ready").touch()
    write_png_variant(root)
    target = root / "packages" / "core" / ".benchbench" / "bridge.ts"
    target.parent.mkdir(exist_ok=True)
    write_if_changed(target, BRIDGE_SRC.read_bytes())
    return root


def write_if_changed(path: Path, data: bytes) -> bool:
    """Atomically replace `path` with `data` (temp file in the same dir, then os.replace), so a bridge
    starting in another process never reads a half-written file. No write when the content is unchanged."""
    if path.exists() and path.read_bytes() == data:
        return False
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
    return True


PNG_VERSION = "compare-v4-png"
# Judge image settings. The defaults are the ones every study verdict used and are never written into a
# verdict config, so verdicts from before these settings existed still match.
# OpenAI `detail`: "high" resizes to a 2,500-patch budget (a 200-DPI letter page drops to ~165 DPI);
# "original" (--image-detail original) keeps the rendered pixels.
IMAGE_DETAIL = "high"
# Gemini: "" = the OpenAI-compatible endpoint at Gemini's default resolution. A MEDIA_RESOLUTION_* level
# (--gemini-media-resolution) sends the call to the native API at that per-image level (geminiNative).
GEMINI_MEDIA_RESOLUTION = ""
_URL_CLAUSE = re.compile(r"### Hyperlinks and embedded URLs:\n(?:- .*\n)+\n")


def write_png_variant(root: Path) -> None:
    """compare-v4 minus its hyperlink clause, which assumes a PDF link layer; our judge sees only a PNG.

    Written as sibling files in the pinned checkout so the judge code is otherwise byte-identical.
    """
    src = root / "packages" / "core" / "src"
    prompt, n = _URL_CLAUSE.subn("", (src / "prompt.ts").read_text())
    if n != 1:
        raise RuntimeError("compare-v4 hyperlink clause not found; update _URL_CLAUSE for this commit")
    judge = (src / "judge.ts").read_text()
    for old, new in [
        ('from "./prompt.ts"', 'from "./prompt.benchbench-png.ts"'),
        ('JUDGE_VERSION = "compare-v4"', f'JUDGE_VERSION = "{PNG_VERSION}"'),
        ('detail: "high"', 'detail: process.env.BENCHBENCH_IMAGE_DETAIL ?? "high"'),
    ]:
        if old not in judge:
            raise RuntimeError(f"judge.ts changed upstream: {old!r} missing")
        judge = judge.replace(old, new)
    for name, text in [("prompt.benchbench-png.ts", prompt), ("judge.benchbench-png.ts", judge)]:
        write_if_changed(src / name, text.encode())
    exclude = root / ".git" / "info" / "exclude"
    lines = ["packages/core/src/*.benchbench-png.ts", "packages/core/.benchbench/"]
    if exclude.parent.exists():
        have = exclude.read_text() if exclude.exists() else ""
        missing = [ln for ln in lines if ln not in have.splitlines()]
        if missing:
            exclude.write_text(have + "".join(ln + "\n" for ln in missing))


def png_variant_sha(root: Path) -> str:
    """SHA-256 of the generated compare-v4-png prompt, recorded in every verdict it produces."""
    import hashlib

    return hashlib.sha256((root / "packages/core/src/prompt.benchbench-png.ts").read_bytes()).hexdigest()[:16]


def parsejudge_commit(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()


MAX_BRIDGES = int(os.environ.get("BENCHBENCH_MAX_BRIDGES", "160"))
SLOT_DIR = Path(
    os.environ.get("BENCHBENCH_BRIDGE_SLOTS", str(Path.home() / ".cache" / "benchbench" / "bridge-slots"))
)


@contextlib.contextmanager
def bridge_slot():
    """Box-wide cap on live node bridges (~125 MB each) across every benchbench process.

    One flock per slot file; the kernel drops a lock when its process dies, so a crash never leaks a slot.
    """
    SLOT_DIR.mkdir(parents=True, exist_ok=True)
    start = random.randrange(MAX_BRIDGES)
    while True:
        for i in range(MAX_BRIDGES):
            fd = os.open(SLOT_DIR / f"{(start + i) % MAX_BRIDGES}", os.O_CREAT | os.O_RDWR)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                continue
            try:
                yield
            finally:
                os.close(fd)
            return
        time.sleep(0.2 + random.random() * 0.3)


def call(request: dict, timeout: int = 1200, env: dict | None = None) -> dict:
    with bridge_slot():
        return _call(request, timeout, env)


def _call(request: dict, timeout: int = 1200, env: dict | None = None) -> dict:
    root = parsejudge_dir()
    bridge = root / "packages" / "core" / ".benchbench" / "bridge.ts"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(request, f)
        req_path = f.name
    try:
        proc = subprocess.run(
            ["node", str(bridge), req_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=bridge.parent,
            env={**os.environ, **(env or {})},
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"bridge timeout {timeout}s", "retryable": True}
    finally:
        os.unlink(req_path)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("{")]
    if not lines:
        return {"ok": False, "error": (proc.stderr or "no output")[-2000:], "retryable": False}
    return json.loads(lines[-1])
