---
name: reference-plantbase-db
description: The plant database Maya uses for species data, water demand, and sourcing.
type: reference
tags: [tool, plants]
originSession: 3
---

PlantBase is the regional plant database Maya relies on for botanical names,
hardiness, water demand, and bloom timing. It is the canonical source for any
species detail; guessing a plant name or its water needs is a known failure mode
(see [[self-assistant-notes]]).

How it is used. Each project's plant list cites PlantBase entries by their exact
botanical name. The meadow palette for [[project-larkspur-gardens]] and the
nursery stock at [[project-meadowlark-nursery]] share a "south-slope meadow" tag
set. Water-demand figures feed [[project-rivulet-tool]].

Access is a web login plus a CSV export. When pulling data, copy names verbatim;
do not normalize or abbreviate them.
