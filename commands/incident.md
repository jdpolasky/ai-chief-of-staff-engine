---
name: incident
description: Capture a failure as a record with no ceremony. Write one incident file to the owner's incidents folder, classify it, append one line to the index, and move on. Analysis happens later, at review.
---

# /incident — capture a failure

Something went wrong. Either the owner named it, or you caught yourself failing. The
job of this command is narrow: write the failure down as data, right now, and stop.
You are not fixing it here, not defending it, not relitigating it. You are recording
it so the system can learn from the pattern later.

The bar is on the floor on purpose. A record takes thirty seconds. The whole point is
that you can capture mid-annoyance, while the failure is fresh, without it becoming a
production. Capture first. Analyze later, at `/incident-review`.

## The one rule that matters

**Write the record straight, even when the owner is venting.** If the owner is
frustrated, the record still gets the real root cause, with no softening and no
defending. Do not argue with the owner inside a record. Do not explain why it
was not really your fault. If the failure was the owner's process, say that plainly
too, without blame. The record is data. It renders no verdict. A record that flatters anyone
is a record that teaches nothing.

## Step 1: write the record file

Write one markdown file to the owner's incidents folder. The shipped location is
`incidents/`; if the owner keeps it elsewhere, use that path. The filename is
`YYYY-MM-DD-<slug>.md`, where the slug is three to six words of what broke, in
kebab-case (for example, `2026-05-28-seedling-order-rederived.md`).

The file's shape:

```markdown
---
date: 2026-05-28
actor: assistant
class: skipped-verification
status: logged
---

# Seedling order re-derived from memory

## What happened
Two to four plain sentences. What the failure was, in the order it happened. No
preamble, no apology, no spin. Just what occurred.

## Root cause
The cause that actually produced the failure, named in one or two sentences, even
when it makes the assistant look bad. If the real cause is "I trusted memory instead of reading the
source," write that. If it is "the owner's note was ambiguous," write that.

## Cost
One line. Time, money, or trust. What did this failure actually cost?

## Rule candidate
The rule that would have prevented this, in one sentence, or "none yet" if no clean
rule is obvious. This is only a candidate; `/incident-review` decides whether it
graduates into a committed rule.
```

### The frontmatter fields

- `date`: the day the failure happened, `YYYY-MM-DD`.
- `actor`: who failed. One of `assistant`, `owner`, or `both`. Most
  records will be `assistant`; the taxonomy is not here to protect anyone.
- `class`: the classification. One of the six below. Pick the closest single fit.
- `status`: always `logged` at capture time. `/incident-review` changes it to
  `graduated` when a record's pattern becomes a rule.

### The classification taxonomy

Keep it small. Six classes, pick the closest one. A taxonomy that needs a decision
tree does not get used.

- `wrong-assumption`: acted on something assumed instead of confirmed, and the
  assumption was wrong.
- `skipped-verification`: answered or acted from memory or guess when a source was
  available and unread.
- `scope-creep`: did more than was asked, or drifted off the actual request.
- `instruction-miss`: missed or ignored a standing instruction or stated preference.
- `tooling-gap`: the tool, command, or data needed did not exist or did not work,
  and that gap caused the failure.
- `owner-process`: the failure traces to the owner's own workflow (an ambiguous
  note, a missing file, a decision not yet made). Logged without blame, because the
  fix is a process fix.

If a record could fit two classes, pick the one closest to the root cause rather
than to the symptom. A wrong answer from an unread note files as
`skipped-verification`, because the source existed and went unread.

## Step 2: append one line to the index

Open `incidents/INDEX.md` and append exactly one line to the catalog, in this shape:

```
- 2026-05-28 · [Seedling order re-derived](2026-05-28-seedling-order-rederived.md) · skipped-verification · logged
```

The index is lean by contract: one line per record, never a narrative. Date, linked
title, class, status. Nothing else. The records hold the detail; the index is the
catalog you scan at review.

## Step 3: stop

That is the whole command. Confirm the file and the index line in one sentence, then
stop. Do not propose a fix. Do not start the analysis. The pattern work happens at
`/incident-review`, after enough records exist to see a shape. Capturing the failure
is the win; resist the pull to solve it now.

## Worked example

The owner, Maya, asked the assistant to confirm the seedling order for the Larkspur
meadow before she sent it to the nursery. The assistant re-derived the quantities from
what it remembered of an earlier conversation instead of opening the vendor note Maya
had written, and the order came back wrong by two hundred seedlings. Here is the
record it wrote:

```markdown
---
date: 2026-05-28
actor: assistant
class: skipped-verification
status: logged
---

# Seedling order re-derived from memory

## What happened
Maya asked me to confirm the meadow seedling order before she sent it to the nursery.
I re-derived the quantities from memory of an earlier conversation rather than opening
the vendor note she had written. The order I confirmed was short by two hundred
seedlings against the note.

## Root cause
I trusted my memory of the numbers instead of reading the source that existed. The
vendor note had the correct quantities; I never opened it.

## Cost
Two hundred seedlings short on a time-sensitive nursery order, and a dent in Maya's
trust that she can hand me a confirmation without re-checking it herself.

## Rule candidate
Before confirming any number that exists in a written source, open the source and read
it; never confirm a quantity from memory.
```

Notice what the record does not do: it does not say the conversation was confusing, it
does not say Maya should have reminded it about the note, it does not hedge. It names
the real cause and the real cost, then stops. That is the standard for every record.
