"""The `hushwire` command line."""
import argparse

from hushwire import digest, hook, stats


def build_parser():
    p = argparse.ArgumentParser(prog="hushwire", description="Fewer cross-session messages for Claude Code.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("hook", help="PreToolUse hook for SendMessage: reads hook JSON on stdin")

    note = sub.add_parser("note", help="queue a note for a peer in the spool")
    note.add_argument("peer")
    note.add_argument("text")
    note.add_argument("--spool", help="spool directory (default $HUSHWIRE_SPOOL)")

    dg = sub.add_parser("digest", help="coalesce queued notes into one JSON message per peer")
    dg.add_argument("--spool", help="spool directory (default $HUSHWIRE_SPOOL)")
    dg.add_argument("--keep", action="store_true", help="leave the notes in the spool")

    st = sub.add_parser("stats", help="SendMessage calls per session per day from transcripts")
    st.add_argument("--dir", help="transcript root (default $CLAUDE_CONFIG_DIR/projects or ~/.claude/projects)")
    st.add_argument("--json", action="store_true")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.cmd == "hook":
        return hook.run()
    if a.cmd == "note":
        print(digest.add_note(digest.spool_dir(a.spool), a.peer, a.text))
        return 0
    if a.cmd == "digest":
        return digest.run(a.spool, a.keep)
    return stats.run(a.dir, a.json)


if __name__ == "__main__":
    raise SystemExit(main())
