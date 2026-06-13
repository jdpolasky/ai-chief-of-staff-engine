# AI Chief of Staff — Memory Engine

A working, tested memory engine for an AI chief of staff: a bitemporal fact store your AI assistant reads at the start of every session and writes to as it learns who you are, what you're working on, and how you want to be helped.

This is not a framework or a demo. It is the engine extracted from a personal AI-chief-of-staff system that I run daily, re-built clean for public use. Your AI can install it, adapt it to your vault, and prove the install worked, all without you writing code.

## What it does

Most AI-assistant memory is a text file that grows until it rots. This engine treats memory as data:

- **Bitemporal fact store** (SQLite + FTS5). Every fact carries two timelines: when it was true in the world (`valid_from`/`valid_to`) and when the system learned it (`tx_from`/`tx_to`). Facts are never silently edited; they are superseded or retracted, and history survives.
- **Write contracts.** Every write is validated against a JSON Schema contract before it touches the database. Malformed memory is rejected loudly at the gate, not discovered later.
- **Three-tier context retrieval.** `cos memory context "<query>"` returns a ranked, deduplicated briefing (pinned structural facts, high-relevance matches, background) sized for an AI context window.
- **Markdown loader.** Your memory corpus stays human-readable markdown with YAML frontmatter. The loader seeds it into the database idempotently: re-runs are no-ops, long rule files split into retrievable sections, nothing truncates.
- **Verification harness.** `python -m cos regress` runs the probe suite. Every code path in the engine ships with a probe that proves it works. If your AI ports or adapts this engine, the harness tells you whether the port is real.

## Quickstart (five minutes)

Requires Python 3.13+.

```
git clone <this repo>
cd ai-chief-of-staff-engine
pip install -r requirements.txt

# Prove the kit works as shipped
python -m cos regress

# Try it on the included synthetic vault
set COS_VAULT=%CD%\sample-vault          (PowerShell: $env:COS_VAULT="$PWD\sample-vault")
python -m cos memory seed --memory-dir sample-vault/memory
python -m cos memory search "irrigation"
python -m cos memory context --query "what is the flagship project"
```

The sample vault is a fully synthetic corpus (a fictional landscape architect and her studio) that exercises every memory type. See `sample-vault/README.md`.

## Install it for yourself

Point your AI agent (Claude Code or equivalent) at this repository and tell it to read **AGENTS.md**. That file is written for your agent, not for you: it walks the agent through verifying the kit, mapping it onto your own vault layout, adopting the memory-file format, seeding, and wiring retrieval into your session startup. The design requirement is that it upgrades *your* build, whatever your layout looks like; nothing assumes the original author's vault.

Configuration is four environment variables: `COS_VAULT` (your vault root), and optionally `COS_STATE_DIR`, `COS_DB`, `COS_MEMORY_DIR` to relocate state, database, and memory corpus.

## Design principles

These are the rules the parent system converged on after months of daily use and a formal architecture review. The engine embodies the first half; the rest describe the system it belongs to.

1. **Routine is code, judgment is model.** Anything deterministic (state, indexes, summaries, checks) is a script; the model spends its judgment on what scripts can't do.
2. **State is computed, not recalled.** The assistant never asserts system state from memory; it runs the command that computes it.
3. **Enforcement lives in the harness.** Rules the assistant must not break are hooks and validators that block the action, not prose the model is asked to remember.
4. **Propose/commit split.** The assistant holds propose-rights; the owner holds commit-rights over their own surfaces. The split is enforced at the write layer.
5. **Logs append, organs distill.** Raw history accumulates in append-only logs; curated working files stay small and current.
6. **Grow only from observed failure.** New machinery is added when something actually broke, not speculatively.
7. **One front door per area.** Every domain has exactly one hub note a reader (human or AI) enters through.
8. **Schema above kernel.** The file-type and naming conventions outrank any single file's contents.
9. **Hard budgets, progressive disclosure.** Indexes and briefings have size caps; additions require removals.
10. **The system tends itself.** Scheduled rituals lint the memory corpus, flag contradictions and orphans, and surface their own silence.

## Operating rules

Four rules, written as prose your assistant adopts, live in [`docs/OPERATING-RULES.md`](docs/OPERATING-RULES.md): stop and check before acting, prove claims with a tool, invite the stress test, never make things up. They are the behavioral counterpart to the engine's mechanical guarantees, and the [enforcement layer](docs/ENFORCEMENT.md) now backs the ones that can be mechanized.

## Session loop

Three commands give a work session a beginning, middle, and end: `/start` opens the day with a Must/Should/Could briefing built from stored facts, `/sync` checkpoints mid-session and saves durable facts, and `/wrap` closes the session, writes an episode record, and leaves a state note the next `/start` resumes from. They live in [`commands/`](commands/) as prose instruction files an AI agent reads, and they use the memory engine for everything they store. The engine is the deterministic half; the commands are the judgment half. See [`docs/SESSION-LOOP.md`](docs/SESSION-LOOP.md).

## Enforcement

Rules decay when they live only as prose: a long session or a fresh context window quietly drops them. So the rules that must not break are moved out of the model's memory and into the harness around it. This stage ships three Claude Code hooks, off until you wire them in: `protect_surfaces` enforces the propose/commit split by blocking edits to files you marked as yours (with a one-time consent-file override), `effort_governor` is a runaway brake that trips at tool-call thresholds, and `output_lint` checks the assistant's final message against rules you turn on. Every hook is standard-library only and fails open by design (a bug in a hook allows the action rather than locking you out), and every branch is covered by `probe_hooks`. See [`docs/ENFORCEMENT.md`](docs/ENFORCEMENT.md).

## Incident logbook

A working system improves by logging its failures as data, not by relitigating them as arguments. This stage adds a failure-capture loop: `/incident` writes a classified record with no ceremony the moment something breaks, and `/incident-review`, run every few weeks, mines the records for repeats and proposes feedback rules for the patterns that recur. On your approval a rule graduates into the memory corpus the engine seeds, and a rule that keeps failing escalates to an enforcement hook. It is markdown and prose only, and it makes the system self-tending: corrections grow only from things that actually broke. See [`docs/LOGBOOK.md`](docs/LOGBOOK.md).

## Self-tending

Untended memory rots quietly: the index drifts, two rules start to contradict, dead notes accumulate, and none of it is loud. The fix is a ritual, not discipline. Two self-tending rituals run on a schedule: a **corpus lint** (`python -m cos lint`) runs five deterministic, read-only checks over the memory corpus (index orphans, malformed frontmatter, stale done-notes, duplicate names, broken cross-links) and stays silent on a clean corpus, loud on findings; and a weekly **dream run** (`/dream`) re-reads recent session residue and proposes at most three durable patterns ("you keep doing X", "these two rules contradict", "this memory looks dead"), each as accept or reject, so the corpus changes only through your yes. This is design principle ten made real. See [`docs/SELF-TENDING.md`](docs/SELF-TENDING.md).

## Capability registry

An assistant with many tools keeps re-learning the same routing lesson: which tool works for which job, and which approaches are dead ends. Each re-discovery costs a failed attempt. The capability registry (`capability/registry.json`) is a small owner-curated file the assistant reads *before* it picks a tool for a class of task, recording the best route, an ordered fallback ladder, and dead ends. Each dead end carries a retest date, because a route that failed once may work later once a tool improves, so a dead end is a fact with an expiry, not a permanent verdict. The lookup is read-only (`python -m cos capability <task-class>`, or `--list`); the assistant proposes registry changes after real failures and the owner commits them, so it grows only from observed failure. See [`docs/CAPABILITY.md`](docs/CAPABILITY.md).

## Mode contracts

One assistant bleeds behaviors across contexts: the coach starts executing, the executor starts editorializing, a reflective conversation turns into a task list nobody asked for. Mode contracts fix this by giving the assistant one identity but several named modes, each governed by a short written contract (what the mode is for, what it may do, what it must never do, how it opens and closes, the tone it holds). This stage ships three contracts in [`modes/`](modes/) (daily-ops, planning-coach, quiet-hours), a blank template to write your own, and the `/mode` command that tells the assistant how to enter, hold, and exit one. The Must-never lines that would do real damage if forgotten escalate to the enforcement hooks. See [`docs/MODES.md`](docs/MODES.md).

## 12-week cycles

Annual plans die because a year is too far to feel and too vague to act on. This stage adds the quarter tier: a 12-week cycle with two or three goals, each scored not on the results you hope for but on the weekly actions you control (lead measures, not lag measures). You score the actions once a week, and the cycle renders into the morning briefing through the session loop, so the plan you wrote three weeks ago greets you each morning without you remembering it exists. The pieces are a self-documenting template (`cycles/CYCLE-TEMPLATE.md`), a read-only renderer (`python -m cos cycle`), and a weekly-review ritual. A pause is a conscious move that costs nothing but honesty; a quietly abandoned cycle is amnesia. See [`docs/CYCLES.md`](docs/CYCLES.md).

## Repository map

```
cos/                  the engine (python -m cos)
  config.py           env-var seam: COS_VAULT, COS_STATE_DIR, COS_DB, COS_MEMORY_DIR, COS_CYCLES_DIR
  memory/             schema, migrations, writers, loader, context retrieval
  braid/              write-contract validation + JSON Schema contracts
  lint.py             read-only structural checks over the memory corpus
  subcommands/        the CLI: memory add/retrieve/search/stats/context/seed, regress, lint, capability, cycle
commands/             session-loop + ritual commands your AI reads: start.md, sync.md, wrap.md, incident.md, incident-review.md, dream.md, route.md, mode.md, cycle-review.md
modes/                mode contracts: CONTRACT-TEMPLATE.md + daily-ops, planning-coach, quiet-hours
cycles/               12-week cycle plans: CYCLE-TEMPLATE.md + a filled example
hooks/                enforcement hooks (stdlib-only) + their JSON config
  config/             protected_surfaces.json, governor.json, lint_rules.json
incidents/            the incident logbook: one record per failure, a lean INDEX.md, the worked example
capability/           the capability registry: registry.json (owner-curated routing memory)
probes/               the verification harness (self-contained probe scripts)
sample-vault/         synthetic demo vault (fictional persona, zero real data)
docs/                 operating rules + a guide per stage (session loop, enforcement, logbook, self-tending, capability registry, modes, cycles)
AGENTS.md             instructions your AI reads to install and adapt the kit
```

## Roadmap

This repository releases in stages, each re-authored clean and reviewed on its own.

- **Stage 1, the runnable memory core (shipped):** the bitemporal fact store, write contracts, three-tier retrieval, the markdown loader, and the verification harness.
- **Stage 2, the session loop (shipped):** the `/start`, `/sync`, and `/wrap` commands and their docs, built on top of the memory core.
- **Stage 3, the enforcement bundle (shipped):** three Claude Code hooks that enforce the operating rules mechanically (the propose/commit write gate, the effort governor, and an output linter), their JSON config, and a probe that covers every branch. See [`docs/ENFORCEMENT.md`](docs/ENFORCEMENT.md).
- **Stage 4, the incident logbook (shipped):** a failure-capture system that logs failures as data and mines them for repeats. Two commands (`/incident` to capture, `/incident-review` to mine and graduate patterns into rules), the incidents folder, and the doc. Markdown and prose only, no new code. See [`docs/LOGBOOK.md`](docs/LOGBOOK.md).
- **Stage 5, the self-tending rituals (shipped):** the corpus lint (`python -m cos lint`, five read-only checks), the weekly dream run (`/dream`), a probe covering every check, and the doc. See [`docs/SELF-TENDING.md`](docs/SELF-TENDING.md).
- **Stage 6, the capability registry (shipped):** an owner-curated routing file the assistant consults before picking a tool, recording the best route, the fallback ladder, and dead ends that carry retest dates, plus the `route` command and a probe over every path. See [`docs/CAPABILITY.md`](docs/CAPABILITY.md).

## Status

Every probe in `probes/` passes (`python -m cos regress` reports the full count with zero failures). The sample vault seeds end to end and re-seeds idempotently. The codebase contains zero personal data by construction: it was re-authored clean-room, allow-list only, and the release gate includes an automated leak scan.
