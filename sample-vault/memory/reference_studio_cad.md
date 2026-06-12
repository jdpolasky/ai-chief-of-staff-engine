---
name: reference-studio-cad
description: The CAD package Maya draws in, and how project files are organized.
type: reference
tags: [tool, cad, drafting]
---

Maya drafts in a desktop CAD package. Every built project gets one master file
plus dated export sheets for client review. The convention is one file per site,
never per phase, so the full history of a design lives in a single drawing.

File layout. Each drawing carries layers for survey base, grading, planting, and
irrigation. The irrigation layer is informed by [[project-rivulet-tool]] output;
the planting layer cites [[reference-plantbase-db]] names in its labels.

Exports go out as flattened PDFs for board and client review; the live file is
never shared directly. Backups run nightly to an external drive.
