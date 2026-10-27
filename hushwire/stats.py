"""Count SendMessage tool calls per session per day in Claude Code transcripts."""
import json
import os
from collections import Counter
from pathlib import Path


def default_root():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base) / "projects"


def collect(root):
    """Return Counter keyed by (day, session)."""
    counts = Counter()
    for path in sorted(Path(root).rglob("*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for raw in lines:
            if "SendMessage" not in raw:
                continue
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            content = (rec.get("message") or {}).get("content") if isinstance(rec, dict) else None
            if not isinstance(content, list):
                continue
            hits = sum(1 for b in content if isinstance(b, dict)
                       and b.get("type") == "tool_use" and b.get("name") == "SendMessage")
            if hits:
                day = str(rec.get("timestamp") or "unknown")[:10]
                counts[(day, rec.get("sessionId") or path.stem)] += hits
    return counts


def run(root=None, as_json=False, stdout=None):
    import sys
    stdout = stdout or sys.stdout
    counts = collect(root or default_root())
    rows = sorted(counts.items(), key=lambda kv: (kv[0][0], -kv[1], kv[0][1]))
    if as_json:
        stdout.write(json.dumps([{"day": d, "session": s, "messages": n} for (d, s), n in rows]) + "\n")
        return 0
    for (day, session), n in rows:
        stdout.write(f"{day}  {session}  {n}\n")
    stdout.write(f"total  {sum(counts.values())}\n")
    return 0
