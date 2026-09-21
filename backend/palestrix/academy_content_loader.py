"""Lesson bodies, loaded from Markdown files in the repository.

``academy_catalog.py`` owns the *shape* of the academy -- which paths exist,
which modules they hold, in what order, for how many Palestras. This module
owns what a student actually reads. Splitting them keeps the catalog legible:
forty-seven lesson bodies inlined into a Python tuple would bury the structure
they belong to.

A lesson lives at::

    academy_content/<path-slug>/<NN>-<module-slug>.md

where ``NN`` is the module's 1-based position and ``<module-slug>`` is its
title slugified. The file opens with optional front matter::

    ---
    summary: What this module is, in one line, for the list view.
    lab: log-triage
    pass: 80
    ---

    # Reading auth logs at speed
    ...

``lab`` names a lab template by slug. When that template exists *and* carries
a published grading scheme, the module can only be completed by passing it --
see ``api/academy.py``. ``pass`` is the percentage required, defaulting to 80.

A module with no file is not an error. It keeps its title and its place, and
the UI says the lesson is still being written, which is honest about a
curriculum that is filled in over time rather than all at once.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

CONTENT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "academy_content")

DEFAULT_PASS_PERCENT = 80

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Lesson:
    summary: str = ""
    body: str = ""
    lab_slug: str | None = None
    pass_percent: int = DEFAULT_PASS_PERCENT

    @property
    def empty(self) -> bool:
        return not self.body.strip()


EMPTY = Lesson()


def slugify(title: str) -> str:
    """Title -> file slug. Stable enough to rename a file by hand."""
    return _SLUG_STRIP.sub("-", title.lower()).strip("-")


def filename_for(position: int, title: str) -> str:
    """1-based position prefix keeps the directory in reading order."""
    return f"{position + 1:02d}-{slugify(title)}.md"


def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Parse the leading ``---`` block. Hand-rolled on purpose: the format is
    three flat keys, and a YAML dependency for that would be silly."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end]
    rest = text[end + 4 :].lstrip("\n")

    meta: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip().lower()] = value.strip()
    return meta, rest


def parse(text: str) -> Lesson:
    meta, body = _split_front_matter(text)

    # Out of range falls back to the default rather than clamping: "pass: 500"
    # is a typo, and silently demanding 100% is a worse answer than the
    # default the author would have got by omitting the key.
    pass_percent = DEFAULT_PASS_PERCENT
    raw_pass = meta.get("pass", "")
    if raw_pass.isdigit() and 1 <= int(raw_pass) <= 100:
        pass_percent = int(raw_pass)

    lab = meta.get("lab") or None
    return Lesson(
        summary=meta.get("summary", "").strip(),
        body=body.strip(),
        lab_slug=lab,
        pass_percent=pass_percent,
    )


def load(path_slug: str, position: int, title: str, root: str = CONTENT_ROOT) -> Lesson:
    """The lesson for one module, or ``EMPTY`` when none is written yet."""
    filename = filename_for(position, title)
    full = os.path.join(root, path_slug, filename)
    try:
        with open(full, encoding="utf-8") as fh:
            return parse(fh.read())
    except FileNotFoundError:
        return EMPTY
    except OSError:
        return EMPTY
