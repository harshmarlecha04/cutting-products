"""Tests for cuts.py.

The first group checks each calculation on a few made-up stores small enough to work out
by hand. The second group checks the real extracts and that README.md quotes them correctly.

    pytest
"""
import os
import re

import pandas as pd
import pytest

import cuts as c

HERE = os.path.dirname(os.path.abspath(__file__))


# ---- names and sizes -----------------------------------------------------------------------

@pytest.mark.parametrize("description, flavor", [
    ("SMIRNOFF 80PRF", "Original"),
    ("SMIRNOFF 80PRF PET", "Original"),
    ("SMIRNOFF 80PRF MINI", "Original"),
    ("SMIRNOFF 100PRF", "100 Proof"),
    ("SMIRNOFF RED, WHITE & BERRY MINI", "Red, White & Berry"),
    ("SMIRNOFF BLUE RASPBERRY MINI", "Blue Raspberry Lemonade"),
    ("SMIRNOFF BLUE RASPBERRY LEMONADE", "Blue Raspberry Lemonade"),
    ("SMIRNOFF ZERO SUGAR INFUSION CUCUMBER & LIME", "Zero Sugar Cucumber & Lime"),
    ("SMIRNOFF KISSED CARAMEL", "Kissed Caramel"),
    ("Smirnoff Variety Pack Mini", "Variety Pack"),
])
def test_flavor_names(description, flavor):
    assert c.flavor_of(description) == flavor


@pytest.mark.parametrize("unit_ml, description, label", [
    (500, "SMIRNOFF 80PRF MINI", "minis x10"),
    (6000, "SMIRNOFF VARIETY PACK MINI", "minis x120"),
    (750, "SMIRNOFF 80PRF", "750 ml"),
    (750, "SMIRNOFF 80PRF PET", "750 ml plastic"),
    (1000, "SMIRNOFF ORANGE", "1 L"),
    (1750, "SMIRNOFF 80PRF PET", "1.75 L plastic"),
])
def test_format_labels(unit_ml, description, label):
    assert c.format_of(unit_ml, description) == label


# ---- where buyers can go, and what a cut loses ---------------------------------------------
# Three stores. Prices per liter: A = 10, B = 20, C = 10.
#   store 1 buys A (lime, 100 dollars, 10 L) and B (lime in another size, 400 dollars, 20 L)
#   store 2 buys A (50 dollars, 5 L) and C (cherry, 30 dollars, 3 L)
#   store 3 buys only A (20 dollars, 2 L)

def small():
    st = pd.DataFrame([
        ("1", "A", 100.0, 10.0, "Lime"), ("1", "B", 400.0, 20.0, "Lime"),
        ("2", "A", 50.0, 5.0, "Lime"), ("2", "C", 30.0, 3.0, "Cherry"),
        ("3", "A", 20.0, 2.0, "Lime"),
    ], columns=["store_no", "item_no", "sales", "liters", "flavor"])
    p = pd.DataFrame({"per_liter": {"A": 10.0, "B": 20.0, "C": 10.0}, "sales": {"A": 170.0, "B": 400.0, "C": 30.0}})
    return st, p


def test_where_buyers_can_go():
    st, _ = small()
    w = c.where_buyers_can_go(st, ["A"]).set_index("store_no")
    assert w.loc["1", "kind"] == "same flavor" and w.loc["1", "substitute"] == "B"
    assert w.loc["2", "kind"] == "other" and w.loc["2", "substitute"] == "C"
    assert w.loc["3", "kind"] == "nowhere" and pd.isna(w.loc["3", "substitute"])


def test_a_store_that_never_bought_the_product_is_ignored():
    st, _ = small()
    w = c.where_buyers_can_go(st, ["C"])
    assert list(w["store_no"]) == ["2"]


def test_loss_when_nothing_moves_is_the_sales_removed():
    st, p = small()
    assert c.loss(st, p, ["A"], 0, 0)[0] == pytest.approx(170)


def test_loss_by_hand():
    st, p = small()
    # store 1: half of 10 L moves to B at 20 a liter = 100 kept, so 0 lost
    # store 2: a quarter of 5 L moves to C at 10 a liter = 12.50 kept, so 37.50 lost
    # store 3: nothing to move to, so 20 lost
    total, w = c.loss(st, p, ["A"], 0.5, 0.25)
    assert total == pytest.approx(0 + 37.5 + 20)
    assert w.set_index("store_no").loc["1", "kept"] == pytest.approx(100)


def test_a_substitute_that_is_also_cut_does_not_count():
    st, p = small()
    w = c.where_buyers_can_go(st, ["A", "B"]).set_index(["store_no", "item_no"])
    assert w.loc[("1", "A"), "kind"] == "nowhere" and w.loc[("1", "B"), "kind"] == "nowhere"
    assert c.loss(st, p, ["A", "B"], 0.5, 0.25)[0] == pytest.approx(100 + 400 + 37.5 + 20)


def test_moving_to_a_dearer_size_can_bring_in_more_than_was_lost():
    st, p = small()
    total, _ = c.loss(st, p, ["A"], 1.0, 0.0)
    # store 1 keeps 10 L at 20 = 200 against 100 removed, a gain of 100. Stores 2 and 3 lose 70.
    assert total == pytest.approx(-100 + 50 + 20)


def test_naive_cut_takes_the_smallest():
    _, p = small()
    assert c.naive_cut(p, 2) == ["C", "A"]


def test_lowest_loss_cut_prefers_the_product_with_somewhere_to_go():
    st = pd.DataFrame([
        ("1", "A", 100.0, 10.0, "Lime"), ("1", "B", 400.0, 40.0, "Lime"),     # A has a same-flavor substitute
        ("1", "D", 90.0, 9.0, "Cherry"),                                      # D is smaller but has none
    ], columns=["store_no", "item_no", "sales", "liters", "flavor"])
    p = pd.DataFrame({"per_liter": {"A": 10.0, "B": 10.0, "D": 10.0}, "sales": {"A": 100.0, "B": 400.0, "D": 90.0}})
    assert c.naive_cut(p, 1) == ["D"]
    chosen, total = c.lowest_loss_cut(st, p, 1, 0.5, 0.25, ["A", "B", "D"])
    assert chosen == ["A"] and total == pytest.approx(50)                     # D would lose 90 - 0.25 * 9 * 10 = 67.50


def test_by_store_and_dataframe_give_the_same_answer():
    st, p = small()
    assert c.loss(c.by_store(st), p, ["A"], 0.5, 0.25)[0] == pytest.approx(c.loss(st, p, ["A"], 0.5, 0.25)[0])


# ---- the real extracts ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def r():
    return c.run()


@pytest.fixture(scope="module")
def f(r):
    return c.facts(r)


def test_product_totals_add_up_to_the_invoice_lines(r):
    assert r["p"]["sales"].sum() == pytest.approx(r["d"]["lines"]["sales_dollars"].sum())
    assert r["p"]["stores"].max() <= r["d"]["lines"]["store_no"].nunique()


def test_every_product_sold_is_on_the_state_product_list(r):
    assert set(r["p"].index) <= set(r["d"]["plist"]["item_no"])


def test_minis_are_counted_as_sleeves_of_ten(r):
    minis = r["p"][r["p"]["format"] == "minis x10"]
    assert len(minis) == 8 and (minis["unit_ml"] == 500).all()
    assert (minis["per_liter_as_filed"] > 100).all()                  # the trap
    assert minis["per_liter"].between(13, 15).all()                   # the corrected figure


def test_price_per_liter_matches_the_state_price_list(r):
    pl = r["d"]["plist"].set_index("item_no")
    item = "37996"                                                    # Original 750 ml
    listed = float(pl.loc[item, "state_bottle_retail"]) / 0.75
    assert r["p"].loc[item, "per_liter"] == pytest.approx(listed, rel=0.01)


def test_new_and_seasonal_products(r):
    p = r["p"]
    assert sorted(p[p["is_new"]]["name"]) == ["Electric Guava, 750 ml", "Electric Guava, minis x10", "Kissed Caramel, minis x10", "Variety Pack, minis x120"]
    assert list(p[p["is_seasonal"]]["name"]) == ["Peppermint Twist, 750 ml"]
    assert len(r["judged"]) == 46


def test_cuts_are_the_right_size_and_come_from_the_judged_products(r):
    assert len(r["smallest"]) == len(r["lowest"]) == 10
    assert set(r["smallest"]) <= set(r["judged"]) and set(r["lowest"]) <= set(r["judged"])
    assert len(r["smallest_all"]) == 10


def test_lowest_loss_cut_really_loses_less_under_its_own_assumption(r):
    t = r["table"]
    assert t.loc["Ten with the lowest loss", "Some moves"] < t.loc["Ten smallest sellers", "Some moves"]
    assert (t["Nothing moves"] - t["sales removed"]).abs().max() < 1e-6


def test_gone_means_no_sale_after_february_2026(r):
    p = r["p"]
    for key in r["gone"]:
        last = p.loc[key, "last_sale_2026"]
        assert pd.isna(last) or last <= c.GONE_AFTER
    still = p[~p["gone_2026"]]
    assert (still["last_sale_2026"] > c.GONE_AFTER).all()


def test_readme_quotes_the_data(r, f):
    text = open(os.path.join(HERE, "README.md"), encoding="utf-8").read()
    p = r["p"]

    def has(s):
        assert s in text, s

    def k(v):
        return f"${round(v / 1000):,}K"

    has(f"{f['lines']:,} invoice lines from {f['stores']:,} stores")
    has(f"{f['products']} products")
    has(f"${f['sales'] / 1e6:.1f} million")
    has(f"${f['sales_2024'] / 1e6:.1f} million in 2024")
    has(f"is {f['top_product_share']:.0%} of sales on its own")
    has(f"five biggest are {f['top5_share']:.0%}")
    has(f"smaller-selling half of the range, 26 products, is {f['bottom_half_share']:.1%}")
    has(f"{k(f['smallest_all_sales'])}, or {f['smallest_all_share']:.1%}")
    has(f"${f['minis_as_filed']:.0f} a liter")
    has(f"${f['per_liter_minis']:.2f} a liter")
    for key in ("375", "200", "750", "1000", "1750"):
        has(f"${f['per_liter_' + key]:.2f}")
    has(f"{f['per_liter_375'] / f['per_liter_1750'] - 1:.0%} more")
    has(f"earn ${f['per_liter_smallest_all']:.2f} a liter between them, against ${f['per_liter_brand']:.2f}")
    has(f"rank 2nd and {int(p.loc['37993', 'rank'])}th")
    has(f"leaves {f['n_judged']}")
    has(f"{k(f['smallest_sales'])}, or {f['smallest_share']:.1%}")
    has(f"{f['second_per_store_stores']} stores, and each spent ${f['second_per_store']:,.0f}")
    has(f"ranks {f['second_per_store_rank']}th")
    has(f"between {f['smallest_stores_min']} and {f['smallest_stores_max']} stores")
    has(f"${f['smallest_per_store_min']:.0f} to ${f['smallest_per_store_max']:.0f}")
    for key in ("smallest", "lowest", "gone"):
        has(f"{k(f[key + '_loss_nothing'])} | {k(f[key + '_loss_some'])} | {k(f[key + '_loss_most'])}")
    has(f"{f['smallest_same_flavor']:.0%}")
    has(f"{f['lowest_same_flavor']:.0%}")
    has(f"{f['gone_same_flavor']:.0%}")
    has(f"{f['overlap']} of the same ten")
    has(f"saves {k(f['saving_some'])}")
    has(f"{k(f['saving_most'])} if most of it moves")
    has(f"loses {k(-f['saving_nothing'])} more")
    has(f"through {pd.Timestamp(f['data_through']).strftime('%B')} {pd.Timestamp(f['data_through']).day}")
    has(f"Nine of the {f['products']}") if f["n_gone"] == 9 else pytest.fail("write-up says nine")
    has(f"{k(f['gone_sales'])}, or {f['gone_share']:.1%}")
    has(f"ranked {f['gone_best_rank']}th or lower")
    has(f"had six of the nine") if f["gone_in_smallest_all"] == 6 else pytest.fail("write-up says six")
    has(f"sales rank had five and my list had four") if (f["gone_judged"], f["gone_in_smallest"], f["gone_in_lowest"]) == (6, 5, 4) else pytest.fail("write-up says 6, 5, 4")
    has("Three of the four") if (f["new_gone"], f["n_new"]) == (3, 4) else pytest.fail("write-up says three of four")
    has("Four new products") if f["new_in_2026"] == 4 else pytest.fail("write-up says four new")
    tests = len(re.findall(r"^def test_", open(os.path.join(HERE, "test_cuts.py"), encoding="utf-8").read(), re.M))
    has(f"{tests} test functions")
