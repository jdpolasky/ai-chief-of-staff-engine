---
mode: <kebab-name>
status: draft            # draft | active | retired
owner_approved: <YYYY-MM-DD or blank until the owner signs off>
---

# Mode: <Name>

## Purpose

One paragraph. What this mode is for, and the one context it serves. If you cannot
say what the mode is for in a sentence or two, it is doing too much; split it.

## May

- The allowed actions, one per line. Be concrete.
- Name the surfaces this mode is allowed to touch and the tools it is allowed to use.
- Keep this list accurate, not aspirational: only what the mode actually does.

## Must never

- The hard limits, one per line. These outrank the May list.
- Write the failure modes you have actually seen, not abstractions.
- A good Must-never line names a real behavior the mode is tempted into and forbids it.

## Entry

How the mode is invoked (a command, a phrase, a schedule) and what it loads on entry:
which memory facts, which files, which prior state. State the contract is held for the
whole stretch, not just the first message.

## Exit

How the mode hands back: what it writes on close, what it hands to another mode, how
the owner knows the stretch is over. A mode that never closes cleanly leaks into the
next one.

## Tone

Two or three sentences. The register this mode holds: how it talks, how much it
asserts versus asks, how it sounds when it says no.

## Escalation

When this mode must stop and hand off: to the owner for a decision it may not make, or
to another mode for work it may not do. Name the trigger and the destination.
