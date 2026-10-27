"""Spool of queued notes, coalesced into one message per peer."""
import json
import os
import re
import time
from pathlib import Path


def spool_dir(override=None):
    if override:
        return Path(override)
    env = os.environ.get("HUSHWIRE_SPOOL")
    if env:
        return Path(env)
    from hushwire.hook import state_dir
    return state_dir() / "spool"


def safe_peer(name):
    clean = re.sub(r"[^A-Za-z0-9._-]", "_", name).lstrip(".")
    if not clean:
        raise ValueError("peer name is empty")
    return clean


def add_note(spool, peer, text):
    """Queue one note for a peer; returns the file written."""
    folder = Path(spool) / safe_peer(peer)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{time.time_ns()}-{os.getpid()}.txt"
    path.write_text(text.strip() + "\n")
    return path


def digest(spool, keep=False):
    """Return [{'to', 'message', 'notes'}] with one entry per peer that has queued notes.

    Consumed notes move to <spool>/.sent unless keep is true.
    """
    spool = Path(spool)
    out = []
    if not spool.is_dir():
        return out
    for folder in sorted(p for p in spool.iterdir() if p.is_dir() and not p.name.startswith(".")):
        files = sorted(f for f in folder.iterdir() if f.is_file() and f.suffix == ".txt")
        lines = []
        for f in files:
            line = " ".join(f.read_text().split())
            if line and line not in lines:
                lines.append(line)
        if not lines:
            continue
        message = f"{len(lines)} note{'s' if len(lines) != 1 else ''}:\n" + "\n".join(f"- {x}" for x in lines)
        out.append({"to": folder.name, "message": message, "notes": len(files)})
        if not keep:
            sent = spool / ".sent" / folder.name
            sent.mkdir(parents=True, exist_ok=True)
            for f in files:
                f.replace(sent / f.name)
    return out


def run(spool=None, keep=False, stdout=None):
    import sys
    stdout = stdout or sys.stdout
    items = digest(spool_dir(spool), keep=keep)
    for item in items:
        stdout.write(json.dumps(item) + "\n")
    return 0
