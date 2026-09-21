"""Whether a module has been earned.

Completing a module used to be self-attestation: press the button, take the
Palestras. That is fine for a reading, and indefensible for anything worth
120 Palestras in a scored competition.

A module that names a lab (``Module.lab_slug``) is gated on the automated
checker instead. The student launches the lab, does the work, and the grading
scheme from Phase 8 scores the instance; completion requires a ``GradeCheck``
at or above the module's ``pass_percent``.

The gate is deliberately conditional. A module is only gated when its lab
actually exists on this deployment *and* carries a **published** scheme --
a draft rubric has editable weights and grading turned off, so enforcing
against it would block students on a lab nobody can pass yet. Anything else
falls back to the honour system, which keeps a reading-only module working
and keeps a site that has not imported the labs from being bricked.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import GradeCheck, GradingScheme, Instance, LabTemplate, Module


@dataclass
class GateStatus:
    """What the UI shows and what ``complete`` enforces."""

    required: bool = False          # is this module gated at all
    lab_slug: str | None = None
    lab_title: str = ""
    lab_available: bool = False     # the template exists here
    scheme_published: bool = False
    pass_percent: int = 0
    best_percent: int | None = None  # this user's best run, None if never run
    passed: bool = True             # ungated modules are trivially "passed"

    @property
    def reason(self) -> str:
        if not self.required or self.passed:
            return ""
        if self.best_percent is None:
            return (
                f"Launch the {self.lab_title or self.lab_slug} lab and pass the "
                f"automated check ({self.pass_percent}% required) to complete this module."
            )
        return (
            f"Best check so far is {self.best_percent}%; "
            f"{self.pass_percent}% is required to complete this module."
        )


def status_for(db: Session, module: Module, user_id: str) -> GateStatus:
    if not module.lab_slug:
        return GateStatus(pass_percent=module.pass_percent)

    status = GateStatus(
        lab_slug=module.lab_slug,
        pass_percent=module.pass_percent,
    )

    template = db.scalar(
        select(LabTemplate).where(LabTemplate.slug == module.lab_slug)
    )
    if template is None:
        # The catalog names a lab this deployment has not imported. Say so
        # rather than locking the student out of content that exists.
        return status
    status.lab_available = True
    status.lab_title = template.title

    scheme = db.scalar(
        select(GradingScheme).where(GradingScheme.lab_template_id == template.id)
    )
    if scheme is None or scheme.status != "published":
        return status
    status.scheme_published = True
    status.required = True

    best = db.scalar(
        select(func.max(GradeCheck.total_percent))
        .join(Instance, Instance.id == GradeCheck.instance_id)
        .where(
            GradeCheck.user_id == user_id,
            Instance.template_id == template.id,
        )
    )
    status.best_percent = int(best) if best is not None else None
    status.passed = best is not None and int(best) >= module.pass_percent
    return status
