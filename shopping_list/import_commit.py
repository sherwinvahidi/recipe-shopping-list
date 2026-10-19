from dataclasses import dataclass
from typing import Callable, Literal

from shopping_list.core.importer import ImportPreview
from shopping_list.core.models import Recipe, RecipeSummary
from shopping_list.storage.recipes import RecipeRepository


@dataclass(frozen=True)
class DuplicateChoice:
    action: Literal["replace", "skip", "keep_both"]
    apply_to_all: bool = False


Resolver = Callable[[Recipe, list[RecipeSummary]], DuplicateChoice | None]


@dataclass(frozen=True)
class ImportResult:
    added: int
    replaced: int
    skipped: int


def commit_import(
    preview: ImportPreview, repo: RecipeRepository, resolve: Resolver
) -> ImportResult | None:
    """Write a preview to the repository, asking `resolve` about duplicates first.

    Returns None (nothing written) if the resolver cancels. Raises ValueError
    if the preview is not importable.
    """
    recipes = preview.to_recipes()

    # Phase 1: decide every action before touching the database.
    plan: list[tuple[Recipe, str, list[RecipeSummary]]] = []
    sticky: DuplicateChoice | None = None
    for recipe in recipes:
        existing = repo.find_by_name(recipe.name)
        if not existing:
            plan.append((recipe, "add", []))
            continue
        choice = sticky
        if choice is None:
            choice = resolve(recipe, existing)
            if choice is None:
                return None
            if choice.apply_to_all:
                sticky = choice
        plan.append((recipe, choice.action, existing))

    # Phase 2: apply all writes atomically, in preview order.
    added = replaced = skipped = 0
    with repo.transaction():
        for recipe, action, existing in plan:
            if action == "skip":
                skipped += 1
            elif action == "replace":
                ids = sorted(s.id for s in existing)
                repo.replace(ids[0], recipe)
                for other in ids[1:]:
                    repo.delete(other)
                replaced += 1
            else:  # "add" or "keep_both"
                repo.add(recipe)
                added += 1
    return ImportResult(added, replaced, skipped)
