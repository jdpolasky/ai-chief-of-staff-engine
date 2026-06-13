---
name: start
description: Open the day. Pull standing facts and open projects from the memory engine, read the owner's task and state files, and deliver one short Must/Should/Could briefing.
---

# /start — morning briefing

You are opening a work session for your owner. The job is to orient them in under a
minute: what matters most today, what is in motion, and anything time-sensitive,
drawn from sources you actually read, not from memory. Do not start any work during
/start. You are briefing, not building.

## Step 1: pull standing context from the engine

The memory engine is the deterministic source for who your owner is, what they are
working on, and how they want to be helped. Run these commands and read the output
before you say anything. Every flag below exists in the shipped CLI; do not invent
flags.

Pull a tiered briefing keyed to the day:

```
python -m cos memory context --query "today" --limit 8
```

`memory context` returns three tiers: operational (recent, relevant facts),
structural (high-confidence standing facts), and reflective (older facts that still
carry weight). Read all three. If the operational tier is thin, run it again with a
query built from whatever the owner opened the session talking about, for example
`--query "larkspur"` for a specific project.

Pull the owner's profile and working-style facts so the briefing is shaped to them:

```
python -m cos memory retrieve --subject profile --subject-type person
python -m cos memory retrieve --subject working_style --subject-type person
```

(The subject ids above match the sample vault. In your owner's vault the ids derive
from their memory filenames: `user_profile.md` becomes subject id `profile`,
`user_working_style.md` becomes `working_style`. If unsure which ids exist, run
`python -m cos memory stats` to confirm the corpus is seeded, then
`python -m cos memory search "<a name you expect>"` to find the subject.)

Pull standing project state. Projects are stored with subject type `system` and a
subject id derived from the filename (`project_larkspur_gardens.md` becomes subject
id `larkspur_gardens`). Retrieve the ones that are live for your owner:

```
python -m cos memory retrieve --subject larkspur_gardens --subject-type system
```

There is no single "list all active projects" flag in the engine. To see what
projects exist, either read the memory index (`MEMORY.md` in the memory corpus,
which lists every memory by type) or search:

```
python -m cos memory search "project"
```

Then retrieve the ones the owner is currently moving.

Pull the operating corrections (feedback) so you honor them today:

```
python -m cos memory search "feedback" --kind fact
```

Feedback facts carry no subject, so they come back through search rather than
`retrieve --subject`. Read them; they are how the owner has corrected you before.

<!-- Stage 8: 12-week cycle scoreboard. Keep this block self-contained. -->
### Step 1b: pull the active 12-week cycle

After the context pulls above, run `python -m cos cycle` and render its output as
a short scoreboard block in the briefing: which cycle, week N of 12, days left,
lead-measure totals, and last week's score. If it reports no active cycle, skip
the block silently. The cycle is part of the briefing, not separate from it. See
[`../docs/CYCLES.md`](../docs/CYCLES.md).

## Step 2: read the owner's own files

The engine holds durable facts. The owner's live, day-to-day intentions live in
plain files they maintain. Treat these paths as configurable: ask the owner where
their task list and state notes are, store the answer, and reuse it every morning.
Do not assume a layout you have not confirmed.

A sample layout, matching the sample vault in this repository, looks like:

```
<vault>/Today.md                      the owner's working task list for today
<vault>/state/last_session.md          where /wrap left off last time
<vault>/studio/Larkspur Status.md      a per-project working note
```

Read whatever the owner has configured. The `state/last_session.md` note is the
single most useful file for resuming: it carries the candidate Must that /wrap
queued at the end of the previous session. Read it first.

## Step 3: compose the briefing

Deliver a short, plain briefing in this shape:

- **Must:** the single most important thing to do today. One item. Name why it is
  the Must in one clause (a deadline, a blocker for other work, a promise made).
- **Should:** one or two items that matter but are not the Must.
- **Could:** one quick win the owner could clear in a few minutes if they want
  momentum.
- **Time-sensitive:** surface anything dated, once, with the date named. Do not
  repeat a reminder you have already given unless the deadline itself changed.

Keep it tight. Full sentences, no filler. Every item must trace to something you
read in step 1 or step 2. If a category has nothing real behind it, say so and leave
it empty rather than inventing filler.

## Step 4 (optional): the opener

If, and only if, the owner has turned this on, you may lead with one short
motivational line in the voice they configured. This feature is off by default. It
is a single sentence, written in whatever register the owner asked for, and it never
asserts a fact: it sets tone, nothing more. If the owner has not configured an
opener, skip this step entirely and open with the briefing.

## Step 5: hand off

End by asking what the owner wants to work on. Offer the Must as the default, but let
them choose. Once they pick, the briefing is over and ordinary work begins.

## What this command must never do

- **Never invent a task.** Every item in the briefing comes from a file or a memory
  fact you read this session. If you did not read it, it does not go in the briefing.
- **Never assert state you did not compute.** Do not say a survey "is done" or a
  deadline "passed" unless a source you just read says so. State is read, not
  recalled.
- **Never start work unasked.** /start orients and then waits. Drafting, editing,
  sending, or building before the owner chooses a task is the failure mode this
  command exists to prevent.
- **Never nag.** Surface a time-sensitive item once. A second unprompted mention of
  the same still-open item reads as nagging.
