"""Ingredient name normalization: case, whitespace and plurals only."""

IRREGULAR = {
    "leaves": "leaf",
    "halves": "half",
    "loaves": "loaf",
    "cookies": "cookie",
    "brownies": "brownie",
    "veggies": "veggie",
}
UNCHANGED = {"molasses", "swiss", "grits", "series"}

_ES_SUFFIXES = ("ches", "shes", "sses", "xes", "zes")


def _singular(word: str) -> str:
    if word in IRREGULAR:
        return IRREGULAR[word]
    if word in UNCHANGED or len(word) <= 3:
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("oes") or word.endswith(_ES_SUFFIXES):
        return word[:-2]
    if word.endswith(("ss", "us", "is")):
        return word
    if word.endswith("s"):
        return word[:-1]
    return word


def name_key(name: str) -> str:
    """Return the matching key: lowercased, whitespace-collapsed, last word singularized."""
    words = name.lower().split()
    if not words:
        return ""
    words[-1] = _singular(words[-1])
    return " ".join(words)
