# Mode contracts

## The problem: one assistant, many jobs

A single assistant that does everything tends to bleed behaviors across contexts. The
mode that drafts and ships work starts editorializing when you wanted a quiet draft. The
mode that helps you think starts executing before you have decided anything. A reflective
conversation, the kind where you are working out what you actually want, turns into a
task list nobody asked for. None of this is the assistant being bad at its job. It is the
assistant having no job in particular, so every behavior is on the table all the time.

A mode contract fixes this by making the assistant's job explicit for a stretch of work.
One assistant, one identity, but several named modes, each governed by a short written
contract: what the mode is for, what it may do, what it must never do, how it opens and
closes, and the tone it holds. The boundaries stop being implicit and become something
you can read, audit, and point at when a line gets crossed.

## The cabinet metaphor

Think of it as one government with several ministers. There is a single state, with one
set of values and one chain of accountability. But the minister of works does not set
foreign policy, and the minister who advises on direction does not pour concrete. Each
has a portfolio and a set of limits, and the limits are what make the cabinet work. When
a minister steps outside their portfolio, that is a problem you can name, because the
portfolio was written down.

The assistant is the government. The modes are the ministers. Daily-ops holds the
working portfolio: it runs the day and gets things done. Planning-coach holds the
thinking portfolio: it helps you reason and is forbidden from executing. Quiet-hours
holds the background portfolio: scheduled work that runs without you and never reaches
outward. One identity, several portfolios, each with explicit limits.

## What ships in this kit

Three contracts and a template, in `modes/`, plus the `/mode` command that tells the
assistant how to run inside one.

- **daily-ops.md** is the default. It runs the session loop, executes approved work,
  and proposes changes to your surfaces rather than making them. It never decides
  strategy on its own and never edits your own reflective notes.
- **planning-coach.md** is the thinking partner. It asks more than it asserts, lays out
  options instead of pushing one, and cannot execute anything beyond a session note. It
  closes by handing execution items back to daily-ops.
- **quiet-hours.md** is the small end of the pattern: scheduled background work that
  writes only to its own files, never talks to you, and never sends anything outward.
- **CONTRACT-TEMPLATE.md** is the blank you copy to write your own.

These three are deliberately generic. A public kit should not ship modes that touch
real-world-sensitive ground; the modes here are the safe, universal shapes (working,
thinking, background) that any owner can adapt without risk.

## Write your own in fifteen minutes

1. **Copy the template.** `CONTRACT-TEMPLATE.md` is one page with every section blank.
2. **Name the one context.** Fill in Purpose. If you cannot say what the mode is for in
   a sentence or two, it is doing too much; split it into two modes.
3. **Write Must-never first.** Before the May list, write what the mode must never do.
   This is the load-bearing section (see below), so do it while you are fresh.
4. **Fill May, Entry, Exit, Tone, Escalation.** Keep each concrete. Name real files,
   real tools, real handoffs. Aspirational prose helps no one.
5. **Get explicit owner approval on the Must-never list, then set status to active.**
   The frontmatter carries the approval date. An unapproved contract is a draft.

Keep it to one page. A contract you cannot hold in your head is a contract the assistant
cannot hold either.

## Why Must-never matters more than May

The failure mode is overreach, not underreach. An assistant that does too little is a
mild annoyance you correct in the moment. An assistant that does too much (sends the
email you were still drafting, edits the file you wanted to keep, decides the thing you
were still thinking about) does damage that is harder to undo and harder to see coming.
So the Must-never list is the part that earns its keep. The May list describes the happy
path; the Must-never list describes the cliff edges. Spend your care there. A mode with a
vague May list and a sharp Must-never list is safe. The reverse is not.

## How contracts pair with enforcement

A contract is prose, and prose is held by the model. On a short session that is enough.
On a long one, or across a fresh context window, a held rule can slip; this is the same
decay the enforcement layer was built for. So the parts of a contract that can be
mechanized should be backed by a hook. The clearest example: a contract can say "never
edit the owner's protected files," and the protect-surfaces hook in `docs/ENFORCEMENT.md`
makes that true mechanically, no matter which mode the assistant thinks it is in. Read
the contract as the intent and the hook as the floor. Where they overlap, the hook wins,
because a hook cannot be talked around and prose can.

## Real limits

Contracts are held by the model, so they can drift on a long session. That is the
unavoidable cost of a rule that lives in prose rather than code. Three things keep the
drift small. They are kept **short**, because a one-page contract is one the model can
actually hold. They are **loaded at entry**, so the contract is fresh, not a memory from
forty messages ago. And the **riskiest lines escalate to hooks**, so the limits that
would do real damage if forgotten do not depend on the model remembering them at all.

That is the real shape of it. A contract makes the boundary explicit and auditable,
which is worth a great deal on its own. For the lines where explicit is not enough, the
enforcement layer is where they go to become unbreakable.
