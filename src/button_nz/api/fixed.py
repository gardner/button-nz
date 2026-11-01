"""A survey fixed as someone decided it, pinned to the survey they decided.

``serve --survey-decided-by`` stops the app changing the survey; the pin
(``--survey-id``) says which survey that was. A survey file replaced since
(regenerated, copied over) has another id and none of the decisions, so it
is refused wherever the fixed survey is served or designed on, with both
ids, rather than served or designed on as if undecided (#91).
"""

from pathlib import Path
from typing import NamedTuple

from button_nz.perception.confirm import Survey


class FixedSurvey(NamedTuple):
    decided_by: str  # who decided it, e.g. "the owner"
    survey_id: str  # the survey they decided


class SurveyReplaced(RuntimeError):
    """The survey file isn't the fixed survey."""


def read_fixed(path: Path | None, fixed: FixedSurvey | None) -> Survey | None:
    """The survey in ``path`` (None if there is none), read once and checked
    to be the fixed survey if it is fixed (else ``SurveyReplaced``). Callers use
    what this returns, never the file again: it may be replaced meanwhile."""
    found = None if path is None else Survey.read(path)
    check_fixed(found, fixed)
    return found


def check_fixed(found: Survey | None, fixed: FixedSurvey | None) -> None:
    """Nothing if the survey isn't fixed or ``found`` is the fixed survey; else
    ``SurveyReplaced``, saying what to do."""
    if fixed is None or (found is not None and found.id == fixed.survey_id):
        return
    now = "missing" if found is None else f"survey {found.id}"
    raise SurveyReplaced(
        f"This server's survey is fixed as {fixed.decided_by} decided survey "
        f"{fixed.survey_id}, but its survey file is now {now}: put the decided "
        "survey back, or pin the new one once it is decided."
    )
