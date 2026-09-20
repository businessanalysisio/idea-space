from typing import Literal

from app.models import Requirement

TraceabilityStatus = Literal["at_risk", "verified", "partial", "draft"]

_VERIFIED_STATUSES = {"approved", "delivered"}


def traceability_status(requirement: Requirement) -> TraceabilityStatus:
    """Compute a requirement's traceability status from its links and status.

    Checked in order:
    1. at_risk  - any linked open, high-severity Risk.
    2. verified - requirement.status is approved/delivered AND has >=1 link
                  in every one of Stakeholders/Decisions/Tasks.
    3. partial  - at least one link in any category.
    4. draft    - zero links in every category.
    """
    if any(risk.severity == "high" and risk.status == "open" for risk in requirement.risks):
        return "at_risk"

    has_full_coverage = bool(requirement.stakeholders) and bool(requirement.decisions) and bool(
        requirement.tasks
    )
    if requirement.status in _VERIFIED_STATUSES and has_full_coverage:
        return "verified"

    has_any_link = bool(
        requirement.stakeholders or requirement.decisions or requirement.risks or requirement.tasks
    )
    if has_any_link:
        return "partial"

    return "draft"
