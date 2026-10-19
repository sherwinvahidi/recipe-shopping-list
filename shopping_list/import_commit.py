from dataclasses import dataclass, field
from typing import Callable, Literal

from shopping_list.core.importer import ImportPreview
from shopping_list.core.models import Recipe, RecipeSummary
from shopping_list.core.validation import normalize_recipe_name
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
    # Old library id -> id of the recipe that replaced it.
    replaced_ids: dict[int, int] = field(default_factory=dict, compare=False)


def commit_import(
    preview: ImportPreview, repo: RecipeRepository, resolve: Resolver
) -> ImportResult | None:
    """Write a preview to the repository, asking `resolve` about duplicates first.

    Returns None (nothing written) if the resolver cancels. Raises ValueError
    if the preview is not importable.
    """
    recipes = preview.to_recipes()
    names = [normalize_recipe_name(r.name) for r in recipes]
    if len(set(names)) != len(names):
        raise ValueError("Two recipes in this import have the same name")

    # Phase 1: decide every action before touching the database.
    plan: list[tuple[Recipe, str, list[RecipeSummary]]] = []
    sticky: DuplicateChoice | None = None
    for recipe in recipes:
        existing = repo.find_by_name(recipe.name)
        if not existing:
            plan.append((recipe, "add", []))
            continue
        # A sticky choice never covers several matches: Replace would delete
        # them all, so the user is asked (and warned) again.
        choice = sticky if len(existing) == 1 else None
        if choice is None:
            choice = resolve(recipe, existing)
            if choice is None:
                return None
            if choice.apply_to_all:
                sticky = choice
        plan.append((recipe, choice.action, existing))

    # Phase 2: apply all writes atomically, in preview order.
    added = replaced = skipped = 0
    replaced_ids: dict[int, int] = {}
    with repo.transaction():
        for recipe, action, existing in plan:
            if action == "skip":
                skipped += 1
            elif action == "replace":
                ids = sorted(s.id for s in existing)
                new_id = repo.replace(ids[0], recipe)
                for other in ids[1:]:
                    repo.delete(other)
                replaced_ids.update(dict.fromkeys(ids, new_id))
                replaced += 1
            else:  # "add" or "keep_both"
                repo.add(recipe)
                added += 1
    return ImportResult(added, replaced, skipped, replaced_ids)
