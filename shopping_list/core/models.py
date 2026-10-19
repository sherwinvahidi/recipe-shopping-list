from dataclasses import dataclass, field
from fractions import Fraction


@dataclass(frozen=True)
class Ingredient:
    name: str
    quantity: Fraction | None
    unit: str | None


@dataclass
class Recipe:
    name: str
    servings: int
    ingredients: list[Ingredient] = field(default_factory=list)
    id: int | None = None


@dataclass(frozen=True)
class RecipeSummary:
    id: int
    name: str
    servings: int
    ingredient_count: int
