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

Four rules, written as prose your assistant adopts, live in [`docs/OPERATING-RULES.md`](docs/OPERATING-RULES.md): stop and check before acting, prove claims with a tool, invite the stress test, never make things up. They are the behavioral counterpart to the engine's mechanical guarantees.

## Session loop

Three commands give a work session a beginning, middle, and end: `/start` opens the day with a Must/Should/Could briefing built from stored facts, `/sync` checkpoints mid-session and saves durable facts, and `/wrap` closes the session, writes an episode record, and leaves a state note the next `/start` resumes from. They live in [`commands/`](commands/) as prose instruction files an AI agent reads, and they use the memory engine for everything they store. The engine is the deterministic half; the commands are the judgment half. See [`docs/SESSION-LOOP.md`](docs/SESSION-LOOP.md).

## Repository map

```
cos/                  the engine (python -m cos)
  config.py           env-var seam: COS_VAULT, COS_STATE_DIR, COS_DB, COS_MEMORY_DIR
  memory/             schema, migrations, writers, loader, context retrieval
  braid/              write-contract validation + JSON Schema contracts
  subcommands/        the CLI: memory add/retrieve/search/stats/context/seed, regress
commands/             session-loop commands your AI reads: start.md, sync.md, wrap.md
probes/               the verification harness (self-contained probe scripts)
sample-vault/         synthetic demo vault (fictional persona, zero real data)
docs/                 operating rules + the session-loop guide (SESSION-LOOP.md)
AGENTS.md             instructions your AI reads to install and adapt the kit
```

## Roadmap

This repository releases in stages, each re-authored clean and reviewed on its own.

- **Stage 1, the runnable memory core (shipped):** the bitemporal fact store, write contracts, three-tier retrieval, the markdown loader, and the verification harness.
- **Stage 2, the session loop (shipped, this stage):** the `/start`, `/sync`, and `/wrap` commands and their docs, built on top of the memory core.
- **Later stages:** the incident logbook, harness hooks (including the propose/commit write gate and an effort governor), the self-tending rituals, and the capability registry pattern.

## Status

Every probe in `probes/` passes (`python -m cos regress`: 7 passed, 0 failed). The sample vault seeds end to end and re-seeds idempotently. The codebase contains zero personal data by construction: it was re-authored clean-room, allow-list only, and the release gate includes an automated leak scan.
