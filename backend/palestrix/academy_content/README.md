# Academy lesson content

One Markdown file per module. `academy_catalog.py` owns the *shape* of the
academy — which paths exist, which modules they hold, in what order, for how
many Palestras. These files own what a student reads.

## Where a file goes

```
academy_content/<path-slug>/<NN>-<module-slug>.md
```

`NN` is the module's **1-based position** in the catalog, zero-padded. The
slug is the module title lowercased with every run of non-alphanumeric
characters replaced by `-`. Rather than working it out by hand:

```python
from palestrix.academy_content_loader import filename_for
filename_for(1, "Reading auth logs at speed")   # 02-reading-auth-logs-at-speed.md
```

A file whose name matches no module is a test failure
(`test_content_root_holds_no_orphans`), which is what catches a renamed title
silently orphaning its lesson.

## Front matter

Optional, and only three keys:

```
---
summary: One line for the roadmap list. Write it; the list looks bare without one.
lab: log-triage
pass: 80
---
```

- **summary** — shown under the title in the roadmap.
- **lab** — a lab template *slug*. When that template exists on the
  deployment **and** carries a published grading scheme, the module can only
  be completed by passing it. Otherwise it falls back to the honour system,
  so naming a lab that has not been imported yet is safe.
- **pass** — percentage required, 1–100, default 80. Out of range falls back
  to the default rather than clamping, because `pass: 500` is a typo.

## Publishing

`ensure_catalog` reloads every file at API startup, so a pull and a restart
publishes an edit. Bodies are reapplied each time — the repository is the
source of truth, not the database row.

A module with no file keeps its title and its place in the path, and the UI
says the lesson is not written yet. That is deliberate: the curriculum fills
in over time, and a half-written path should still show its shape.

## What the renderer supports

`components/ui/markdown.tsx` is a small in-house renderer, not a full
CommonMark implementation. It handles headings, paragraphs, fenced code,
inline code, bold, italic, links, blockquotes and **flat** lists.

No tables, and no nested lists — they will render as flat ones. Nothing is
parsed as raw HTML, so author input cannot inject markup.

## House style

The three shipped SOC Analyst lessons set the tone. Briefly:

- Lead with what the thing is *for*, not with definitions.
- Show real artifacts — log lines, event fields, commands — and read them.
- Say what is boring as well as what is alarming. Knowing what to ignore is
  most of the skill, and a lesson that treats everything as an incident
  teaches an analyst to escalate everything.
- Close with a handful of questions a reader can answer from the text.
