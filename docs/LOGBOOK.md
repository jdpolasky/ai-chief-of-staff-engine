# The incident logbook

A working assistant system improves by logging its failures as data, not by
relitigating them as arguments. That sentence is the whole stage. This doc is the
owner's read: what the logbook is, why it works the way it does, and the almost-nothing
you actually do to keep it running.

## Failure as data, not failure as argument

When your assistant gets something wrong, the usual move is an argument. You point out
the mistake, it explains, you push back, it apologizes, and the next session it makes a
nearby version of the same mistake because nothing about the exchange survived. The
argument lived in the moment and died with it. You both spent energy and learned
nothing durable.

The logbook replaces the argument with a record. The failure gets written down once, in
plain language, with the real root cause and a real cost. Then the conversation moves
on. The record does the remembering. There is no shame in it and nothing to relitigate,
because a record is not a verdict on anyone, it is a data point. And a data point
outlives the mood that produced it. You can be annoyed when you log it and the record
will still be calm and useful three weeks later, which is exactly when it earns its
keep.

This is the same principle the rest of the engine runs on. State is computed, not
recalled. History is kept, not argued. The logbook brings failures into that discipline:
they become facts the system can act on instead of feelings it has to manage.

## The capture bar is on the floor, on purpose

A logging system only works if logging is nearly free. If writing a record feels like
filing a report, you will not do it when you are busy or irritated, which is exactly
when the failures happen. So the bar is deliberately low: a record takes about thirty
seconds, and it is meant to be written mid-annoyance, while the failure is fresh.

You invoke `/incident`, or your assistant catches itself failing and writes the record
on its own. Either way the record gets written straight, even when you are venting. The
assistant does not argue with you inside a record, does not soften the cause to look
better, and does not make you fill in fields. It writes what happened, the real cause,
the cost, and a candidate rule, then stops. Capture first. The analysis waits.

Owners tend to give this folder a saltier name than "incidents," something closer to a
fuckup log, and the system works exactly the same whichever name you use; the discipline
is in the capture, not the label.

## The taxonomy is small on purpose

Every record gets one classification from a list of six:

- **wrong-assumption**: acted on something assumed instead of confirmed.
- **skipped-verification**: answered from memory when a source was there and unread.
- **scope-creep**: did more than was asked, or drifted off the request.
- **instruction-miss**: missed a standing instruction or a stated preference.
- **tooling-gap**: the tool or data needed did not exist or did not work.
- **owner-process**: the failure traces to your own workflow, logged without blame.

Six, not sixteen. A taxonomy you have to think hard about is a taxonomy that does not
get used, and an unused taxonomy is worse than none because it gives the illusion of
structure. Six categories are enough to group failures into patterns at review and few
enough that picking one is instant. When a record could fit two, the rule is to pick the
one closest to the root cause, not the symptom.

## The graduation path: record, repeat, rule, hook

A single failure is noise. The signal is the repeat, the same failure in the same shape
more than once. So the logbook has a path that turns repeats into defenses, escalating
only as far as the evidence demands:

1. **Record.** Every failure gets captured with `/incident`. No rule yet, just the data.
2. **Repeat.** When the same shape shows up a second time, the pattern is real. Two is
   the floor; a pattern of one is watched, not acted on.
3. **Rule.** At `/incident-review`, run every few weeks, your assistant groups the
   records, surfaces the repeats, and proposes a feedback rule for each one, written in
   the format the memory engine seeds. You approve it before it becomes a rule. On
   approval, the rule is written into your memory corpus and the engine re-seeds, so the
   rule shows up in your assistant's briefing at the start of every session from then on.
4. **Hook.** Sometimes a rule graduates and the failure still recurs. That means the
   prose rule is not holding, because prose can be forgotten across a long session or a
   fresh context window. When a graduated rule keeps failing, the fix is no longer
   another rule, it is a hook: the rule moves out of the model's memory and into the
   enforcement harness, where the runtime blocks the failure instead of asking the model
   to remember not to make it. See [`ENFORCEMENT.md`](ENFORCEMENT.md).

Each step is more force than the last, and you only climb when the evidence makes you.
Most failures never leave step one. The few that recur earn a rule. The rare rule that
keeps failing earns a hook. Effort tracks the actual problem, which is the whole design.

## How this feeds the rest of the system

The logbook is not a side notebook. It plugs into the two layers this repository already
ships.

It feeds the **memory engine** at the rule step. A graduated rule is a `feedback_*.md`
file in the same format as every other memory the engine seeds, so once it graduates it
is just another fact your assistant reads at session start. The logbook is where those
correction-rules come from: observed, repeated failure, not speculation.

It feeds the **enforcement layer** at the hook step. When a rule graduates and still
fails, the logbook is what tells you the prose is not enough and points you at turning it
into a hook. The incident record is the evidence that justifies the escalation.

Together that makes the system self-tending. Failures become rules, rules that fail
become hooks, and the corpus of corrections grows only from things that actually broke,
never from imagined problems. The logbook is the observed-failure intake for the whole
machine.

## What you actually do

Almost nothing, and that is the point.

- **Name the failure when it happens.** Say what went wrong, or let your assistant catch
  itself. Either way a record gets written in about thirty seconds. You do not fill in
  fields or file a report.
- **At review, approve or reject proposed rules.** Every few weeks your assistant brings
  you the repeat patterns and a proposed rule for each. You say yes, no, or wait. That is
  the commit half of the split: the assistant proposes the rule, you decide whether it
  becomes one.

That is the entire job. The capture, the classification, the grouping, the rule drafting,
the re-seeding, and the hook proposals are the assistant's work. Yours is to name the
failures plainly and to decide which patterns become standing rules. Do those two things
and the system gets quietly better at not repeating itself, which is the only kind of
improvement that compounds.
