import pytest
from shopping_list.core.names import IRREGULAR, UNCHANGED, name_key

@pytest.mark.parametrize("name,key", [
    ("  Olive   Oil ", "olive oil"), ("EGG", "egg"), ("", ""),          # step 1
    ("gas", "gas"), ("abs", "abs"),                                       # <= 3 letters
    ("berries", "berry"), ("anchovies", "anchovy"),                       # ies -> y
    ("tomatoes", "tomato"), ("potatoes", "potato"),                       # oes
    ("peaches", "peach"), ("radishes", "radish"), ("glasses", "glass"),
    ("boxes", "box"), ("topazes", "topaz"),                               # ches/shes/sses/xes/zes
    ("asparagus", "asparagus"), ("hummus", "hummus"), ("couscous", "couscous"),
    ("watercress", "watercress"), ("pastis", "pastis"),                   # ss/us/is
    ("onions", "onion"), ("eggs", "egg"), ("peas", "pea"), ("cloves", "clove"),  # s
    ("onion", "onion"), ("leaf", "leaf"),                                 # already singular
    ("green onions", "green onion"), ("Bay Leaves", "bay leaf"),
    ("peas and carrots", "peas and carrot"), ("cherry  tomatoes", "cherry tomato"),  # last word only
])
def test_name_key(name, key):
    assert name_key(name) == key

@pytest.mark.parametrize("plural,singular", sorted(IRREGULAR.items()))
def test_every_irregular_entry(plural, singular):
    assert name_key(plural) == singular and name_key(singular) == singular
    assert name_key(f"fresh {plural}") == f"fresh {singular}"

@pytest.mark.parametrize("word", sorted(UNCHANGED))
def test_every_unchanged_entry(word):
    assert name_key(word) == word and name_key(word.title()) == word
