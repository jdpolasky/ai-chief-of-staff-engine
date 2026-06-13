# AGENTS.md — install and adapt this memory engine for your owner

You are an AI agent. Your owner pointed you at this repository because they want the memory engine installed and adapted to their own system. This file is your work order. Read it fully before acting.

The outcome you are responsible for: your owner's vault gains a verified, idempotent, bitemporal memory store that you (and future sessions of you) seed from markdown and query at session start. The kit must be adapted to THEIR layout. Nothing here assumes the original author's vault structure, paths, or content.

## Ground rules

1. **Prove, don't assume.** After every phase below, run the named verification before moving on. If a verification fails, stop and report to your owner; do not improvise around it.
2. **Propose before you write.** Before creating or modifying anything in your owner's vault, show them the plan (where files go, what gets created) and get their approval. You hold propose-rights; they hold commit-rights.
3. **Never put real secrets or third parties' personal data into memory files.** Memory content is plain text on disk.
4. **Do not modify the engine's schema or write contracts** unless your owner explicitly asks; if you do, re-run `python -m cos regress` and treat any red probe as a stop.

## Phase 0 — verify the kit as shipped

```
pip install -r requirements.txt        (needs Python 3.13+)
python -m cos regress
```

All probes must pass before you change anything. Then prove the full loop on the included synthetic vault:

```
COS_VAULT=<repo>/sample-vault  python -m cos memory seed --memory-dir sample-vault/memory
COS_VAULT=<repo>/sample-vault  python -m cos memory context --query "flagship project"
```

Expected: the seed reports 13 files inserted plus 11 law sections; the context command returns a tiered briefing about the fictional persona's projects. Re-running seed must insert nothing (all idempotent).

## Phase 1 — map your owner's system

Decide, with your owner, four things:

1. **Vault root** (`COS_VAULT`): the directory their notes live in. Any layout works; the engine never assumes specific folders.
2. **Memory directory** (`COS_MEMORY_DIR`, default `<vault>/memory`): where the markdown memory corpus will live. If they already keep agent memory files somewhere, prefer that location.
3. **State location** (`COS_STATE_DIR`, default `<vault>/_state`): where the database and append-only JSONL backup go. Keep it out of folders that sync to public places.
4. **How you'll be invoked**: the engine is a CLI (`python -m cos ...`). Plan to call it from your session-start routine and whenever the owner teaches you something durable.

Set the environment variables in whatever mechanism persists for your sessions (settings file, shell profile, hook environment). Verify: `python -m cos memory stats` runs against the right database path.

## Phase 2 — adopt the memory-file format

Each memory is one markdown file: one fact, one file. The loader's contract:

**Frontmatter** (YAML):

```markdown
---
name: short-kebab-slug
description: one-line summary used for relevance
type: project            # or nested:  metadata: { type: project }
tags: [optional, list]
originSession: 42        # optional int
---

The fact itself, in prose.
```

**Types and what they mean** (`type:` maps to a storage category):

| type      | category   | use for |
|-----------|------------|---------|
| feedback  | preference | operating corrections the owner gave you |
| user      | capability | who the owner is |
| self      | reference  | your own running observations |
| project   | reference  | standing project state |
| reference | reference  | external tools, docs, pointers |
| law       | reference  | consolidated rule files (see below) |

**Filename prefixes** drive subject derivation: `user_*` (person), `self_*`/`project_*` (system), `reference_*` (tool), `feedback_*` (no subject), `laws_*` (system, special handling).

**Law files** (`laws_*.md`) are long consolidated rule documents. Structure them as numbered `## N. Title` sections (optionally with `### Na.` children) and an optional `## Provenance` footer (skipped). The loader stores one fact per section, tagged `law:<name>` and `section:<anchor>`, chunking any over-long section without losing content. Use these when the owner's rules outgrow individual feedback files.

**The index** `MEMORY.md` (one line per memory, `- [Title](file.md) — hook`) is for humans and for your own session-start orientation; the loader skips it.

**House style for bodies:** feedback and project memories carry a `**Why:**` line and a `**How to apply:**` line after the fact. Keep each file under ~2000 characters of body; longer content belongs in a law file or gets split.

If your owner has existing memory in another shape, migrate it: one fact per file, the frontmatter above, the prefix conventions. Propose the migration mapping before writing files.

## Phase 3 — seed and verify

```
python -m cos memory seed                 # uses COS_MEMORY_DIR, or pass --memory-dir
```

Read the summary line. Investigate anything `rejected` (the loader prints reasons; a rejection rate over 10% exits nonzero and means the format mapping is wrong; stop and fix the files, not the engine). Then verify:

1. Re-run seed: everything must report idempotent, zero new inserts.
2. `python -m cos memory search "<a term you know is in the corpus>"` returns the right facts.
3. `python -m cos memory context "<a question the owner would actually ask>"` returns a sensible tiered briefing.
4. `python -m cos memory stats` matches the corpus size you expect.

## Phase 4 — wire it into your loop

Minimum viable integration, in order of value:

1. **Session start:** run `cos memory context` with a query built from the session's opening topic, and fold the result into your working context.
2. **When the owner corrects you durably:** write a `feedback_*.md` memory file (propose it first), then re-run seed.
3. **When project state changes durably:** update or add `project_*.md` and re-seed. Prefer superseding a fact (write the new file, let content-dedup handle the rest) over editing history.
4. **Periodically:** re-run `python -m cos regress` after any engine update, and re-run seed after any corpus change. Both are safe to run any time; that is the point of idempotency.

Direct writes (`cos memory add`) exist for programmatic use; they pass through the same validation contracts. For owner-authored memory, prefer the file-then-seed path so the corpus stays human-readable.

## Adaptation notes

- **Different vault layouts:** everything is env-var driven; nothing else needs to change. Do not hardcode your owner's paths into the engine; set the variables.
- **Renaming concepts:** if your owner's system says "rules" instead of "laws" or "people" instead of "user", keep the FILENAME conventions (the loader keys on prefixes) and translate in your prose. Changing `TYPE_TO_CATEGORY`/`PREFIX_TO_SUBJECT_TYPE` in `cos/memory/loader.py` is possible but then the probe suite is your safety net: extend `probes/probe_loader.py` to cover your mapping and keep `cos regress` green.
- **What not to touch:** `cos/memory/schema.sql`, `cos/braid/contracts/*.json`, and the writers' supersede/retract semantics are the engine's guarantees. Changes there without green probes are how memory systems rot.
- **Scaling:** the store is SQLite with FTS5; thousands of facts are fine. If seeding gets slow, it is almost always signature-checking your corpus repeatedly; seed is incremental by design, so run it after changes, not on a timer.

## Phase 5 — install the session loop (Stage 2)

Once the engine is seeded and verified, install the three session commands so your
owner gets an open/checkpoint/close rhythm on top of the memory core. They live in
`commands/` as prose instruction files you read and follow: `start.md`, `sync.md`,
`wrap.md`. They are not Python; they tell you how to run the engine at the seams of a
session.

**Install.** Copy the three files into wherever your runtime looks for custom commands.
For a Claude Code style layout that is the owner's commands directory:

```
cp commands/start.md commands/sync.md commands/wrap.md  <vault>/.claude/commands/
```

If your runtime uses a different convention (a skills folder, a different filename
scheme), put them there instead; the prose is what matters, not the location.

**Adapt to your owner's layout.** The shipped command files are written around the
sample vault, so their paths and project ids are examples. Before relying on them,
edit the prose in each file to match your owner's real setup. Propose the edits first,
then make them on approval. Three things to localize:

1. **File paths.** `/start` reads the owner's task list and a `state/last_session.md`
   note; `/wrap` writes that state note. Confirm with your owner where those live in
   their vault and update the sample paths in `start.md` and `wrap.md` to point there.
2. **Subject ids.** The `retrieve` examples use sample handles like `profile` and
   `larkspur_gardens`. Your owner's handles derive from their memory filenames. Run
   `python -m cos memory stats` to confirm the corpus is seeded, then
   `python -m cos memory search "<a name you expect>"` to find the real subject ids,
   and update the examples.
3. **The opener.** `/start` can lead with a one-line motivational opener in a voice the
   owner chooses. It is off by default. Leave it off unless the owner asks for it, and
   if they do, record the voice they want in the prose.

**Verify the install with a dry /start against the sample vault.** Before pointing the
commands at your owner's real vault, prove they work end to end on the synthetic one.
Seed the sample vault, then walk `start.md` by hand: run its read commands and confirm
each returns real output.

```
COS_VAULT=<repo>/sample-vault  COS_STATE_DIR=<repo>/.tmp-verify  python -m cos memory seed --memory-dir sample-vault/memory
COS_VAULT=<repo>/sample-vault  COS_STATE_DIR=<repo>/.tmp-verify  python -m cos memory context --query "larkspur" --limit 5
COS_VAULT=<repo>/sample-vault  COS_STATE_DIR=<repo>/.tmp-verify  python -m cos memory retrieve --subject larkspur_gardens --subject-type system
```

Expected: the context call returns a tiered briefing and the retrieve call returns the
Larkspur project fact. Then read `sample-vault/state/last_session.md`: that is the
shape `/wrap` writes and `/start` reads, so a real `/start` would pick up the candidate
Must from it. Delete the temporary state directory when done. If every read returns real
data, the loop is wired correctly and you can repeat the adaptation against your owner's
vault.

## Phase 6 — install the enforcement hooks (Stage 3)

Once the loop is in place, install the three hooks that enforce the operating
rules mechanically, so the rules hold whether you remember them or not. They live
in `hooks/` as standard-library Python scripts with JSON config in
`hooks/config/`. Full reference: [`docs/ENFORCEMENT.md`](docs/ENFORCEMENT.md).

**Copy the hooks.** Put the `hooks/` folder where your runtime can reach it (for a
Claude Code layout, the project root is fine, since the settings example below
uses `${CLAUDE_PROJECT_DIR}`):

```
cp -r hooks  <your-project-root>/hooks
```

**Wire settings.json.** Add a `hooks` block in the exact official format. Copy the
complete snippet from `docs/ENFORCEMENT.md` ("How to install"); it registers
`protect_surfaces` on the `Edit|Write|NotebookEdit` matcher, `effort_governor` on
`*`, and `output_lint` as a `Stop` hook. Point the `command` paths at wherever you
put the `hooks/` folder. Restart the owner's session so the hooks load.

**Adapt the protected surfaces to the owner's real files.** Edit
`hooks/config/protected_surfaces.json`: replace the sample-vault globs with globs
for the files the owner wants to commit themselves (their task list, their
invoicing note, any front-door hub). Propose the list to the owner first, then
write it on approval. Each entry is `{ "pattern": <glob>, "label": <short-name>,
"note": <why> }`; the label names the one-time consent file, so keep it short and
filename-safe. Leave the lint rules off except the ones the owner asks for.

**Verify two ways.**

1. Run the probe: `python -m cos regress` (it now includes `probe_hooks`, which
   drives all three hooks through every branch). All probes must stay green.
2. Try it live in a scratch session: attempt an edit to one of the owner's
   protected files and confirm the hook blocks you with a propose-instead message.
   Then have the owner create the named `.consent-<label>` file, retry, and confirm
   the edit goes through exactly once and the consent file is consumed.

If the block does not fire, the hook is almost certainly not wired into
`settings.json` correctly or the session was not restarted; re-check the matcher
and the command path before changing anything else.

## Phase 8 — install the self-tending rituals (Stage 5)

Once the corpus is seeded and the loop is in place, install the two rituals that
keep the corpus from rotting: the corpus lint and the weekly dream run. Full
reference: [`docs/SELF-TENDING.md`](docs/SELF-TENDING.md).

**Verify the lint runs against the owner's corpus.** The lint is already part of
the engine; there is nothing to copy. Run it against the owner's real memory
directory:

```
python -m cos lint
```

It reads `COS_MEMORY_DIR` (or pass `--memory-dir`). It is read-only: it never
writes a file or touches the database, so it is always safe to run. Expect
`corpus clean` on a healthy corpus, or one line per finding (index-orphans,
frontmatter-malformed, stale-superseded, duplicate-names, broken-wikilinks) with
exit code 1. If it reports findings, triage them with the owner: each is a
structural drift with a plain fix (relist a file in `MEMORY.md`, add a missing
frontmatter key, move a SUPERSEDED note out of the live corpus, resolve a name
collision, fix a dangling `[[name]]` link). Fixes to the owner's files are
proposals; name them, do not make them unasked. Confirm `python -m cos regress`
stays green (`probe_lint` covers every check).

**Install the dream command.** Copy `commands/dream.md` into wherever your
runtime looks for custom commands, alongside the session-loop commands:

```
cp commands/dream.md  <vault>/.claude/commands/
```

Then either schedule it or alias it. The dream run is meant to fire weekly: if
your runtime supports scheduled sessions, set one that runs `/dream` once a week;
if it does not, leave it as a command the owner types `/dream` to invoke.
Staleness is fine either way. The ritual is catch-up by design, so a missed week
just reads more residue on the next run.

**Thresholds to adapt:** none. The lint has no tunable thresholds (its five
checks are structural pass/fail, not configurable limits), and the dream run's
one hard number, the three-proposal cap, is a deliberate fixed ceiling, not a
knob. There is nothing here to configure per owner; say so plainly rather than
inventing config. The only per-owner adaptation is the schedule above.

## If something fails

Report to your owner: the exact command, the verbatim output, and which phase you were in. The probe suite (`python -m cos regress`) is the arbiter of "is the engine broken or is my usage wrong": green probes plus a failing usage almost always means a format or env-var problem on your side.
