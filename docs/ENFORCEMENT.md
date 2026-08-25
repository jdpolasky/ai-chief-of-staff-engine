# Enforcement

Operating rules decay when they live only as prose. The model is asked to remember "stop and
check before acting" or "never edit the owner's invoicing file," and most of the
time it does, until a long session, a confident wrong turn, or a fresh context
window quietly drops the rule. Prose is a hope, not a guarantee.

Enforcement moves the rules out of the model's memory and into the harness around
it. A hook is a small script the runtime runs on your behalf at a fixed moment:
before a tool call, or when the assistant tries to end its turn. The script can
let the action through or block it. Because the runtime runs it, not the model, a
hook cannot be forgotten, talked around, or lost to a context window. The rule
holds whether the model remembers it or not.

This stage ships three hooks, a config file for each, and a probe that proves
every branch of all three. They are grounded in the official Claude Code hooks
reference: <https://code.claude.com/docs/en/hooks>. Every claim below about what a
hook receives and how it blocks comes from that page.

## The three hooks

**protect_surfaces** (runs before an Edit, Write, or NotebookEdit). This enforces
the propose/commit split: you commit changes to your own surfaces, the assistant
only proposes them. If the assistant tries to edit a file you marked protected,
the hook blocks it and tells the assistant to show you the change and ask you to
either make it yourself or grant a one-time override. The override is a small
empty file you create, named `.consent-<label>`, in the hooks config folder; the
hook deletes it the moment it is used, so it is good for exactly one edit.

**effort_governor** (runs before every tool call). This is a runaway brake. It
counts how many tool calls a session has made and trips at thresholds you set: a
quiet warning, then a one-time hard stop that forces the assistant to tell you
what it is doing and how much further it expects to go, then a ceiling that blocks
everything until you raise the limit. It is deliberately blunt. It does not judge
whether the work is good, only how much of it there has been.

**output_lint** (runs when the assistant tries to end its turn). This reads the
assistant's final message and checks it against regex rules you turn on. If a rule
matches, the stop is blocked and the assistant has to rewrite before it hands the
turn back. It ships with three example rules (ban the em-dash, flag a suspiciously
long quote, flag three hedging words stacked in one sentence); all but the
first are off by default. It is a last-line style check, not a content
judge.

## The fail-open philosophy, and its tradeoff

These hooks run inside your live session on tool calls and turn-endings. A bug in
a hook, or a half-finished pip install, could in principle wedge your session: if
a hook crashed and the runtime read that as "block," you could be locked out of
your own files or unable to end a turn.

So every hook here is built to **fail open**. Each one wraps its whole body in a
catch-all: if anything goes wrong (bad input, a corrupt state file, a broken regex
in your config, a missing file), the hook logs the problem to its error stream and
allows the action. The hooks are also **standard-library only**, no third-party
imports, so a broken dependency cannot stop them from running at all. Their config
files are plain JSON for the same reason.

The tradeoff: fail-open means a broken hook silently stops enforcing. If
your governor config has a typo, the brake quietly does nothing rather than
blocking you. That is the deliberate choice. A guardrail that occasionally fails
to guard is recoverable; a guardrail that can lock you out of your own machine is
not. If you want to know a hook is healthy, run the probe (below); do not rely on
it to announce its own silence.

## What the governor can and cannot see

This matters because it is tempting to expect more of the brake than it can
deliver. A before-tool hook, per the docs, receives one tool call at a time with a
stable `session_id`. So the governor **can** keep a running count per session and
trip at a total.

It **cannot** see turn boundaries: it has no way to tell where one of your prompts
ends and the next begins, so "calls this turn" is not available to it; it counts
the whole session. And it **cannot** see tool results: a before-tool hook fires
before the tool runs, so it never learns whether a call succeeded or failed, which
means "stop after N consecutive failures" is not something it can do. It is a
session-total odometer with trip points, nothing cleverer. The config comment says
so too, so nobody is surprised later.

## How to install

These are off until you wire them in. Hooks live in your `settings.json` under a
`hooks` key, grouped by event, each with a `matcher` that picks which tools fire
the hook. The structure below is copied from the official format in the docs page
linked above. Point the `command` paths at wherever you copied this repo's
`hooks/` folder; `${CLAUDE_PROJECT_DIR}` expands to your project root, so the
example uses it.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python ${CLAUDE_PROJECT_DIR}/hooks/protect_surfaces.py"
          }
        ]
      },
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python ${CLAUDE_PROJECT_DIR}/hooks/effort_governor.py"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python ${CLAUDE_PROJECT_DIR}/hooks/output_lint.py"
          }
        ]
      }
    ]
  }
}
```

The `matcher` is the tool name (or names joined with `|`); `protect_surfaces`
matches the three write tools, while the governor and lint use `*` so they see
everything. After editing `settings.json`, restart your assistant session so it
loads the hooks, then prove they work by running the probe and by trying a real
protected edit (see "Verify" below).

Adapt `hooks/config/protected_surfaces.json` to your own files. The shipped globs
follow the sample vault (paths under `sample-vault/state`, the invoicing note, the
studio hub). Replace them with globs for the files you actually want to commit
yourself. Each entry is `{ "pattern": <glob>, "label": <short-name>, "note":
<why> }`; the label is what the consent file is named after, so keep it short and
filename-safe.

## How to write your own lint rule

Open `hooks/config/lint_rules.json` and add an entry to the `rules` list:

```json
{
  "name": "no_apology_opener",
  "pattern": "(?i)^\\s*(?:sorry|apolog)",
  "message": "Your final message opens with an apology. Cut it and lead with the answer, then stop.",
  "enabled": true
}
```

`name` is a label for you. `pattern` is a Python regular expression tested against
the assistant's final message; keep it specific so it does not fire on innocent
text. `message` is what the assistant is told when the rule matches, so write it
as an instruction to rewrite. `enabled` turns it on. A rule with a broken regex is
skipped (logged, not fatal), so a typo in one rule never disables the others.

## Verify

Two checks, both worth doing after you wire the hooks in.

1. Run the probe: `python -m cos regress` runs the whole suite, including
   `probe_hooks`, which drives all three hook scripts through every branch (allow,
   block, consent consumed, fail-open). Green means the scripts themselves are
   sound.
2. Try it live: in a scratch session, ask the assistant to edit one of your
   protected files. You should see it blocked with a message telling it to propose
   the change instead. Then create the named `.consent-<label>` file, ask again,
   and confirm the edit goes through once and the consent file disappears.

## Default posture

Nothing here runs until you add it to your `settings.json`, and the lint
rules beyond the em-dash arrive turned off. Turn on
what you actually need. The protect hook is worth it the moment you have a file
you never want auto-edited; the governor is worth it the first time a session runs
away from you; the lint is worth it when you have a style line you keep having to
repeat. Start with one, prove it, add the next.
