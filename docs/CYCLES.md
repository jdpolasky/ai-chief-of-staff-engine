# 12-week cycles

Most annual plans die the same way. You write one in January, full of ambition,
and by March you cannot remember what was in it. The plan was real. The problem
is that a year is too far away to feel and too vague to act on. "Grow the
business this year" does not tell you what to do on a Tuesday in April. So the
plan sits in a file, and the year happens to you instead of the other way around.

Twelve weeks fixes both halves of that. A quarter is close enough to feel: the
end is in sight from the start, so the work stays urgent. And it is long enough to
matter: you can move something real in twelve weeks, not just clear a to-do list.
A year's ambition does not shrink, it just gets carried twelve weeks at a time, in
a plan close enough that you act on it.

## Lead measures, not lag measures

This is the one idea that makes a cycle work. A lag measure is the result you
want: land two clients, ship the product, lose the weight. You do not control it
directly, and by the time the number moves it is too late to change anything. A
lead measure is the action you control that drives the result: have five outreach
conversations this week, write one section a day, walk every morning. You can do a
lead measure on purpose, this week, whether or not the result has arrived yet.

A cycle scores the lead measures, not the lag measures. You cannot make a client
sign. You can have the five conversations. So the plan asks for the five
conversations, every week, and trusts that the signings follow, or it tells you
early that five conversations was the wrong action and you need a different one.
The result is the point; the lead measure is the thing you can actually do about
it.

## The weekly score is a heartbeat, not a grade

Once a week you count what you did against the weekly actions you chose, and you
write down a simple score: how many lead measures hit their target, out of how
many there were. Three of four is `3/4`. That is the whole score. It is not a
performance review and it carries no verdict. It is a heartbeat: proof the cycle
is still alive and an honest read of how the week went.

The discipline that matters is scoring every week, including the bad ones,
especially the bad ones. A weak week scored `1/4` with one plain line about what
got in the way is worth more than a strong week left blank, because the blank week
is where the plan starts dying. The score is not there to make you feel good or
bad. It is there so the plan keeps breathing.

## Pausing is a move, not a failure

Sometimes a cycle stops fitting. A project blows up, life changes, the goals were
wrong. You have two ways to stop a cycle. One is to quietly stop scoring it and
let it fade, and three weeks later you have a dead plan and a vague guilt about
it. The other is to set its status to `paused` on purpose.

A paused cycle costs nothing but honesty. The reader shows it as paused, plainly,
with no shame language, because choosing to pause is a decision and decisions are
allowed. A paused cycle is a plan you stopped on purpose; a quietly abandoned one
is amnesia wearing a plan's clothes. The difference is whether you decided. The
pause is how you decide.

## How a cycle reaches you each morning

A plan that lives in a file you have to remember to open is a plan you will
forget. So the cycle renders itself into the daily briefing instead. The reader is
a small command:

```
python -m cos cycle
```

It finds the active cycle, works out which week of twelve you are in and how many
days are left, sums your lead-measure counts so far, and shows last week's score
and note. The session-loop `/start` command (see [`../commands/start.md`](../commands/start.md))
runs it during the morning briefing and folds its output in as a scoreboard
block, after the standing-context and task pulls. So the plan you wrote three
weeks ago greets you this morning without you remembering it exists. The system
carries the plan, not your memory. That is the entire point.

The reader is read-only and calm by design. No active cycle is a one-line note,
not an error: not running a cycle is a fine state to be in. A cycle in planning
shows when it starts. A paused cycle shows as paused. Only a genuinely broken
cycle file (bad frontmatter, an unparseable score table) makes it complain, and
then it complains loudly, because a plan you cannot read is a plan you cannot
trust.

## How to start your first cycle

1. **Copy the template.** `cycles/CYCLE-TEMPLATE.md` is a blank cycle with its
   instructions written into the comments, so a fresh copy teaches its own use.
   Copy it to `cycles/cycle-1.md`.
2. **Fill it in.** Write the one sentence the cycle is for. If you cannot say it
   in one sentence, it is trying to do too much; narrow it. Then name two or three
   goals (three is the ceiling), and under each, two or three lead measures phrased
   as countable weekly actions. If the mode contracts from Stage 7 are installed
   (see [`MODES.md`](MODES.md)), your agent can do this with you in a planning-coach
   register: it interviews you for the sentence, the goals, and the measures, and
   pushes back once if a "measure" is really a lag measure in disguise.
3. **Point the reader at it.** Set `COS_CYCLES_DIR` if your cycles do not live in
   the default `<vault>/cycles`, then run `python -m cos cycle` and confirm it
   renders the planning state.
4. **Start scoring.** On the start date, set `status: active`, and run the weekly
   review (see [`../commands/cycle-review.md`](../commands/cycle-review.md)) once a
   week. Count, write the row, read the score. Twelve times, and the cycle is done.

Look at [`../cycles/cycle-1-example.md`](../cycles/cycle-1-example.md) for a filled
cycle with three weeks of scores, including one honest weak week, to see the shape
before you write your own.
