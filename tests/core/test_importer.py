from fractions import Fraction as F

from shopping_list.core.importer import (
    IGNORED_COLUMNS,
    MISSING_COLUMNS,
    NO_ROWS,
    NOT_UTF8,
    SERVINGS_MISMATCH,
    parse_csv_file,
    parse_csv_text,
    revalidate,
)
from shopping_list.core.template import TEMPLATE_CSV
from shopping_list.core.validation import RECIPE_NAME_REQUIRED, UNKNOWN_UNIT

H = "recipe,servings,ingredient,quantity,unit\n"


def test_template_imports_cleanly():
    p = parse_csv_text(TEMPLATE_CSV)
    assert [r.name for r in p.recipes] == ["Pancakes", "Garlic Pasta"]
    warnings = [i for r in p.recipes for row in r.rows for i in row.issues]
    assert [w.message for w in warnings] == [UNKNOWN_UNIT.format(unit="clove")]
    assert p.is_importable
    recipes = p.to_recipes()
    assert recipes[0].servings == 4 and len(recipes[0].ingredients) == 6
    assert recipes[0].ingredients[0].quantity == F(3, 2)


def test_tab_separated_paste_matches_csv():
    tsv = TEMPLATE_CSV.replace(",", "\t")
    assert parse_csv_text(tsv).to_recipes() == parse_csv_text(TEMPLATE_CSV).to_recipes()


def test_headers_case_insensitive_any_order_extra_ignored():
    p = parse_csv_text("Unit, Ingredient ,QUANTITY,notes,Servings,Recipe\ncup,milk,1,x,2,Soup\n")
    assert p.notices == [IGNORED_COLUMNS.format(columns="notes")]
    assert p.to_recipes()[0].ingredients[0].unit == "cup"


def test_duplicate_header_first_wins_later_ignored():
    p = parse_csv_text("recipe,servings,ingredient,quantity,unit,unit\nA,1,egg,1,cup,g\n")
    assert p.to_recipes()[0].ingredients[0].unit == "cup"
    assert p.notices == [IGNORED_COLUMNS.format(columns="unit")]


def test_short_and_long_rows():
    p = parse_csv_text(H + "A,1,egg\nA,1,milk,1,cup,extra,more\n")
    rows = p.recipes[0].rows
    assert (rows[0].quantity, rows[0].unit) == ("", "")
    assert rows[1].unit == "cup"
    assert p.is_importable


def test_missing_column_rejected():
    p = parse_csv_text("recipe,ingredient,quantity,unit\nA,b,1,\n")
    assert [i.message for i in p.file_issues] == [MISSING_COLUMNS.format(missing="servings")]
    assert p.file_issues[0].level == "error" and p.file_issues[0].field is None
    assert not p.is_importable and p.recipes == []


def test_empty_file():
    assert [i.message for i in parse_csv_text("").file_issues] == [NO_ROWS]
    assert [i.message for i in parse_csv_text(H).file_issues] == [NO_ROWS]
    assert [i.message for i in parse_csv_text(H + ",,,,\n\n").file_issues] == [NO_ROWS]


def test_bom_file(tmp_path):
    f = tmp_path / "r.csv"
    f.write_bytes(("﻿" + H + "A,1,egg,1,\n").encode())
    assert parse_csv_file(f).is_importable


def test_non_utf8_file(tmp_path):
    f = tmp_path / "r.csv"
    f.write_bytes((H + "A,1,milk,").encode() + b"\xbd,cup\n")
    p = parse_csv_file(f)
    assert [i.message for i in p.file_issues] == [NOT_UTF8]
    assert p.recipes == [] and not p.is_importable


def test_non_contiguous_grouping_case_insensitive():
    p = parse_csv_text(H + "Soup,2,a,1,\nTea,1,b,1,\n soup ,2,c,1,\n")
    assert [(r.name, [x.ingredient for x in r.rows]) for r in p.recipes] == [
        ("Soup", ["a", "c"]),
        ("Tea", ["b"]),
    ]


def test_servings_mismatch_warning_uses_first():
    p = parse_csv_text(H + "A,4,x,1,\nA,6,y,1,\n")
    assert p.recipes[0].parsed_servings == 4
    assert [i.message for i in p.recipes[0].issues] == [SERVINGS_MISMATCH.format(servings=4)]
    assert p.is_importable


def test_mismatch_warning_survives_revalidate():
    p = parse_csv_text(H + "A,4,x,1,\nA,6,y,1,\n")
    revalidate(p)
    assert [i.message for i in p.recipes[0].issues] == [SERVINGS_MISMATCH.format(servings=4)]


def test_blank_recipe_name_groups_and_blocks():
    p = parse_csv_text(H + ",2,x,1,\nA,1,y,1,\n")
    assert p.recipes[0].name == "" and p.recipes[0].issues[0].message == RECIPE_NAME_REQUIRED
    assert not p.is_importable
    p.recipes[0].skipped = True
    assert revalidate(p).is_importable


def test_row_error_fix_and_skip():
    p = parse_csv_text(H + "A,1,milk,1-2,cup\nA,1,egg,1,\n")
    assert not p.is_importable
    p.recipes[0].rows[0].quantity = "2"
    assert revalidate(p).is_importable
    p.recipes[0].rows[0].quantity = "bad"
    p.recipes[0].rows[0].skipped = True
    assert revalidate(p).is_importable and len(p.to_recipes()[0].ingredients) == 1


def test_all_recipes_skipped_not_importable():
    p = parse_csv_text(H + "A,1,egg,1,\n")
    p.recipes[0].skipped = True
    assert not revalidate(p).is_importable


def test_all_rows_skipped_blocks_recipe():
    p = parse_csv_text(H + "A,1,egg,1,\n")
    p.recipes[0].rows[0].skipped = True
    assert not revalidate(p).is_importable


def test_to_recipes_raises_when_not_importable():
    import pytest

    with pytest.raises(ValueError):
        parse_csv_text("").to_recipes()


def test_line_numbers():
    p = parse_csv_text(H + "A,1,egg,1,\n\nA,1,milk,1,cup\n")
    assert [r.line_no for r in p.recipes[0].rows] == [2, 4]


def test_quoted_comma_cell():
    p = parse_csv_text(H + 'A,1,"salt, kosher",1,tsp\n')
    assert p.to_recipes()[0].ingredients[0].name == "salt, kosher"


def test_blank_rows_ignored():
    p = parse_csv_text(H + "A,1,egg,1,\n,,,,\n\n   ,  ,,,\n")
    assert p.is_importable and len(p.recipes) == 1 and len(p.recipes[0].rows) == 1


def test_crlf_line_endings():
    assert (
        parse_csv_text(TEMPLATE_CSV.replace("\n", "\r\n")).to_recipes()
        == parse_csv_text(TEMPLATE_CSV).to_recipes()
    )


def test_paste_without_header():
    p = parse_csv_text("Pancakes\t4\tflour\t1 1/2\tcup\n")
    assert p.file_issues and p.file_issues[0].message.startswith(
        "Missing required column(s): recipe, servings, ingredient, quantity, unit"
    )


def test_parse_csv_file_directory_is_read_error(tmp_path):
    from shopping_list.core.importer import COULD_NOT_READ, parse_csv_file
    d = tmp_path / "x.csv"
    d.mkdir()
    preview = parse_csv_file(d)
    assert not preview.is_importable
    assert len(preview.file_issues) == 1
    assert preview.file_issues[0].message.startswith("Could not read file: ")
    assert COULD_NOT_READ.startswith("Could not read file")


def test_parse_csv_file_missing_is_read_error(tmp_path):
    from shopping_list.core.importer import parse_csv_file
    preview = parse_csv_file(tmp_path / "nope.csv")
    assert not preview.is_importable
    assert preview.file_issues[0].message.startswith("Could not read file: ")


def test_parse_csv_text_oversized_cell_is_invalid_csv():
    import csv
    from shopping_list.core.importer import parse_csv_text
    big = "a" * (csv.field_size_limit() + 1)
    preview = parse_csv_text("recipe,servings,ingredient,quantity,unit\n" + big + ",1,x,1,\n")
    assert not preview.is_importable
    assert preview.file_issues[0].message.startswith("This doesn't look like a valid CSV: ")
