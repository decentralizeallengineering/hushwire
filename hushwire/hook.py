"""PreToolUse hook for SendMessage.

Reads the hook JSON from stdin. Prints a deny decision on stdout when the
message should not be sent; prints nothing (allow) otherwise. Any internal
error also allows the message, so the hook can never block real work.
"""
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_MAX_WORDS = 100
DEFAULT_DEDUPE_MINUTES = 30

# A message is worth sending when it asks a question, reports a blocker or
# gives an instruction. These patterns are a heuristic; extend them with
# HUSHWIRE_SIGNALS (a regular expression).
SIGNAL_RE = re.compile(
    r"\?"
    r"|\b(block(ed|er|ers|ing)|stuck|cannot|can't|unable|urgent|broken|error|fail(ed|ing|s)?)\b"
    r"|\b(please|must|need(s|ed)?|should|order(ed)?|request(ed|ing)?|go ahead|approve|approval"
    r"|decide|decision|confirm|stop|start|run|fix|review|revert|merge|ship|switch|don't|do not)\b",
    re.IGNORECASE,
)

STATUS_REASON = "status-only message (no new order, no blocker, no question): write a STATE line instead"


def state_dir():
    base = os.environ.get("HUSHWIRE_DIR")
    if base:
        return Path(base)
    xdg = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(xdg) / "hushwire"


def _int_env(name, default):
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        return default


def extract(payload):
    """Return (recipient, text) for a SendMessage payload, or None if not applicable."""
    if not isinstance(payload, dict) or payload.get("tool_name") != "SendMessage":
        return None
    tin = payload.get("tool_input")
    if not isinstance(tin, dict):
        return None
    text = next((tin[k] for k in ("message", "content", "text") if k in tin), None)
    if not isinstance(text, str):
        return None  # structured messages (protocol replies) are never blocked
    to = next((str(tin[k]) for k in ("to", "recipient", "target") if tin.get(k)), "")
    return to, text


def is_status_only(text):
    extra = os.environ.get("HUSHWIRE_SIGNALS")
    if SIGNAL_RE.search(text):
        return False
    return not (extra and re.search(extra, text, re.IGNORECASE))


def _key(to, text):
    norm = " ".join(text.lower().split())
    return hashlib.sha256(f"{to}\n{norm}".encode()).hexdigest()


def _load(path):
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".seen-")
    with os.fdopen(fd, "w") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def decide(payload, now=None, directory=None, max_words=None, dedupe_minutes=None):
    """Return a deny reason string, or None to allow. Records allowed messages for dedupe."""
    got = extract(payload)
    if got is None:
        return None
    to, text = got
    now = time.time() if now is None else now
    max_words = max_words if max_words is not None else _int_env("HUSHWIRE_MAX_WORDS", DEFAULT_MAX_WORDS)
    window = 60 * (dedupe_minutes if dedupe_minutes is not None else _int_env("HUSHWIRE_DEDUPE_MINUTES", DEFAULT_DEDUPE_MINUTES))

    if is_status_only(text):
        return STATUS_REASON
    count = len(text.split())
    if count > max_words:
        return f"message is {count} words, the limit is {max_words}: shorten it and put detail in a STATE line"

    seen_path = (directory or state_dir()) / "seen.json"
    seen = _load(seen_path)
    key = _key(to, text)
    if key in seen and now - seen[key] < window:
        return f"same text already sent to {to or 'this peer'} within {window // 60} minutes: do not repeat it"
    seen = {k: t for k, t in seen.items() if now - t < window}
    seen[key] = now
    _save(seen_path, seen)
    return None


def deny_json(reason):
    return json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    })


def run(stdin=None, stdout=None):
    """Hook entry point. Always returns 0 (fail open)."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    try:
        reason = decide(json.loads(stdin.read()))
    except Exception:  # noqa: BLE001 - failing open is the contract
        return 0
    if reason:
        stdout.write(deny_json(reason) + "\n")
    return 0
