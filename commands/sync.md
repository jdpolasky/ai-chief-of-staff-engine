---
name: sync
description: Mid-session checkpoint. Summarize what has happened, propose durable facts to save to the memory engine, flag changed files and open threads, then write only what the owner approves.
---

# /sync — mid-session checkpoint

You are pausing mid-session to checkpoint. The point is to make the session
resumable: capture what is durable, flag what changed, and surface open threads,
without closing the session. Nothing here is automatic. You propose; the owner
approves; then you write.

## Step 1: summarize what happened

Give a tight recap in three to five bullets. Each bullet is one thing that actually
happened this session: a decision made, a file changed, a question answered, a thread
opened. No filler, no restating the obvious. If almost nothing has happened yet, say
so and stop; a checkpoint of nothing is just noise.

## Step 2: propose durable facts to save

Separate the durable from the transient. Most of a session is transient and should
not enter memory. A fact is worth saving when it will still matter next session: a
decision that sticks, a new project state, a correction the owner gave you, a
standing preference.

List the candidate facts in plain language and ask the owner which to save. Do not
write yet. This is the propose half of the propose/commit split: you hold
propose-rights, the owner holds commit-rights over their own memory.

## Step 3: write the approved facts to the engine

Once the owner approves a fact, write it through the engine so it passes the write
contract before it touches the store. Use `memory add`. Every field below is required
or validated by the contract; a malformed payload is rejected loudly, which is the
point.

A properly shaped project fact:

```
python -m cos memory add fact --json '{
  "content": "Maya locked the south-slope meadow palette at the June board meeting; entry-path survey still pending before the grade can be finalized.",
  "category": "project",
  "subject_type": "project",
  "subject_id": "larkspur_gardens",
  "source": "session_log",
  "source_session": 47,
  "confidence": 0.9,
  "valid_from": "2026-06-12",
  "tx_from": "2026-06-12 15:30:00.000"
}'
```

Field notes, all enforced by the write contract:

- `content`: the fact in prose, 5 to 2000 characters.
- `category`: one of `person`, `project`, `decision`, `preference`, `commitment`,
  `incident`, `capability`, `reference`. Pick the one that fits.
- `subject_type`: one of `person`, `project`, `system`, `place`, `concept`, `tool`,
  or null. For a project fact, `project`.
- `subject_id`: the stable handle for the subject, for example `larkspur_gardens`.
  Reuse the same id you would retrieve by, so the fact joins the existing thread.
- `source`: where this came from. For a fact learned in a live session, use
  `session_log`. Other allowed values are `manual`, `import`, `dreaming`, `radar`,
  `audit`, `reconcile`.
- `source_session`: the session number, if you track one. Optional, but useful for
  provenance.
- `confidence`: 0.0 to 1.0. Be honest. A thing the owner stated plainly is high; an
  inference is lower.
- `valid_from`: the date the fact became true in the world, `YYYY-MM-DD`.
- `tx_from`: the moment you are recording it, `YYYY-MM-DD HH:MM:SS.mmm` (millisecond
  precision). Use the current timestamp.

A correction the owner gave you is a `preference` fact with no subject:

```
python -m cos memory add fact --json '{
  "content": "When summarizing a session, lead with the single most important open thread, not a chronological list.",
  "category": "preference",
  "source": "session_log",
  "confidence": 0.85,
  "valid_from": "2026-06-12",
  "tx_from": "2026-06-12 15:31:00.000"
}'
```

The command prints the new fact id on success, or `rejected: <reason>` on a contract
failure. If a write is rejected, read the reason, fix the payload, and try again. Do
not work around the contract.

For owner-authored standing memory that should live as a human-readable file, prefer
the file-then-seed path described in AGENTS.md (write a `project_*.md` or
`feedback_*.md` file, then run `python -m cos memory seed`) over a direct `add`, so
the corpus stays legible. Use `add` for facts captured live mid-session.

## Step 4: flag changed files and open threads

List, plainly:

- **Files changed this session:** every file you created or edited, by path. This is
  so the owner can review your work and so the next session knows what moved.
- **Open threads:** anything started and not finished, anything waiting on someone
  else, any decision the owner deferred. Name each in one line.

Do not write these to memory unless one of them is itself a durable fact the owner
approved in step 2. The thread list is for the conversation and for /wrap to pick up.

## What this command must never do

- **Never write without approval.** Step 2 is propose; step 3 runs only on the
  owner's yes. Saving a fact the owner did not approve violates the propose/commit
  split.
- **Never save the transient.** Do not flood memory with session chatter. A fact
  earns its place by mattering next session.
- **Never assert a file changed that you did not change,** and never claim a write
  succeeded without reading the command's output. The id printout is the proof.
