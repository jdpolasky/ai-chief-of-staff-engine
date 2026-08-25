# Incidents

This is the incident logbook: the folder where failures get written down as data. The
thesis is simple. A working assistant system improves by logging its failures and
mining them for patterns, not by relitigating each one as an argument. A record outlives
the mood that produced it; an argument does not.

For the full why and how, read [`../docs/LOGBOOK.md`](../docs/LOGBOOK.md). This file is
the short reference for what lives here and the format.

## What lives here

- **One record per failure**, named `YYYY-MM-DD-<slug>.md`. The slug is a few words of
  what broke, in kebab-case.
- **`INDEX.md`**, the lean catalog: one line per record, never a narrative.
- **The worked example**, `2026-05-28-seedling-order-rederived.md`, which ships with the
  kit so the format is concrete. It is a fictional record for the sample persona; adapt
  it out of your own live folder when you install.

The two commands that write here are `commands/incident.md` (capture) and
`commands/incident-review.md` (mine for patterns and graduate repeats into rules).

## The record format

Each record is markdown with YAML frontmatter:

```markdown
---
date: 2026-05-28
actor: assistant
class: skipped-verification
status: logged
---

# Short title of what broke

## What happened
Two to four plain sentences.

## Root cause
The real cause, not the flattering one.

## Cost
One line: time, money, or trust.

## Rule candidate
The rule that would have prevented it, or "none yet".
```

- `actor`: `assistant`, `owner`, or `both`.
- `class`: one of `wrong-assumption`, `skipped-verification`, `scope-creep`,
  `instruction-miss`, `tooling-gap`, `owner-process`.
- `status`: `logged` at capture, `graduated` once a review turns its pattern into a
  rule.

## The lean-index rule

`INDEX.md` is one line per record and nothing more: date, linked title, class, status.
It is the catalog you scan at review to see shape across many records. The moment the
index starts carrying narrative, it stops being scannable, and the detail already lives
in the records. Keep it lean.
