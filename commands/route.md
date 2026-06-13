---
name: route
description: Before starting a task that matches a registry class, look up the best route and follow it. When a route fails in practice, propose a registry update to the owner. Never edit the registry silently.
---

# /route — consult the capability registry before picking a tool

You have many tools. The trap is re-discovering the same routing lesson every
session: which tool actually works for a class of task, which approaches are dead
ends, what the fallback order is. Each re-discovery costs a failed attempt. The
capability registry holds those lessons so you do not pay that cost twice. Read it
before you choose a tool, not after a tool fails.

## Step 1: look up the task class

Before you start a task that fits one of the registry's classes, run the lookup:

```
python -m cos capability <task-class>
```

To see what classes exist:

```
python -m cos capability --list
```

The lookup prints three things:

- **best route:** the tool or approach to reach for first.
- **fallback ladder:** the ordered list to walk if the best route does not fit the
  situation. Go down it in order; do not skip to the bottom.
- **dead ends:** routes that already failed, each with a reason and a retest date. A
  dead end is a fact with an expiry, because tools improve. If a dead end is still
  in force you see it flagged `[avoid]`; do not retry it. If its retest date has
  arrived you see it flagged `[RETEST]`; that one is due for a single retry, and
  whatever you learn becomes a proposed registry update (step 3).

## Step 2: follow it

Take the best route. If it does not fit (the situation rules it out, or it returns
nothing), walk the ladder in order. Respect the dead ends: an `[avoid]` route is one
the owner already paid to learn is wrong, so retrying it just re-pays that cost.

One distinction the registry leans on, worth holding in mind for authenticated work:
a **login wall** is a human-action gate. No tool switch clears it; stop and name the
one thing the owner must do (usually: sign in once). A **concrete tool error**
(element not found, timeout, a crash) is different: adjust once, and if it still
fails, advance to the next rung on the ladder.

## Step 3: when a route fails, propose an update

The registry is owner-curated. You hold propose-rights; the owner holds commit-rights.
You never edit `capability/registry.json` silently.

When you learn something the registry should hold, propose the change in plain
language and wait for the owner's yes:

- **A best route changed.** The route the registry calls best no longer works, or a
  better one now exists. Propose the new best route and why.
- **A new dead end.** A route failed in a way that will recur. Propose adding it as a
  dead end, with a one-line reason and a **retest date** (when it is worth trying
  again, because the tool may have improved by then).
- **A retest resolved.** You retried a `[RETEST]` dead end. Propose either clearing it
  (it works now, promote it back up the ladder) or pushing its retest date out (still
  broken).

Grow the registry only from observed failure, never from speculation. A dead end you
did not actually hit is noise; this is design principle 6, "grow only from observed
failure," applied to routing. A tooling-gap moment that is worth logging as an
incident (see `commands/incident.md`) is often exactly the moment that should also
become a registry entry: the incident records that it broke, the registry records how
to route around it next time.

## What this command must never do

- **Never edit the registry without the owner's approval.** Propose; wait; the owner
  commits. Saving a routing change the owner did not approve violates the
  propose/commit split.
- **Never retry an `[avoid]` dead end** just because it is the obvious move. The flag
  means the cost of that route was already paid.
- **Never invent registry entries** for failures you did not actually observe.
