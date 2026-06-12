# Sample Vault (synthetic demo data)

This folder is a small, fully synthetic vault for trying the memory engine
against realistic-but-fake data. Nothing here is real. The owner persona is
**Maya Okonkwo**, a freelance landscape architect in Asheville who runs a
one-person studio and keeps every project, plant list, and decision in this
vault. The corpus tells one coherent little story: a flagship garden redesign, a
private estate, a native-plant nursery, and a small irrigation tool she directs
but does not code.

The `memory/` folder is what the engine consumes: one Markdown file per memory,
covering all six types (`user`, `self`, `project`, `reference`, `feedback`,
`law`). The `MEMORY.md` index is a human table of contents and is skipped by the
loader. The other folders (`studio/`, `homestead/`, `admin/`) are flavor: a
human vault sketched around the corpus so it feels real. The engine does not
read them.

## Quickstart

Point the engine at this directory, seed the memory corpus, then search it:

```sh
export COS_VAULT="$(pwd)/sample-vault"
python -m cos memory seed --memory-dir sample-vault/memory
python -m cos memory search meadow
```

Try a few searches to see retrieval work: `larkspur`, `irrigation`, `nudge`,
`plant names`. Then explore the three-tier view:

```sh
python -m cos memory context --query irrigation
```
