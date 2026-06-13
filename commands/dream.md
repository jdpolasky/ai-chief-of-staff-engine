---
name: dream
description: Weekly self-tending ritual. Lint the memory corpus, re-read recent session residue, and propose at most three durable patterns the owner accepts or rejects. Propose only; write nothing without a yes.
---

# /dream — the weekly dream run

You are tending the memory corpus so it does not rot. The job is to notice
patterns the owner has not named yet, propose a few, and let the owner accept or
reject each. You propose; the owner commits. Write nothing without a yes. Keep
the whole ritual to one screen.

This runs on a weekly scheduled session, or whenever the owner types /dream.
Staleness is fine: if it has been three weeks, the ritual just catches up on more
residue at once. There is no backlog to fear.

## Step 1: lint the corpus

Run the deterministic checks first, because they are free and certain:

```
python -m cos lint
```

If it prints `corpus clean`, say so in one line and move on. If it lists
findings, triage them: each line is one of index-orphans, frontmatter-malformed,
stale-superseded, duplicate-names, or broken-wikilinks. These are structural, not
matters of judgment, so you can name the fix plainly (relist the file in
MEMORY.md, add the missing frontmatter key, move a SUPERSEDED note out of the
live corpus, resolve a name collision, fix a dangling wikilink). Fixes to the
owner's files are still proposals: name them, do not make them unasked.

## Step 2: read the recent residue

Now read what the week left behind, so your proposals come from evidence, not
invention:

- **State notes.** Read the `last_session.md` note /wrap leaves. It carries the
  most recent wins, open threads, and the candidate Must.
- **Recent episodes.** Run `python -m cos memory search "<a term from this
  week's work>"` to pull recent episode records, or search a couple of project
  names you saw in the state note. Episodes are the session-level arc.
- **The incident logbook, if present.** If the incident logbook is installed
  (`incidents/`, with `commands/incident.md` and `commands/incident-review.md`),
  read its index. A repeated incident shape is exactly the kind of pattern a
  dream run should surface.

Read for repetition and contradiction, not for completeness. You are looking for
three things at most.

## Step 3: propose at most three patterns

Propose no more than three candidate patterns. Fewer is better; zero is a fine
result on a quiet week. Each candidate takes one of three shapes:

- **"You keep doing X."** A recurring correction or move that has earned a
  durable feedback file. Consequence: a new `feedback_*.md`.
- **"These two rules contradict."** Two memories that now disagree.
  Consequence: an edit to one, or a note that supersedes the older.
- **"This memory looks dead."** A note nothing has touched or referenced in a
  long time. Consequence: retire it (move it out of the live corpus).

Write each candidate as a single accept/reject line with its one-line
consequence. For example:

- *You keep trimming my drafts by half. Make it a feedback file?*
  (accept -> new `feedback_trim_first_pass.md`; reject -> nothing)
- *`reference_old_vendor` has not been linked or retrieved in months. Retire it?*
  (accept -> move it out of the live corpus; reject -> nothing)

Do not stack reasoning under each line. The owner reads the line and decides.

## Step 4: act only on acceptance

For each candidate the owner accepts, do the named consequence and then re-seed
so the change reaches retrieval:

```
python -m cos memory seed
```

Writing a new `feedback_*.md` or editing a memory file is a corpus change, so it
needs a re-seed; retiring a note (moving it out of the live corpus) needs one
too, so the dropped fact stops surfacing. For anything the owner rejects, record
nothing. A reject leaves no trace; that is the point of propose/commit.

## The one-screen cap

The entire ritual fits on one screen: the lint result in a line or two, then at
most three accept/reject lines, then a one-line close naming what you wrote. If
you are writing paragraphs, you are over budget. The dream run is a nudge, not a
report.

## What this command must never do

- **Never write a memory file, edit one, or retire one without a yes.** Every
  consequence in step 3 waits for explicit acceptance.
- **Never propose more than three patterns.** If you found more, keep the three
  strongest and let the rest wait for next week.
- **Never invent a pattern to fill the quota.** Three is a ceiling, not a target.
  On a quiet week, report the clean lint and stop.
- **Never treat the lint as truth about meaning.** The lint sees structure
  (orphans, bad frontmatter, dead markers); whether a memory is actually wrong or
  actually dead is your judgment, and judgment is why everything here is
  accept/reject.
