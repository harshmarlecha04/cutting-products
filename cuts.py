"""Which products could a brand drop, and what would it lose?

Works on the files in data/, which are extracts of the State of Iowa's liquor sales
(see get_data.py). The brand is Smirnoff, the year is 2025, and a "sale" is a store
buying from the state's wholesale warehouse.

    python cuts.py          # prints the product table and the comparison of cuts
"""
import os
import re

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
GONE_AFTER = "2026-02-28"      # a product with no sales after this date in 2026 counts as gone
N_CUT = 10

SCENARIOS = {                  # share of a cut product's liters that stay with the brand, by where the store can turn
    "Nothing moves": (0.0, 0.0),
    "Some moves": (0.5, 0.25),
    "Most moves": (0.8, 0.5),
}


# ---- reading -------------------------------------------------------------------------------

def load(folder=DATA):
    lines = pd.read_csv(os.path.join(folder, "lines_2025.csv"), dtype=str)
    for col in ("sales_bottles", "sales_dollars", "sales_liters", "bottle_volume_ml"):
        lines[col] = lines[col].astype(float)
    plist = pd.read_csv(os.path.join(folder, "product_list.csv"), dtype=str)
    y24 = pd.read_csv(os.path.join(folder, "by_product_2024.csv"), dtype={"item_no": str})
    y26 = pd.read_csv(os.path.join(folder, "by_product_2026.csv"), dtype={"item_no": str})
    return {"lines": lines, "plist": plist, "y24": y24, "y26": y26}


def flavor_of(description):
    """'SMIRNOFF RED, WHITE & BERRY MINI' -> 'Red, White & Berry'."""
    s = re.sub(r"^SMIRNOFF\s+", "", description.upper().strip())
    s = re.sub(r"\b(MINI|PET)\b", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    fixed = {
        "80PRF": "Original",
        "100PRF": "100 Proof",
        "BLUE RASPBERRY": "Blue Raspberry Lemonade",     # the state lists the mini without 'Lemonade'
        "VARIETY PACK": "Variety Pack",
    }
    if s in fixed:
        return fixed[s]
    s = s.replace("ZERO SUGAR INFUSION ", "Zero Sugar ")
    return " ".join(w if w in ("&",) else w.capitalize() for w in s.split())


def format_of(unit_ml, description):
    plastic = " plastic" if re.search(r"\bPET\b", description.upper()) else ""
    if unit_ml == 500:
        return "minis x10"
    if unit_ml == 6000:
        return "minis x120"
    if unit_ml >= 1000:
        return f"{unit_ml / 1000:g} L{plastic}"
    return f"{unit_ml:g} ml{plastic}"


def products(d):
    """One row per product sold in 2025, with everything the six steps need."""
    lines, plist = d["lines"], d["plist"].set_index("item_no")
    lines = lines.assign(month=lines["ordered_on"].str[:7])
    g = lines.groupby("item_no").agg(
        description=("im_desc", "first"), bottle_ml=("bottle_volume_ml", "first"),
        sales=("sales_dollars", "sum"), units=("sales_bottles", "sum"), state_liters=("sales_liters", "sum"),
        stores=("store_no", "nunique"), lines=("invoice_id", "count"),
        months=("month", "nunique"), first_sale=("ordered_on", "min"), last_sale=("ordered_on", "max"))
    g["inner_pack"] = plist["inner_pack"].reindex(g.index).astype(float).fillna(1)
    g["unit_ml"] = g["bottle_ml"] * g["inner_pack"]            # what one unit sold actually holds
    g["liters"] = g["units"] * g["unit_ml"] / 1000
    g["per_liter"] = g["sales"] / g["liters"]
    g["per_liter_as_filed"] = g["sales"] / g["state_liters"]   # what you get if you trust the file's liters
    g["flavor"] = g["description"].map(flavor_of)
    g["format"] = [format_of(u, desc) for u, desc in zip(g["unit_ml"], g["description"])]
    g["name"] = g["flavor"] + ", " + g["format"]
    g["per_store"] = g["sales"] / g["stores"]
    g["sales_2024"] = d["y24"].set_index("item_no")["sales_dollars"].reindex(g.index).fillna(0.0)
    g["is_new"] = g["sales_2024"] == 0
    g["is_seasonal"] = (g["months"] <= 5) & ~g["is_new"]
    y26 = d["y26"].set_index("item_no")
    g["sales_2026"] = y26["sales_dollars"].reindex(g.index).fillna(0.0)
    g["last_sale_2026"] = y26["last_sale"].reindex(g.index)
    g["gone_2026"] = g["last_sale_2026"].isna() | (g["last_sale_2026"] <= GONE_AFTER)
    g["rank"] = g["sales"].rank(ascending=False).astype(int)
    g["share"] = g["sales"] / g["sales"].sum()
    return g.sort_values("sales", ascending=False)


def by_size(p):
    """Price per liter for each size the brand sells, using corrected liters."""
    t = p.groupby("unit_ml").agg(products=("sales", "size"), sales=("sales", "sum"), liters=("liters", "sum")).reset_index()
    t["per_liter"] = t["sales"] / t["liters"]
    t["share_of_sales"] = t["sales"] / t["sales"].sum()
    return t


# ---- what a cut would lose -----------------------------------------------------------------

def store_table(d, p):
    """Dollars and (corrected) liters for every store and product."""
    t = d["lines"].groupby(["store_no", "item_no"]).agg(sales=("sales_dollars", "sum"), units=("sales_bottles", "sum")).reset_index()
    t["liters"] = t["units"] * t["item_no"].map(p["unit_ml"]) / 1000
    t["flavor"] = t["item_no"].map(p["flavor"])
    return t


def by_store(st):
    """{store: [(item, sales, liters, flavor), ...]} with each store's biggest product first."""
    out = {}
    for r in st.sort_values("liters", ascending=False).itertuples():
        out.setdefault(r.store_no, []).append((r.item_no, r.sales, r.liters, r.flavor))
    return out


def where_buyers_can_go(st, cut):
    """For each cut product: its sales split by what the store still stocks.

    same flavor   the store buys the same flavor in another size or container
    other         the store buys some other product of the brand
    nowhere       it was the store's only product of the brand
    The substitute is whichever of those the store buys most of, by liters.
    """
    cut = set(cut)
    stores = st if isinstance(st, dict) else by_store(st)
    rows = []
    for store, items in stores.items():
        stay = [x for x in items if x[0] not in cut]
        if len(stay) == len(items):
            continue
        for item, sales, liters, flavor in items:
            if item not in cut:
                continue
            same = next((x[0] for x in stay if x[3] == flavor), None)
            if same is not None:
                rows.append((store, item, sales, liters, "same flavor", same))
            elif stay:
                rows.append((store, item, sales, liters, "other", stay[0][0]))
            else:
                rows.append((store, item, sales, liters, "nowhere", None))
    return pd.DataFrame(rows, columns=["store_no", "item_no", "sales", "liters", "kind", "substitute"])


def loss(st, p, cut, t_same, t_other):
    """Dollars lost if `cut` is dropped.

    A share of each cut product's liters moves to what the store still stocks (t_same if the
    same flavor is there in another size, t_other if only another product of the brand is),
    and is paid for at that product's price per liter. The rest is lost.
    """
    w = where_buyers_can_go(st, cut)
    if w.empty:
        return 0.0, w.assign(kept=[], lost=[])
    rate = w["kind"].map({"same flavor": t_same, "other": t_other, "nowhere": 0.0})
    price = w["substitute"].map(p["per_liter"]).fillna(0.0)
    w["kept"] = rate * w["liters"] * price
    w["lost"] = w["sales"] - w["kept"]
    return float(w["lost"].sum()), w


def lowest_loss_cut(st, p, n, t_same, t_other, candidates):
    """Pick n products one at a time, each time the one that adds the least loss to the cut so far."""
    chosen, total = [], 0.0
    pool = list(candidates)
    while len(chosen) < n and pool:
        best = None
        for k in pool:
            value, _ = loss(st, p, chosen + [k], t_same, t_other)
            if best is None or value < best[1]:
                best = (k, value)
        chosen.append(best[0])
        pool.remove(best[0])
        total = best[1]
    return chosen, total


def naive_cut(p, n):
    return list(p.sort_values("sales").index[:n])


def compare(st, p, cuts):
    """Loss for each named cut under each scenario, plus plain sales removed."""
    rows = []
    for name, cut in cuts.items():
        row = {"cut": name, "products": len(cut), "sales removed": float(p.loc[cut, "sales"].sum())}
        for scenario, (a, b) in SCENARIOS.items():
            row[scenario] = loss(st, p, cut, a, b)[0]
        rows.append(row)
    return pd.DataFrame(rows).set_index("cut")


def run(d=None):
    """Everything the write-up needs, computed once."""
    d = d or load()
    p = products(d)
    st = by_store(store_table(d, p))
    judged = list(p.index[~p["is_new"] & ~p["is_seasonal"]])
    smallest_all = naive_cut(p, N_CUT)
    smallest = naive_cut(p.loc[judged], N_CUT)
    a, b = SCENARIOS["Some moves"]
    lowest, _ = lowest_loss_cut(st, p, N_CUT, a, b, judged)
    gone = list(p.index[p["gone_2026"] & ~p["is_seasonal"]])
    cuts = {"Ten smallest sellers": smallest, "Ten with the lowest loss": lowest, "The nine that stopped selling": gone}
    return {"d": d, "p": p, "st": st, "judged": judged, "smallest_all": smallest_all, "smallest": smallest,
            "lowest": lowest, "gone": gone, "cuts": cuts, "table": compare(st, p, cuts)}


def facts(r=None):
    """Every number quoted in the write-up, in one place."""
    r = r or run()
    p, st, d = r["p"], r["st"], r["d"]
    total = p["sales"].sum()
    cum = p["sales"].cumsum() / total
    size = by_size(p).set_index("unit_ml")
    gone, judged = set(r["gone"]), set(r["judged"])
    f = {
        "products": len(p), "stores": d["lines"]["store_no"].nunique(), "lines": len(d["lines"]),
        "sales": total, "sales_2024": d["y24"]["sales_dollars"].sum(),
        "top5_share": cum.iloc[4], "top_product_share": p["share"].iloc[0],
        "n_for_90": int((cum < 0.9).sum() + 1), "bottom_half_share": p["sales"].iloc[-(len(p) // 2 + 1):].sum() / total,
        "smallest_all_sales": p.loc[r["smallest_all"], "sales"].sum(),
        "smallest_all_share": p.loc[r["smallest_all"], "sales"].sum() / total,
        "per_liter_brand": total / p["liters"].sum(),
        "per_liter_smallest_all": p.loc[r["smallest_all"], "sales"].sum() / p.loc[r["smallest_all"], "liters"].sum(),
        "per_liter_375": size.loc[375, "per_liter"], "per_liter_200": size.loc[200, "per_liter"],
        "per_liter_750": size.loc[750, "per_liter"], "per_liter_1000": size.loc[1000, "per_liter"],
        "per_liter_minis": size.loc[500, "per_liter"], "per_liter_1750": size.loc[1750, "per_liter"],
        "minis_as_filed": p.loc[p["unit_ml"] == 500, "sales"].sum() / p.loc[p["unit_ml"] == 500, "state_liters"].sum(),
        "n_new": int(p["is_new"].sum()), "n_seasonal": int(p["is_seasonal"].sum()), "n_judged": len(judged),
        "new_gone": int((p["is_new"] & p["gone_2026"]).sum()),
        "smallest_sales": p.loc[r["smallest"], "sales"].sum(), "smallest_share": p.loc[r["smallest"], "sales"].sum() / total,
        "lowest_sales": p.loc[r["lowest"], "sales"].sum(),
        "overlap": len(set(r["smallest"]) & set(r["lowest"])),
        "n_gone": len(gone), "gone_sales": p.loc[r["gone"], "sales"].sum(), "gone_share": p.loc[r["gone"], "sales"].sum() / total,
        "gone_best_rank": int(p.loc[r["gone"], "rank"].min()),
        "gone_in_smallest_all": len(gone & set(r["smallest_all"])),
        "gone_judged": len(gone & judged),
        "gone_in_smallest": len(gone & set(r["smallest"])), "gone_in_lowest": len(gone & set(r["lowest"])),
        "new_in_2026": int((~d["y26"]["item_no"].isin(p.index)).sum()),
        "data_through": d["y26"]["last_sale"].max(),
    }
    pl = d["plist"]
    pl = pl[pl["item_no"].isin(p.index)]
    markup = pl["state_bottle_retail"].astype(float) / pl["state_bottle_cost"].astype(float)
    f["markup_min"], f["markup_max"] = float(markup.min()), float(markup.max())
    small = p.loc[r["smallest"]]
    f["smallest_stores_min"], f["smallest_stores_max"] = int(small["stores"].min()), int(small["stores"].max())
    f["smallest_per_store_min"], f["smallest_per_store_max"] = float(small["per_store"].min()), float(small["per_store"].max())
    by_rate = p.sort_values("per_store", ascending=False)
    f["second_per_store_name"] = by_rate["name"].iloc[1]
    f["second_per_store"], f["second_per_store_stores"], f["second_per_store_rank"] = float(by_rate["per_store"].iloc[1]), int(by_rate["stores"].iloc[1]), int(by_rate["rank"].iloc[1])
    for name, cut in r["cuts"].items():
        w = where_buyers_can_go(st, cut)
        split = w.groupby("kind")["sales"].sum() / w["sales"].sum()
        key = {"Ten smallest sellers": "smallest", "Ten with the lowest loss": "lowest", "The nine that stopped selling": "gone"}[name]
        for kind in ("same flavor", "other", "nowhere"):
            f[f"{key}_{kind.replace(' ', '_')}"] = float(split.get(kind, 0.0))
        for scenario in SCENARIOS:
            f[f"{key}_loss_{scenario.split()[0].lower()}"] = float(r["table"].loc[name, scenario])
    f["saving_some"] = f["smallest_loss_some"] - f["lowest_loss_some"]
    f["saving_most"] = f["smallest_loss_most"] - f["lowest_loss_most"]
    f["saving_nothing"] = f["smallest_loss_nothing"] - f["lowest_loss_nothing"]
    return f


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    pd.set_option("display.max_rows", 100)
    r = run()
    p = r["p"]
    show = p[["name", "sales", "share", "stores", "per_store", "per_liter", "sales_2024", "is_new", "is_seasonal", "gone_2026"]]
    print(show.round({"sales": 0, "share": 3, "per_store": 0, "per_liter": 2, "sales_2024": 0}).to_string())
    print()
    print(by_size(p).round(2).to_string(index=False))
    print()
    for name, cut in r["cuts"].items():
        print(f"{name}: " + "; ".join(p.loc[k, "name"] for k in cut))
    print()
    print(r["table"].round(0).to_string())
    print()
    for k, v in facts(r).items():
        print(f"{k:26s} {v:,.4f}" if isinstance(v, float) else f"{k:26s} {v}")
