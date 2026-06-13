# Self-tending

Memory that nobody tends rots quietly. The index drifts out of step with the
files. Two rules end up contradicting each other and nothing flags it. A note
gets marked done but never moved, so it keeps seeding into every briefing. Dead
notes pile up at the edges. None of this is loud. It is slow entropy, and the
usual fix is discipline: remember to prune, remember to reconcile, remember to
check the index. Discipline is exactly the thing this system exists to not
require of you.

So the fix is a ritual, not discipline. Two of them run on a schedule and tend
the corpus for you. One is deterministic and certain (the corpus lint); one is
judgment and can be wrong (the dream run), which is why it proposes instead of
acting. This is design principle ten made real: the system tends itself, and it
surfaces its own silence.

## What the lint catches

The corpus lint is `python -m cos lint`. It reads your memory files and runs five
structural checks. It never changes anything; it only reports. In plain words, the
five things it catches:

- **Orphans, both directions.** A memory file that exists but is missing from
  your index, and an index line that points at a file that is no longer there.
  Either way the index has drifted from the files, and the lint names which.
- **Malformed frontmatter.** A memory file missing one of the three keys every
  memory needs (its name, its one-line description, its type), or one whose
  frontmatter is broken enough that the loader cannot read it. These are the
  files that would silently fail to seed.
- **Stale done-notes.** A note whose opening lines say SUPERSEDED or RESOLVED but
  that still sits in your live corpus. The marker means the note's job is over;
  if it stays, it keeps feeding retrieval with something you already retired.
- **Duplicate names.** Two files claiming the same name. The system keys
  retrieval and cross-links on the name, so a collision is ambiguous and one of
  them needs renaming.
- **Broken cross-links.** A `[[name]]` link pointing at a name that no file
  declares. The link is dangling; it goes nowhere.

When the lint finds nothing it prints `corpus clean` and exits quietly. When it
finds something it prints one line per finding and exits with an error code, so a
scheduled run can notice. Silence on success, loud on findings.

## What the dream run does, and why it proposes

The dream run is the weekly ritual, `/dream`. Where the lint checks structure,
the dream run reads meaning. It runs the lint first, then re-reads the residue of
your recent sessions (the state note your last wrap left, recent session records,
the incident log if you have one) and looks for patterns you have not named yet.
Then it proposes at most three:

- *You keep doing X*, a correction you keep giving that has earned a standing
  rule.
- *These two rules contradict*, two memories that now disagree.
- *This memory looks dead*, a note nothing has touched or referenced in a long
  time.

Each proposal comes as a single accept-or-reject line with its one consequence:
a new memory file, an edit, or a retirement. If you accept, it writes the file
and re-seeds. If you reject, it records nothing and the proposal leaves no trace.

It proposes instead of acting for the same reason the rest of the system splits
propose-rights from commit-rights. The dream run is judgment, and judgment about
your own memory is exactly the kind of thing you want to hold the final say on. A
ritual that quietly rewrote your corpus on a guess would be worse than no ritual:
you would stop trusting the corpus. A ritual that proposes and waits stays
trustworthy, because every change to your memory passed through your yes.

## Why silence on success matters

The lint is built to say nothing when the corpus is clean, and the dream run is
built to fit on one screen with at most three proposals. That is deliberate. The
whole value of a self-tending ritual is that you only hear from it when there is
something to hear. A check that printed a long all-clear report every week would
train you to skim past it, and the one week it found something real would scroll
by with the rest. Silence on success keeps the signal sharp: when the ritual
speaks, it is because something actually drifted.

## How often

Weekly is plenty. The corpus accumulates entropy slowly, so a weekly pass catches
drift long before it matters. If you miss a week or three, nothing breaks: the
rituals are catch-up by design. The next run just reads more residue at once and
the lint reports whatever has accumulated. There is no backlog that compounds,
because the lint recomputes the whole picture every time and the dream run only
ever proposes the few strongest patterns it sees today.

## Honest limits

The lint sees structure, not truth. It can tell you a note is marked RESOLVED and
still in the live corpus, but it cannot tell you whether a note that looks fine is
actually saying something wrong. It checks that a name is unique and an index is
in sync; it does not check that what a memory claims is correct. Structural
cleanliness is necessary, not sufficient.

The dream run is judgment, and judgment can be wrong. It might propose retiring a
note you still want, or read a coincidence as a pattern, or miss the thing that
actually mattered this week. That is precisely why everything it does is
accept/reject: the ritual is allowed to be wrong because you are the one who
commits. Read its proposals the way you would read a sharp assistant's hunch,
worth considering and not worth rubber-stamping. Approve the ones that ring true,
reject the rest, and the corpus stays both clean and yours.

For the deterministic guarantees underneath all this (validated writes,
idempotent seeding, durable history), see [`../README.md`](../README.md). For the
behavioral rules that keep the judgment honest, see
[`OPERATING-RULES.md`](OPERATING-RULES.md).
