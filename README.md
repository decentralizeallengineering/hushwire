# hushwire

Fewer cross-session messages for fleets of Claude Code sessions.

Why: sessions that message each other for every status update flood each other's context. Status belongs in a state file; messages should carry a new order, a blocker or a question. hushwire enforces that with a hook and gives you tools to batch and measure the rest.

## Install

    pip install .          # or run `python -m hushwire` from a checkout

Python 3.9 or newer, no dependencies.

## Hook

Add to `.claude/settings.json`:

    {"hooks": {"PreToolUse": [{"matcher": "SendMessage",
      "hooks": [{"type": "command", "command": "hushwire hook"}]}]}}

The hook denies a SendMessage call when it is

1. status-only: no question mark, blocker word or instruction word (heuristic; reason "write a STATE line instead");
2. longer than N words (default 100);
3. the same text sent to the same peer within M minutes (default 30).

It never blocks on its own failure: bad JSON, other tools, structured messages and unreadable state all allow the call.

## Configure

- `HUSHWIRE_MAX_WORDS` word cap (default 100).
- `HUSHWIRE_DEDUPE_MINUTES` dedupe window (default 30).
- `HUSHWIRE_SIGNALS` extra regular expression that marks a message as worth sending.
- `HUSHWIRE_DIR` state directory (default `$XDG_STATE_HOME/hushwire`, else `~/.local/state/hushwire`).
- `HUSHWIRE_SPOOL` note spool (default `$HUSHWIRE_DIR/spool`).
- `CLAUDE_CONFIG_DIR` where transcripts live (default `~/.claude`).

## Commands

- `hushwire note <peer> "<text>"` queues a note in `<spool>/<peer>/`.
- `hushwire digest [--spool DIR] [--keep]` prints one JSON line per peer, `{"to", "message", "notes"}`, merging that peer's queued notes (duplicates dropped). Consumed notes move to `<spool>/.sent` unless `--keep`.
- `hushwire stats [--dir DIR] [--json]` counts SendMessage tool calls per session per day from the transcripts under `<dir>/**/*.jsonl`.

## Example

    hushwire note worker-a "parser merged"
    hushwire note worker-a "docs still need a review"
    hushwire digest
    # {"to": "worker-a", "message": "2 notes:\n- parser merged\n- docs still need a review", "notes": 2}
    hushwire stats

## Tests

    python -m pytest tests

## License

Apache-2.0. See LICENSE and NOTICE.
