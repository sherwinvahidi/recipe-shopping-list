import pytest
from shopping_list.core.importer import parse_csv_text
from shopping_list.core.template import TEMPLATE_CSV
from shopping_list.storage.db import connect
from shopping_list.storage.recipes import RecipeRepository
from shopping_list.import_commit import commit_import, DuplicateChoice, ImportResult


def fresh():
    return RecipeRepository(connect(":memory:"))


def never(*_):
    raise AssertionError("resolver should not be called")


def test_clean_import():
    repo = fresh()
    assert commit_import(parse_csv_text(TEMPLATE_CSV), repo, never) == ImportResult(2, 0, 0)
    assert len(repo.list_summaries()) == 2


def test_replace_all_on_reimport():
    repo = fresh(); commit_import(parse_csv_text(TEMPLATE_CSV), repo, never)
    calls = []

    def resolve(recipe, existing):
        calls.append(recipe.name); return DuplicateChoice("replace", apply_to_all=True)

    assert commit_import(parse_csv_text(TEMPLATE_CSV), repo, resolve) == ImportResult(0, 2, 0)
    assert calls == ["Pancakes"] and len(repo.list_summaries()) == 2


def test_skip_and_keep_both():
    repo = fresh(); commit_import(parse_csv_text(TEMPLATE_CSV), repo, never)
    choices = iter([DuplicateChoice("skip"), DuplicateChoice("keep_both")])
    assert commit_import(parse_csv_text(TEMPLATE_CSV), repo, lambda r, e: next(choices)) == ImportResult(1, 0, 1)
    assert len(repo.list_summaries()) == 3


def test_cancel_writes_nothing():
    repo = fresh(); commit_import(parse_csv_text(TEMPLATE_CSV), repo, never)
    choices = iter([DuplicateChoice("replace"), None])
    assert commit_import(parse_csv_text(TEMPLATE_CSV), repo, lambda r, e: next(choices)) is None
    assert len(repo.list_summaries()) == 2


def test_failure_mid_import_rolls_back(monkeypatch):
    repo = fresh(); real_add = repo.add; n = {"i": 0}

    def flaky(recipe):
        n["i"] += 1
        if n["i"] == 2: raise RuntimeError("disk full")
        return real_add(recipe)

    monkeypatch.setattr(repo, "add", flaky)
    with pytest.raises(RuntimeError):
        commit_import(parse_csv_text(TEMPLATE_CSV), repo, never)
    assert repo.list_summaries() == []


def test_not_importable_raises():
    with pytest.raises(ValueError):
        commit_import(parse_csv_text("recipe\n"), fresh(), never)


def test_replace_with_several_matches_keeps_one():
    repo = fresh(); commit_import(parse_csv_text(TEMPLATE_CSV), repo, never)
    commit_import(parse_csv_text(TEMPLATE_CSV), repo, lambda r, e: DuplicateChoice("keep_both", True))
    assert len(repo.list_summaries()) == 4
    result = commit_import(parse_csv_text(TEMPLATE_CSV), repo, lambda r, e: DuplicateChoice("replace", True))
    assert result == ImportResult(0, 2, 0)
    assert len(repo.list_summaries()) == 2
