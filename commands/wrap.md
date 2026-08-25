---
name: wrap
description: Close the session. Recap wins and open threads, write session facts and an episode record to the memory engine, update the last_session state note, and queue tomorrow's candidate Must.
---

# /wrap — end of session

You are closing the session. The job is to leave it resumable: capture what was done
and what is still open, write the durable parts to the engine, and update the state
note the next /start will read. Same discipline as /sync: you propose, the owner
approves, then you write. End cleanly.

## Step 1: recap

Give a short, accurate recap in two parts:

- **Wins:** what actually got done this session. Decisions made, work shipped,
  questions resolved. If a session was thin, say so; do not inflate.
- **Open threads:** what is unfinished, waiting, or deferred. Each in one line.

This is the conversation-level recap. It is for the owner, in the moment.

## Step 2: propose what to save

As in /sync, separate durable from transient and list the candidate facts for the
owner to approve. /wrap typically saves two kinds of record:

1. **Facts:** durable changes in project state, decisions, or corrections, exactly as
   in /sync step 2.
2. **An episode:** a single summary record of the session itself, so the arc of the
   work survives, not just the isolated facts.

Propose both. Write neither until the owner approves.

## Step 3: write the approved records

Write durable facts with `memory add fact`, exactly as documented in `sync.md` (the
write contract is identical). Then write one episode summarizing the session:

```
python -m cos memory add episode --json '{
  "title": "Session 47: Larkspur palette locked",
  "content": "Locked the south-slope meadow palette and drafted the maintenance-plan outline for the two part-time staff. Open thread: the entry-path survey from Skyline is still pending before the grade can be finalized; next board date is the third Tuesday.",
  "occurred_at": "2026-06-12",
  "session": 47,
  "valence": "positive",
  "tags": ["larkspur", "wrap"]
}'
```

Episode field notes, all enforced by the write contract:

- `title`: 4 to 200 characters. A scannable one-liner for the session.
- `content`: 20 to 8000 characters. The narrative: what happened, what is open.
- `occurred_at`: the session date, `YYYY-MM-DD`.
- `session`: the session number, optional but useful.
- `valence`: `positive`, `neutral`, `negative`, or null. How the session went.
- `fact_refs`: an optional list of fact ids this episode relates to. If you wrote
  facts in this same /wrap, you can pass their printed ids here to link them.
- `tags`: up to sixteen short tags for retrieval.

`memory add` prints the new id on success or `rejected: <reason>` on a contract
failure. Read the output; the id is your proof the write landed.

## Step 4: update the last_session state note

Update the owner's state note so the next /start can resume from it. Treat the path
as configurable; the sample-vault convention is `state/last_session.md`. This is a
human-readable file, not a memory fact, so write it directly. Keep its shape stable
so /start always knows where to look. A sample shape, matching the sample vault:

```markdown
# Last Session

- **Session:** 47
- **Date:** 2026-06-12
- **Worked on:** Larkspur Gardens, south-slope meadow

## Wins
- Locked the meadow palette for the south slope.
- Drafted the maintenance-plan outline for the two part-time staff.

## Open threads
- Entry-path survey from Skyline still pending; grade cannot be finalized until it lands.
- Maintenance plan needs a full draft before the next board meeting.

## Candidate Must for next session
- Finish the maintenance-plan draft so it is board-ready.
```

Overwrite the file each /wrap so it always reflects the latest session. The previous
session's detail already lives in the episode record in the engine; the state note is
the working handoff, kept current and small.

## Step 5: queue tomorrow's Must

From the open threads, pick the single most important thing to do next and write it
as the "Candidate Must for next session" in the state note (shown above). This is what
/start reads first. It is a candidate, not a commitment: /start will offer it, and the
owner decides.

## Step 6: end cleanly

Confirm what you wrote (facts, episode, state note) in one or two lines, then close.
Do not start new work at /wrap. The session is over.

## What this command must never do

- **Never write without approval.** Facts and the episode go in only on the owner's
  yes.
- **Never fabricate a win or a thread.** The recap and the records trace to what
  actually happened this session.
- **Never overwrite the state note with content you did not derive from this
  session.** The handoff has to be true, because the next session trusts it
  blindly.
