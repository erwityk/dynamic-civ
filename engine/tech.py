from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tech:
    name: str
    cost: int
    prereqs: tuple[str, ...]
    unlocks: tuple[str, ...]  # UnitType / BuildingType names


TECHS: dict[str, Tech] = {t.name: t for t in [
    Tech("Agriculture",      20, (),              ("Granary",)),
    Tech("Mining",           20, (),              ("Workshop",)),
    Tech("Writing",          25, (),              ("Library",)),
    Tech("Bronze Working",   30, ("Mining",),     ("Spearman",)),
    Tech("Mathematics",      35, ("Writing",),    ("Aqueduct", "Catapult")),
    Tech("Currency",         30, ("Writing",),    ("Market",)),
    Tech("Horseback Riding", 35, ("Agriculture",), ("Cavalry",)),
]}


def available_techs(researched: set[str]) -> list[Tech]:
    """Return all techs whose prerequisites are met and that haven't been researched yet."""
    return [
        t for t in TECHS.values()
        if t.name not in researched
        and all(p in researched for p in t.prereqs)
    ]
