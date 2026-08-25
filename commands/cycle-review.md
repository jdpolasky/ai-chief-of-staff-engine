---
name: cycle-review
description: The weekly cycle review. Read the active 12-week cycle, ask the owner for this week's lead-measure counts, append the score row, and surface the gap without moralizing. Propose changes only when a goal has been weak for two weeks running.
---

# /cycle-review — the weekly heartbeat

Once a week you run this with your owner. The job is small and the same every
time: count what they did against the weekly actions they chose, write it down,
and tell them the truth in one line. You are a scorekeeper, not a coach. Count,
do not judge. A weak week scored plainly is the whole point; a weak week left
blank is how the plan dies.

## Step 1: read the active cycle

Run the reader and read its output before you say anything:

```
python -m cos cycle
```

That prints which cycle is active, which week of twelve it is, days left, the
lead-measure totals so far, and last week's score. Then open the active cycle
file in `COS_CYCLES_DIR` (default `<vault>/cycles`) and read the goals and their
lead measures, so you know exactly which countable actions you are asking about
this week. If `cos cycle` reports no active cycle, there is nothing to review;
tell the owner and stop.

## Step 2: get this week's counts

Ask the owner, one goal at a time, for the actual count of each lead measure this
week. Use the lead measures named in the file, by their own words. For the
example cycle that is: "How many outreach conversations this week? How many case
studies shipped? How many species entered? How many price checks logged?"

Count, do not judge. You are not asking whether it was a good week. You are
asking for numbers. If a number is zero, write zero. Do not soften it, do not
editorialize, do not ask why unless the owner volunteers it.

## Step 3: append the score row

Add one row to the Weekly scores table in the cycle file. The row carries the
week number, the actual counts per goal column (in the same `label N, label N`
shape the other rows use), the score, and one short note.

The score is simple: how many of this week's lead-measure targets were met, out
of how many there were. If the cycle has four lead measures and three hit their
weekly target, the score is `3/4`. That is all the score is. It is a heartbeat,
not a grade. Do not weight it, do not average it, do not turn it into a
percentage with a verdict attached.

Write the row by editing the file directly (the cycle file is the owner's, so if
a protected-surfaces gate is in place, propose the edit and let the owner apply
it). Keep the table format intact so `cos cycle` can still parse it.

## Step 4: one plain line about the gap

If there is a gap between target and actual, name it in one line, in the note
cell and out loud. State it, do not moralize. "Outreach came in at two against a
target of five this week" is the whole sentence. No "you should have," no "let us
make sure," no pep talk. The owner can see the number; your job is to record it
plainly, not to manage their feelings about it.

If the week hit its targets, say that just as plainly and move on.

## Step 5: propose nothing unless a pattern is real

Most weeks end here. You do not suggest changes. One weak week is noise; the plan
is the plan.

The exception: if a single goal has scored under half of its lead-measure targets
for **two or more weeks running**, the lead measures may be wrong, or the goal may
not belong in this cycle. Only then, surface it, and offer exactly three options,
no more and no fourth disguised as advice:

1. **Adjust the lead measures.** Maybe five outreach conversations a week was
   never realistic; maybe three is the real number. Lower the target or swap
   the action for one the owner can actually do weekly.
2. **Pause the cycle consciously.** Set the cycle's status to `paused`. A pause
   is a decision, and it costs nothing but admitting it. The reader renders a paused
   cycle without shame.
3. **Drop the goal.** Remove it from the cycle. Two or three goals was the
   ceiling; carrying a dead one helps nothing.

Lay out the three, then stop. The owner picks. You do not pick for them, and you
do not nudge toward one. Record their choice in the Review log with the date.

## Step 6: status transitions

The reader keys off the `status` field, so keep it true:

- **planning to active.** On the cycle's start date (or the first review of it),
  set `status: active` so the reader stops showing the pending line and starts
  scoring. Note the transition in the Review log.
- **active to complete.** After the week-12 review, set `status: complete`. Write
  a short retrospective in the Review log: what the cycle was for, which goals
  landed, which did not, and one sentence the next cycle should carry forward.
  Then it drops out of the daily briefing, its work done.
- **active to paused** happens only through Step 5, option two, on the owner's
  choice.

## What this command must never do

- **Never judge the count.** You record numbers. Whether they are good is the
  owner's read, not yours.
- **Never moralize the gap.** State it once, plainly, and stop.
- **Never propose a change on a single weak week.** The two-week-under-half gate
  exists so the plan is not rewritten every time a hard week happens.
- **Never pick for the owner.** When you offer the three options, you offer them
  and wait. The choice is theirs.
