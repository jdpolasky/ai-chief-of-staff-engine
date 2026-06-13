# Capability registry

An assistant with many tools keeps re-learning the same lesson: which tool actually
works for which job, and which approaches are dead ends. It tries the obvious route,
the route fails, it falls back, the fallback works, and then next session it has no
memory of any of that and tries the failing route again. Each re-discovery costs a
real failed attempt. The lesson was learned and then thrown away.

The capability registry is where those lessons live so they are not thrown away. It is
a small owner-curated file the assistant reads **before** it picks a tool for a class
of task. It does not run anything and it does not pick the tool for you; it is routing
memory the assistant consults the way a person consults a note that says "last time,
the fast way did not work; use the other way."

## What it holds

The registry (`capability/registry.json`) is a list of task classes. Each entry holds
four things:

- **best route:** the tool or approach to reach for first for this class of task.
- **fallback ladder:** an ordered list of what to try when the best route does not fit.
  The assistant walks it in order rather than guessing.
- **dead ends:** routes that already failed, each with a one-line reason and a retest
  date.
- **notes:** anything else worth knowing before routing this class.

Look one up from the command line:

```
python -m cos capability authenticated-web-work
```

or list the classes:

```
python -m cos capability --list
```

The lookup is read-only. It prints the best route, the ladder, and the dead ends, and
exits. The command `commands/route.md` tells the assistant to run it before starting a
matching task.

## A dead end is a fact with an expiry

The least obvious idea here is the retest date on each dead end. A naive registry would
record "this route does not work" and avoid it forever. But tools improve. A route that
failed in June may work by October because the tool got a feature, or a site changed,
or a bug was fixed. A permanent "never" would lock in a failure that is no longer true.

So every dead end carries a **retest date**: the day it becomes worth trying once more.
Before that date, the lookup shows the dead end flagged `[avoid]` and the assistant does
not retry it. On or after that date, the lookup shows it flagged `[RETEST]` instead of
hiding it: the route is due for a single retry, and whatever the assistant learns
becomes a proposed update. A dead end is not a permanent verdict; it is a fact with an
expiry.

## Who writes it

The registry is owner-curated. The assistant holds propose-rights; the owner holds
commit-rights. The assistant never edits `registry.json` silently. When a route fails in
practice, or a retest resolves, the assistant proposes the change in plain language (a
new best route, a new dead end with a retest date, a cleared retest) and waits for the
owner's yes. Then the owner commits it.

The registry grows **only from observed failure**, never from speculation. This is
design principle 6 from the README, "grow only from observed failure," applied to
routing. A dead end the assistant did not actually hit is noise: it would steer routing
away from a route nobody has shown to be bad. The registry earns each entry the hard
way, the same way the operating rules did.

## How it pairs with the incident logbook

The incident logbook (`docs/LOGBOOK.md`, `commands/incident.md`) records the times
something broke: a tooling gap, a failed approach, a surprise. The capability registry
records how to route around those breaks next time. They are two halves of the same
loop. A tooling-gap incident, the kind where the assistant reached for a tool and it did
not work, is exactly the kind of failure that should also become a registry entry: the
incident is the record that it broke, and the registry entry is the lesson that keeps it
from breaking the same way twice. When you log such an incident, ask whether the routing
lesson belongs in the registry too.

## Adapt it to your own tools

The shipped registry seeds five generic task classes (vault file operations, public web
reads, authenticated web work, long-document generation, structured data pulls) with
neutral descriptions, no tool brand names. They are a starting shape, not a
prescription. Edit `capability/registry.json` so the routes name the tools you actually
use, and so the dead ends record the failures you have actually seen. The verification
is simple: run `python -m cos capability --list` and one lookup, and confirm the output
reads true for your setup.
