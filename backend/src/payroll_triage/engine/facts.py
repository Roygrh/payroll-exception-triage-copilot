"""Facts schemas: the structured input the LLM receives per finding (ADR-008).

Every number the model is allowed to mention comes from one of these models.
The field descriptions are shown to the model so it can name the facts; the
schema is versioned with the eval manifest (facts keys must stay equal to the
`expected_findings[].facts` keys in `evals/cases/manifest.yaml`).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

FACTS_SCHEMA_VERSION = 1


class MealPeriodFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    hours_to_meal: float = Field(description="Hours from call to meal out, in tenths")
    meal_minutes: int = Field(description="Recorded meal duration in whole minutes")
    minutes_late: int = Field(description="Minutes by which meal out exceeded the deadline")
    increments: int = Field(description="Started penalty increments owed for the delay")
    penalty_usd: Decimal = Field(description="Meal penalty owed for the day, USD")
    is_late: bool = Field(description="True when meal out is later than the deadline")
    is_short: bool = Field(description="True when the meal is shorter than the minimum")
    deadline_hours: float = Field(description="Meal deadline in hours after call (agreement)")
    min_duration_minutes: int = Field(description="Minimum meal duration in minutes (agreement)")
    increment_minutes: int = Field(description="Length of one penalty increment in minutes")


FACTS_MODELS: dict[str, type[BaseModel]] = {"MEAL_PERIOD": MealPeriodFacts}
