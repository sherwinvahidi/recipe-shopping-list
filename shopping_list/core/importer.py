import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

from shopping_list.core.models import Ingredient, Recipe
from shopping_list.core.validation import (
    Issue,
    normalize_recipe_name,
    validate_recipe,
    validate_row,
)

REQUIRED_COLUMNS = ("recipe", "servings", "ingredient", "quantity", "unit")
MISSING_COLUMNS = (
    "Missing required column(s): {missing}. "
    "Required columns: recipe, servings, ingredient, quantity, unit"
)
NO_ROWS = "No recipe rows found. Required columns: recipe, servings, ingredient, quantity, unit"
NOT_UTF8 = "File is not valid UTF-8 text. Save it as 'CSV UTF-8' and try again."
IGNORED_COLUMNS = "Ignored columns: {columns}"
SERVINGS_MISMATCH = "Rows disagree on servings; using {servings}"


@dataclass
class PreviewRow:
    line_no: int
    ingredient: str
    quantity: str
    unit: str
    issues: list[Issue]
    parsed: Ingredient | None
    skipped: bool = False


@dataclass
class PreviewRecipe:
    name: str
    servings: str
    rows: list[PreviewRow]
    issues: list[Issue]
    parse_issues: list[Issue]
    parsed_servings: int | None
    skipped: bool = False


@dataclass
class ImportPreview:
    file_issues: list[Issue] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    recipes: list[PreviewRecipe] = field(default_factory=list)

    @property
    def active_recipes(self) -> list[PreviewRecipe]:
        return [r for r in self.recipes if not r.skipped]

    @property
    def is_importable(self) -> bool:
        if any(i.level == "error" for i in self.file_issues):
            return False
        active = self.active_recipes
        if not active:
            return False
        for recipe in active:
            if any(i.level == "error" for i in recipe.issues):
                return False
            for row in recipe.rows:
                if not row.skipped and any(i.level == "error" for i in row.issues):
                    return False
        return True

    def to_recipes(self) -> list[Recipe]:
        if not self.is_importable:
            raise ValueError("Preview has unresolved errors")
        return [
            Recipe(
                r.name,
                r.parsed_servings,
                [row.parsed for row in r.rows if not row.skipped],
            )
            for r in self.active_recipes
        ]


def _error(message: str) -> Issue:
    return Issue("error", message, None)


def _blank(cells: list[str]) -> bool:
    return all(not c.strip() for c in cells)


def _valid_servings(text: str) -> int | None:
    text = text.strip()
    return int(text) if text.isdecimal() and text.isascii() and int(text) > 0 else None


def parse_csv_text(text: str) -> ImportPreview:
    preview = ImportPreview()
    first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
    delimiter = "\t" if "\t" in first_line else ","
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)

    header: list[str] | None = None
    data: list[tuple[int, list[str]]] = []
    for cells in reader:
        if _blank(cells):
            continue
        if header is None:
            header = cells
        else:
            data.append((reader.line_num, cells))

    if header is None:
        preview.file_issues.append(_error(NO_ROWS))
        return preview

    names = [h.strip().lower() for h in header]
    index: dict[str, int] = {}
    ignored: list[str] = []
    for i, name in enumerate(names):
        if name in REQUIRED_COLUMNS and name not in index:
            index[name] = i
        else:
            ignored.append(header[i].strip())
    missing = [c for c in REQUIRED_COLUMNS if c not in index]
    if missing:
        preview.file_issues.append(_error(MISSING_COLUMNS.format(missing=", ".join(missing))))
        return preview
    if not data:
        preview.file_issues.append(_error(NO_ROWS))
        return preview
    ignored = [c for c in ignored if c]
    if ignored:
        preview.notices.append(IGNORED_COLUMNS.format(columns=", ".join(ignored)))

    def cell(cells: list[str], column: str) -> str:
        i = index[column]
        return cells[i].strip() if i < len(cells) else ""

    groups: dict[str, PreviewRecipe] = {}
    servings_seen: dict[str, list[str]] = {}
    for line_no, cells in data:
        name = cell(cells, "recipe")
        key = normalize_recipe_name(name)
        servings = cell(cells, "servings")
        recipe = groups.get(key)
        if recipe is None:
            recipe = PreviewRecipe(name, servings, [], [], [], None)
            groups[key] = recipe
            servings_seen[key] = []
            preview.recipes.append(recipe)
        servings_seen[key].append(servings)
        recipe.rows.append(
            PreviewRow(
                line_no,
                cell(cells, "ingredient"),
                cell(cells, "quantity"),
                cell(cells, "unit"),
                [],
                None,
            )
        )

    for key, recipe in groups.items():
        values = servings_seen[key]
        valid = next((v for v in values if _valid_servings(v) is not None), None)
        recipe.servings = valid if valid is not None else values[0]
        if len({v for v in values if v}) > 1:
            recipe.parse_issues.append(
                Issue("warning", SERVINGS_MISMATCH.format(servings=recipe.servings), "servings")
            )

    return revalidate(preview)


def parse_csv_file(path: Path) -> ImportPreview:
    try:
        text = Path(path).read_text(encoding="utf-8-sig", newline="")
    except UnicodeDecodeError:
        return ImportPreview(file_issues=[_error(NOT_UTF8)])
    return parse_csv_text(text)


def revalidate(preview: ImportPreview) -> ImportPreview:
    for recipe in preview.recipes:
        for row in recipe.rows:
            row.parsed, row.issues = validate_row(row.ingredient, row.quantity, row.unit)
        active = sum(1 for row in recipe.rows if not row.skipped)
        recipe.parsed_servings, recipe_issues = validate_recipe(recipe.name, recipe.servings, active)
        recipe.issues = list(recipe.parse_issues) + recipe_issues
    return preview
