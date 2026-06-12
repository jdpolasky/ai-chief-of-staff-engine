---
name: project-rivulet-tool
description: A small irrigation-and-runoff modeling tool Maya is building on the side.
type: project
tags: [active, software, side-project]
originSession: 6
---

Rivulet is a little command-line tool Maya is building to estimate a site's
water budget: rainfall in, evapotranspiration and runoff out, and how much
supplemental irrigation a given plant palette needs. She is not the coder; she
describes the behavior and reviews the output against her field judgment.

It already feeds two live jobs. The [[project-larkspur-gardens]] south slope and
the [[project-hollis-estate]] rain garden are both sized from Rivulet runs. The
plant water-demand figures come from [[reference-plantbase-db]].

Scope is deliberately small: one site at a time, a single growing season, a CSV
in and a one-page summary out. The temptation is to grow it into a full
hydrology suite; the standing decision is to keep it narrow and reliable.

**Why:** This is the only software project in the vault and the clearest example
of Maya directing code without writing it.
**How to apply:** When Maya asks for a Rivulet change, confirm the behavior
first and resist scope creep toward general-purpose modeling.
