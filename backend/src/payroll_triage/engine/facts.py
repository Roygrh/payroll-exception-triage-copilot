"""Facts schemas: the structured input the LLM receives per finding (ADR-008).

Every number the model is allowed to mention comes from one of these models.
The field descriptions are shown to the model so it can name the facts; the
schema is versioned with the eval manifest (facts keys must stay equal to the
`expected_findings[].facts` keys in `evals/cases/manifest.yaml`).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

FACTS_SCHEMA_VERSION = 2  # 2: hours_late (Iteration 2b)

# Units of the duration facts (P1.I2b.S8). Units are metadata: fact names and values are unchanged.
HOURS = {"unit": "hours"}
MINUTES = {"unit": "minutes"}


class MealPeriodFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hours_to_meal: float = Field(
        description="Hours from call to meal out, in tenths", json_schema_extra=HOURS
    )
    meal_minutes: int = Field(
        description="Recorded meal duration in whole minutes", json_schema_extra=MINUTES
    )
    minutes_late: int = Field(
        description="Minutes by which meal out exceeded the deadline", json_schema_extra=MINUTES
    )
    hours_late: float = Field(
        description="The same delay as minutes_late, in hours (tenths); zero when not late",
        json_schema_extra=HOURS,
    )
    increments: int = Field(description="Started penalty increments owed for the delay")
    penalty_usd: Decimal = Field(description="Meal penalty owed for the day, USD")
    is_late: bool = Field(description="True when meal out is later than the deadline")
    is_short: bool = Field(description="True when the meal is shorter than the minimum")
    deadline_hours: float = Field(
        description="Meal deadline in hours after call (agreement)", json_schema_extra=HOURS
    )
    min_duration_minutes: int = Field(
        description="Minimum meal duration in minutes (agreement)", json_schema_extra=MINUTES
    )
    increment_minutes: int = Field(
        description="Length of one penalty increment in minutes", json_schema_extra=MINUTES
    )


FACTS_MODELS: dict[str, type[BaseModel]] = {"MEAL_PERIOD": MealPeriodFacts}


def fact_units(rule_id: str) -> dict[str, str]:
    """The unit of each fact that has one ("hours" or "minutes"); the unit-aware check of the
    validate node compares a number written with a unit only with facts of that unit."""
    model = FACTS_MODELS.get(rule_id)
    if model is None:
        return {}
    return {
        name: extra["unit"]
        for name, field in model.model_fields.items()
        if isinstance(extra := field.json_schema_extra, dict) and "unit" in extra
    }
