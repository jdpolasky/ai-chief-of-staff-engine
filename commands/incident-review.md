---
name: incident-review
description: Mine the incident logbook for repeat patterns. Read the index and recent records, group by class and root cause, propose feedback rules for repeats, and on the owner's approval write each rule into the memory corpus and re-seed so the engine learns it.
---

# /incident-review — mine the logbook for patterns

Run this every few weeks, once enough records have accumulated to see a shape. Single
incidents are noise. The signal is the repeat: the same failure, in the same shape,
more than once. This command finds those repeats and turns the durable ones into rules
the memory engine seeds, so a recurring failure becomes a standing correction instead
of a thing you keep relearning.

The loop this command closes: capture (`/incident`), classify, review (here), graduate
the repeats into feedback rules, and when a graduated rule still fails, escalate it to
an enforcement hook. Prose that keeps failing is prose that should be machinery.

## Step 1: read the logbook

Read `incidents/INDEX.md` for the full catalog, then read the records since the last
review (or all of them on a first pass). You are reading for shape, not detail: what
kept happening, not what happened once.

## Step 2: group by class and by root cause

Group the records two ways:

1. **By `class`.** Count records per class. A class with several records is a
   standing weakness, even if the surface details differ.
2. **By root-cause similarity.** Read the "Root cause" sections and cluster the ones
   that name the same underlying cause, regardless of class. Two records can share a
   root cause across different classes; this is the grouping that matters most, because
   the rule attaches to the cause.

## Step 3: surface the repeats

A repeat pattern is two or more records that share a shape: same class or same root
cause, same kind of failure. For each repeat, write a short block:

- **The pattern,** in one line: what keeps happening.
- **The source records,** by filename: the two-plus records that establish it.
- **A proposed feedback rule,** written in the kit's feedback-memory format (below).

Single records with no repeat do not get a rule yet. Name them in one line as
"watching" so the next review knows to look, but do not graduate a pattern of one. A
rule earns its place by a failure happening twice.

## Step 4: propose the rule, do not write it yet

This is the propose half of propose/commit. Show the owner each proposed rule and wait.
The owner approves a rule before it becomes a memory file. They may reject it, reword
it, or ask you to wait for one more occurrence. Do not write any rule the owner has not
approved.

A proposed feedback rule is a full `feedback_*.md` file, in the exact shape the loader
ingests. Match the shipped feedback memories: top-level YAML frontmatter with `name`,
`description`, `type: feedback`, optional `tags`, optional `originSession`, then the
rule in prose with a `**Why:**` line and a `**How to apply:**` line. The Why cites the
source incidents by what happened, so the rule traces back to its evidence.

```markdown
---
name: feedback-read-the-source-before-confirming
description: Open and read a written source before confirming any number, never confirm a quantity from memory.
type: feedback
tags: [correction, verification]
---

Before confirming any number that exists in a written source, open the source and
read it. The assistant has confirmed quantities from memory more than once when the
correct numbers were written down and unread, and the confirmation was wrong each time.

**Why:** The seedling order on 2026-05-28 was confirmed two hundred short because the
vendor note went unread, the same shape as earlier from-memory misses on written
figures. Same failure, same cause, more than once.
**How to apply:** Any request to confirm, send, or finalize a number that lives in a
note, an order, or a file gets the source opened and read first. Confirm from the
source, cite it, and never from memory.
```

## Step 5: write the rule and re-seed (on approval only)

When the owner approves a rule, and only then:

1. **Write the file** into the owner's memory corpus, where their `feedback_*.md`
   files live (the directory the engine seeds, `COS_MEMORY_DIR`). Use a `feedback_`
   filename prefix so the loader classifies it correctly.
2. **Re-seed the engine** so it ingests the new rule:

   ```
   python -m cos memory seed
   ```

   Read the summary line. The new file should report as inserted; a re-run should
   report idempotent. If it is rejected, read the reason, fix the file's format, and
   re-seed. Do not work around the contract.

3. **Mark the source records graduated.** In each incident record that fed the rule,
   change `status: logged` to `status: graduated` in the frontmatter, and update its
   line in `INDEX.md` to read `graduated`. A graduated record should also name the
   rule it produced, so the link runs both ways: the rule cites its incidents, the
   incidents cite their rule. Add one line at the end of each graduated record:
   `Graduated to: feedback-read-the-source-before-confirming.`

That is the closed loop. The incident became data, the repeat became a rule, the rule
entered the memory the engine seeds at session start, and the records that justified it
are marked and linked.

## Step 6: escalate rules that keep failing

A graduated rule is still only prose. The engine surfaces it, but a long session or a
fresh context window can still drop it. So watch for the tell: a new incident whose
pattern matches a rule that already graduated. That means the prose rule is not
holding, and the fix is no longer another rule.

When a graduated rule recurs, propose escalating it to an enforcement hook. The
enforcement layer (see [`docs/ENFORCEMENT.md`](../docs/ENFORCEMENT.md)) moves a rule
out of the model's memory and into the harness, where it cannot be forgotten. Some
rules map cleanly to a hook: a banned phrase becomes an `output_lint` rule, an edit
the owner never wants becomes a `protect_surfaces` glob, a runaway becomes a governor
threshold. Others do not, and stay prose. Name the candidate hook in the review and let
the owner decide. The progression is the point: record, repeat, rule, and when the rule
keeps failing, hook.

## What this command must never do

- **Never write a rule the owner did not approve.** Step 4 is propose; step 5 runs
  only on the owner's yes.
- **Never graduate a pattern of one.** A single record is watched, not ruled. Two is
  the floor for a rule.
- **Never claim a re-seed landed without reading the summary line.** The inserted
  count is the proof; a rejected file is not in the engine no matter how good the rule.
- **Never rewrite an incident record's body at review.** You change `status` and add
  the graduation line. The original account of what happened stays as it was captured.
