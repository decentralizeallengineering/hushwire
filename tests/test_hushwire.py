import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hushwire import digest, hook, stats


def payload(text, to="worker-a", tool="SendMessage"):
    return {"tool_name": tool, "tool_input": {"to": to, "message": text}}


def run_cli(args, stdin="", env=None):
    full = {**os.environ, "PYTHONPATH": str(ROOT), **(env or {})}
    return subprocess.run([sys.executable, "-m", "hushwire", *args], input=stdin, check=False,
                          capture_output=True, text=True, env=full, timeout=30)


def test_status_only_and_long_messages_are_denied(tmp_path):
    d = tmp_path
    reason = hook.decide(payload("Tests passed, all green, work continues."), directory=d)
    assert "write a STATE line instead" in reason
    assert hook.decide(payload("Blocked on the build: need the key rotated."), directory=d) is None
    assert hook.decide(payload("Can you take the parser next?"), directory=d) is None
    long = "please " + "word " * 120
    assert "limit is 100" in hook.decide(payload(long), directory=d)
    assert hook.decide(payload(long), directory=d, max_words=200) is None


def test_same_text_to_same_peer_is_deduped_within_window(tmp_path):
    text = "Please review the patch for Ann Example."
    assert hook.decide(payload(text), now=1000, directory=tmp_path, dedupe_minutes=10) is None
    assert "already sent" in hook.decide(payload(text), now=1300, directory=tmp_path, dedupe_minutes=10)
    assert hook.decide(payload(text, to="worker-b"), now=1300, directory=tmp_path, dedupe_minutes=10) is None
    assert hook.decide(payload(text), now=1000 + 601, directory=tmp_path, dedupe_minutes=10) is None


def test_hook_cli_denies_with_json_and_fails_open(tmp_path):
    env = {"HUSHWIRE_DIR": str(tmp_path)}
    res = run_cli(["hook"], json.dumps(payload("fyi, finished the task")), env)
    out = json.loads(res.stdout)["hookSpecificOutput"]
    assert res.returncode == 0 and out["permissionDecision"] == "deny"
    assert "STATE line" in out["permissionDecisionReason"]
    for bad in ("not json at all", "", json.dumps(payload("fyi done", tool="Bash")),
                json.dumps({"tool_name": "SendMessage", "tool_input": {"message": {"type": "shutdown"}}})):
        res = run_cli(["hook"], bad, env)
        assert res.returncode == 0 and res.stdout == ""
    blocked = {"HUSHWIRE_DIR": str(tmp_path / "file")}
    (tmp_path / "file").write_text("a file where a directory is needed")
    res = run_cli(["hook"], json.dumps(payload("Please run the suite.")), blocked)
    assert res.returncode == 0 and res.stdout == ""


def test_digest_coalesces_notes_per_peer(tmp_path):
    spool = tmp_path / "spool"
    digest.add_note(spool, "worker-a", "step one done")
    digest.add_note(spool, "worker-a", "step two\nneeds review")
    digest.add_note(spool, "worker-a", "step one done")
    digest.add_note(spool, "worker-b", "single note")
    res = run_cli(["digest", "--spool", str(spool)])
    items = [json.loads(x) for x in res.stdout.splitlines()]
    assert [i["to"] for i in items] == ["worker-a", "worker-b"]
    assert items[0]["message"] == "2 notes:\n- step one done\n- step two needs review"
    assert items[0]["notes"] == 3 and items[1]["message"] == "1 note:\n- single note"
    assert run_cli(["digest", "--spool", str(spool)]).stdout == ""
    assert len(list((spool / ".sent" / "worker-a").iterdir())) == 3


def test_stats_counts_send_message_per_session_per_day(tmp_path):
    def rec(ts, session, *names):
        blocks = [{"type": "tool_use", "name": n, "input": {}} for n in names]
        return json.dumps({"type": "assistant", "timestamp": ts, "sessionId": session,
                           "message": {"content": blocks}})

    proj = tmp_path / "projects" / "demo"
    proj.mkdir(parents=True)
    (proj / "a.jsonl").write_text("\n".join([
        rec("2026-03-01T10:00:00Z", "s1", "SendMessage"),
        rec("2026-03-01T11:00:00Z", "s1", "Bash", "SendMessage"),
        rec("2026-03-02T09:00:00Z", "s1", "SendMessage"),
        "this line is not json but mentions SendMessage",
        json.dumps({"type": "user", "message": {"content": "SendMessage"}}),
    ]) + "\n")
    (proj / "b.jsonl").write_text(rec("2026-03-01T12:00:00Z", "s2", "SendMessage") + "\n")
    got = stats.collect(tmp_path / "projects")
    assert got[("2026-03-01", "s1")] == 2 and got[("2026-03-02", "s1")] == 1
    assert got[("2026-03-01", "s2")] == 1 and sum(got.values()) == 4
    res = run_cli(["stats", "--dir", str(tmp_path / "projects"), "--json"])
    rows = json.loads(res.stdout)
    assert {"day": "2026-03-01", "session": "s1", "messages": 2} in rows
