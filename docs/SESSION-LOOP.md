# The session loop

The memory engine in this repository is the deterministic part of an AI chief of
staff: it stores facts and hands them back reliably. The session loop is the part you
live in day to day. It is three commands you type to your AI assistant, one to open
the day, one to checkpoint in the middle, one to close it down. Together they give a
session a beginning, a middle, and an end, so no day starts from a blank page and no
day ends with work half-remembered.

## Why a loop

This rhythm was built for a working style where the hard part is not doing the work,
it is holding the thread: remembering where you left off, what mattered most, and what
you already decided. If you have ever opened your laptop and lost ten minutes just
reconstructing what you were doing, the loop is for you. Open, checkpoint, close. Every
session becomes resumable, because the close of one session writes the opening of the
next.

The loop does not require you to be organized. The assistant does the remembering, the
engine does the storing, and the state note carries the handoff. You just type three
short commands at the natural seams of your day.

## The three commands

**/start** opens the day. The assistant pulls your standing facts and open projects
from the memory engine, reads your task list and the note your last session left
behind, and gives you one short briefing: a single Must (the most important thing), a
Should or two, a quick Could win, and anything time-sensitive. Then it asks what you
want to work on. It never starts work on its own.

**/sync** is a mid-session checkpoint. The assistant summarizes what has happened so
far in a few bullets, proposes any durable facts worth saving to memory, flags which
files changed, and names the open threads. You approve what gets saved before anything
is written. Use it whenever you want to lock in progress without stopping.

**/wrap** closes the session. The assistant recaps the wins and the open threads, saves
the durable facts and a one-record summary of the session to the engine, updates a
small "last session" note for next time, and queues a candidate Must for tomorrow. Then
it ends cleanly. The next /start reads what /wrap wrote.

## How the commands use the memory engine

The engine is a fact store you query and write through a small command-line tool
(`python -m cos memory ...`). The commands lean on a few of its operations:

- **/start reads.** It runs `memory context` for a tiered briefing and
  `memory retrieve` for specific projects and your profile, so the briefing is built
  from stored facts, not from the assistant's guesses.
- **/sync and /wrap write.** When you approve a durable fact, the assistant runs
  `memory add`, which validates the fact against a write contract before it is stored.
  A malformed fact is rejected at the gate, so memory does not quietly rot.
- **/wrap also records an episode,** a single summary of the whole session, so the
  shape of the work survives and not just the isolated facts.

The dividing line is simple. The engine is deterministic: the same query gives the same
answer, every write is validated, history is kept. The commands are judgment: deciding
what is worth saving, what the Must is, how to phrase a briefing. The engine never
guesses; the commands never store anything they did not validate first.

## How to install

The three commands are prose instruction files in the `commands/` folder of this
repository: `start.md`, `sync.md`, and `wrap.md`. They are written for an AI agent to
read and follow, not for the computer to execute directly.

To install them for an assistant that uses the Claude Code command convention, copy the
files into that assistant's commands directory:

```
cp commands/start.md commands/sync.md commands/wrap.md  <your-vault>/.claude/commands/
```

After that, typing `/start`, `/sync`, or `/wrap` in a session loads the matching
instructions. If your assistant uses a different convention for custom commands or
skills, put the files wherever it looks for them; the content is the same, only the
folder name changes.

The commands assume the memory engine is already installed and seeded. If it is not,
have your assistant read `AGENTS.md` first; that file walks it through installing,
adapting, and verifying the engine against your own vault.

## How to adapt the commands to your vault

The command files are written around the sample vault in this repository, so the file
paths and project names in them are examples, not requirements. Adapt them to your own
setup:

- **Paths.** Each command treats your task list and your "last session" note as
  configurable. Tell your assistant where yours live (for example, your daily note and
  a `state/last_session.md` file), and have it edit the prose in the command files to
  point there.
- **Project ids.** The retrieve examples use sample project handles like
  `larkspur_gardens`. Your projects have their own handles, derived from your memory
  filenames. Have your assistant confirm them with `python -m cos memory stats` and
  `python -m cos memory search`, then update the examples.
- **The opener.** /start can lead with a one-line motivational opener in a voice you
  choose. It is off by default. Turn it on only if you want it, and tell your assistant
  the register you want; leave it off and /start just gives you the briefing.

None of this requires writing code. You are editing prose instructions and telling your
assistant where your files are.

## Real limitations

These commands are rituals carried out by a model, not deterministic scripts. The
assistant decides what the Must is, what is worth saving, and how to phrase a briefing,
and those are judgments that can be wrong. The engine is the deterministic half: a fact
you save is validated and stored exactly, a query returns exactly what is there. So the
guarantee is narrow but real. The engine will not lose or corrupt what the commands
choose to save, and it will hand back exactly what was stored. What the commands choose
to save, and how well they brief you, is judgment, and judgment is checkable, not
certain. Read the briefings, approve the writes, and the loop stays accurate. Rubber-stamp
them and it drifts.

For the behavioral rules that keep the judgment accountable (stop and check before acting,
prove claims with a tool, invite the stress test, never make things up), see
[`OPERATING-RULES.md`](OPERATING-RULES.md).
