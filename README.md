# AI Chief of Staff: Memory Engine and Operating Loop

> Built by [Joshua Polasky](https://github.com/jdpolasky), a strategy and operations consultant. Business first, then AI. [How I work with businesses](https://github.com/jdpolasky/jdpolasky/blob/main/HOW-I-WORK.md) · joshua.polasky@gmail.com

[![regress](https://github.com/jdpolasky/ai-chief-of-staff-engine/actions/workflows/regress.yml/badge.svg)](https://github.com/jdpolasky/ai-chief-of-staff-engine/actions/workflows/regress.yml) [![GitHub stars](https://img.shields.io/github/stars/jdpolasky/ai-chief-of-staff-engine)](https://github.com/jdpolasky/ai-chief-of-staff-engine/stargazers)

*Last verified October 2026. Eight staged releases, v0.1.0 through v0.8.0, each with notes on the Releases page.*

A working, tested memory engine for an AI chief of staff: a fact store with full write history that your AI assistant reads at the start of every session and writes to as it learns who you are, what you're working on, and how you want to be helped.

I built it as the memory layer for my own system, then re-built it clean for public use. My own daily system never adopted it and still runs on plain markdown. Your AI can install it, adapt it to your vault, and prove the install worked, all without you writing code.

The memory engine is stage one. Seven further stages build the operating loop on top of it: session commands, enforcement hooks, an incident logbook, self-tending rituals, a capability registry, mode contracts, and 12-week cycles. All eight are shipped. The stages that add code (1, 3, 5, 6, and 8) each come with probes; stages 2, 4, and 7 are prose commands and markdown, with no code to probe. My working system is published separately as [chief-of-staff-2](https://github.com/jdpolasky/chief-of-staff-2), and it runs on plain markdown without this engine.

## What it does

Most AI-assistant memory is a text file that grows until it rots. This engine treats memory as data:

- **Fact store with history** (SQLite + FTS5). The engine keeps transaction-time history: each fact records when the system wrote it (`tx_from`) and, once a writer replaces or retracts it, when that belief ended (`tx_to`). `memory context --as-of` shows the facts the system still held as current at an earlier moment. Facts retracted since then don't appear. Each fact also stores `valid_from` and `valid_to`, the dates it was true in the world. Those are kept for your own use; no query filters on them.
- **What adds and what replaces.** The markdown loader only adds facts. Editing or deleting a memory file and re-seeding leaves the old fact in the database. `supersede_fact` and `retract_fact` in `cos/memory/writers.py` exist for writers that call them; there's no CLI command for either. `memory search` and `memory retrieve` skip retracted facts but still return superseded ones. Without `--as-of`, `memory context` returns current beliefs only.
- **Write contracts.** Every write is validated against a JSON Schema contract before it touches the database. Malformed memory is rejected loudly at the gate, not discovered later.
- **Three-tier context retrieval.** `python -m cos memory context --query "<words>"` returns a ranked, deduplicated briefing (pinned structural facts, high-relevance matches, background) sized for an AI context window.
- **Markdown loader.** Your memory corpus stays human-readable markdown with YAML frontmatter. The loader seeds it into the database idempotently, so re-runs are no-ops. Law files (`laws_*.md`) split into one fact per section, and long sections split into parts, so no section is cut short. The `## Provenance` footer isn't loaded. Every other memory file becomes one fact, cut at 1,950 characters, so keep those files short.
- **Verification harness.** `python -m cos regress` runs the probe suite. Each stage that adds code (stages 1, 3, 5, 6, and 8) ships with probes for the commands it adds. Each probe runs with the engine's paths pointed at a fresh temp folder, so the suite never writes to your vault. If your AI ports or adapts this engine, the harness tells you whether the port is real.

## Quickstart (five minutes)

Requires Python 3.10 or newer.

```
git clone https://github.com/jdpolasky/ai-chief-of-staff-engine.git
cd ai-chief-of-staff-engine
pip install -e .
python -m cos regress
```

The last line proves the kit works as shipped.

`pip install -e .` installs the engine, its two dependencies, and a `cos` command. Use the editable install (`-e`). The `capability/`, `cycles/`, and `probes/` folders sit outside the Python package, so a regular `pip install .` leaves them behind, and `cos capability` and `cos regress` look for theirs in the repo folder. `python -m cos --version` prints the installed version.

Then point the engine at the included synthetic vault. Pick the line for your shell.

PowerShell:

```
$env:COS_VAULT = "$PWD\sample-vault"
```

Command Prompt:

```
set COS_VAULT=%CD%\sample-vault
```

bash (macOS, Linux, Git Bash):

```
export COS_VAULT="$PWD/sample-vault"
```

Seed it and query it:

```
python -m cos memory seed --memory-dir sample-vault/memory
python -m cos memory search "irrigation"
python -m cos memory context --query flagship
```

The last command prints this (the dates are the day you seeded):

```
## Operational (0 / 10)
(none)

## Structural (2 / 10)
[1] fact #6 (reference, 2026-10-14, conf 0.95): Maya's small native-plant nursery side business that supplies her own jobs.

Meadowlark is a half-acre native-plant n...
[2] fact #5 (reference, 2026-10-14, conf 0.95): Public botanical garden redesign; the studio's flagship job this year.

Larkspur Gardens is a twelve-acre municipal b...

## Reflective (0 / 10)
(none)
```

`memory search` needs every word to match. `memory context --query` ranks facts that share any of its words, so a plain question works there too.

The sample vault is a fully synthetic corpus (a fictional landscape architect and her studio) that exercises every memory type. See `sample-vault/README.md`.

## Install it for yourself

Point your AI agent (Claude Code or equivalent) at this repository and tell it to read **AGENTS.md**. That file is written for your agent to follow: it walks the agent through verifying the kit, mapping it onto your own vault layout, adopting the memory-file format, seeding, and wiring retrieval into your session startup. The design requirement is that it upgrades *your* build, whatever your layout looks like; nothing assumes the original author's vault.

Configuration is environment variables. `COS_VAULT` is your vault root (default `~/cos-vault`). The rest are optional: `COS_STATE_DIR` for the database and backups (default `<vault>/_state`), `COS_DB` for the SQLite file (default `<state>/memory.db`), `COS_MEMORY_DIR` for the memory files to seed (default `<vault>/memory`), `COS_CYCLES_DIR` for 12-week cycle plans (default `<vault>/cycles`), `COS_CAPABILITY_REGISTRY` for the capability registry (default `capability/registry.json` in this repo), and `COS_HOOK_STATE_DIR` for the effort governor's counter files (default your system temp folder).

## Design principles

These are the rules my own system converged on after months of daily use. The engine embodies the first half; the rest describe the system it belongs to. These mechanisms came out of a private build that grew too big, so take them piece by piece and only what you need.

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

Annual plans die because a year is too far to feel and too vague to act on. This stage adds the quarter tier: a 12-week cycle with two or three goals, each scored not on the results you hope for but on the weekly actions you control (lead measures, not lag measures). You score the actions once a week, and the cycle renders into the morning briefing through the session loop, so the plan you wrote three weeks ago greets you each morning without you remembering it exists. The pieces are a self-documenting template (`cycles/CYCLE-TEMPLATE.md`), a read-only renderer (`python -m cos cycle`), and a weekly-review ritual. A pause is a conscious move that costs nothing but admitting it; a quietly abandoned cycle is amnesia. See [`docs/CYCLES.md`](docs/CYCLES.md).

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

## Stages

This repository releases in stages, each re-authored clean and reviewed on its own.

- **Stage 1, the runnable memory core (shipped):** the fact store with write history, write contracts, three-tier retrieval, the markdown loader, and the verification harness.
- **Stage 2, the session loop (shipped):** the `/start`, `/sync`, and `/wrap` commands and their docs, built on top of the memory core.
- **Stage 3, the enforcement bundle (shipped):** three Claude Code hooks that enforce the operating rules mechanically (the propose/commit write gate, the effort governor, and an output linter), their JSON config, and a probe that covers every branch. See [`docs/ENFORCEMENT.md`](docs/ENFORCEMENT.md).
- **Stage 4, the incident logbook (shipped):** a failure-capture system that logs failures as data and mines them for repeats. Two commands (`/incident` to capture, `/incident-review` to mine and graduate patterns into rules), the incidents folder, and the doc. Markdown and prose only, no new code. See [`docs/LOGBOOK.md`](docs/LOGBOOK.md).
- **Stage 5, the self-tending rituals (shipped):** the corpus lint (`python -m cos lint`, five read-only checks), the weekly dream run (`/dream`), a probe covering every check, and the doc. See [`docs/SELF-TENDING.md`](docs/SELF-TENDING.md).
- **Stage 6, the capability registry (shipped):** an owner-curated routing file the assistant consults before picking a tool, recording the best route, the fallback ladder, and dead ends that carry retest dates, plus the `route` command and a probe over every path. See [`docs/CAPABILITY.md`](docs/CAPABILITY.md).
- **Stage 7, mode contracts (shipped):** one assistant identity with several named modes, each governed by a short contract stating its purpose, what it may and must never do, and how it opens and closes, plus a blank template and the `/mode` command. See [`docs/MODES.md`](docs/MODES.md).
- **Stage 8, the 12-week cycle core (shipped):** the quarter tier, a year's ambition carried twelve weeks at a time and scored weekly on lead measures rather than outcomes, with a read-only renderer and a weekly cycle-review ritual that feeds the morning briefing. See [`docs/CYCLES.md`](docs/CYCLES.md).

## Status

Every probe in `probes/` passes (`python -m cos regress` reports the full count with zero failures). The sample vault seeds end to end and re-seeds idempotently. The codebase was re-authored clean-room, allow-list only, to keep personal data out.

## Prior art

The 12-week cycle in stage 8 follows the pattern in *The 12 Week Year* by Brian P. Moran and Michael Lennington (Wiley, 2013): a planning year shortened to twelve weeks.

## Who made this

Built by Joshua Polasky, a strategy and operations consultant. Business first, then AI. If you're an owner or leader who wants help figuring out where AI fits in your business, get in touch: joshua.polasky@gmail.com or [LinkedIn](https://linkedin.com/in/joshuapolasky).
