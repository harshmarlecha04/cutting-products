"""Rebuilds the files in data/ from the State of Iowa's own downloads.

You do not need to run this. The extracts are already in data/. It is here so anyone
can check that they are what I say they are.

    python get_data.py                 # downloads about 1.7 GB from the Iowa Data Hub
    python get_data.py --keep raw/     # same, and keeps the downloads in raw/

Source: Iowa Department of Revenue, Alcoholic Beverages Division, via the Iowa Data Hub
(https://data.iowa.gov), licensed CC BY 4.0.
  Iowa Liquor Sales, 2024 / 2025 / 2026   dataset ids 1261, 1262, 1263
  Iowa Liquor Products                    dataset id 1029
"""
import argparse
import io
import os
import shutil
import tempfile
import urllib.request
import zipfile

import pandas as pd

BRAND = "SMIRNOFF"
API = "https://idh-be.iowa.gov/api/v1/datasets/{id}/rows.csv"
SALES = {2024: 1261, 2025: 1262, 2026: 1263}
PRODUCTS = 1029
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data")
COLS = ["invoice_id", "ordered_on", "store_no", "store_name", "store_city", "county_name", "item_no", "im_desc",
        "bottle_volume_ml", "pack", "sales_bottles", "sales_dollars", "sales_liters"]


def fetch(dataset_id, folder):
    """Download one dataset (the state serves a zip of CSV parts) and return the path."""
    path = os.path.join(folder, f"{dataset_id}.zip")
    if not os.path.exists(path):
        print(f"downloading dataset {dataset_id} ...")
        request = urllib.request.Request(API.format(id=dataset_id), headers={"User-Agent": "Mozilla/5.0 (get_data.py)"})   # the site refuses Python's default
        with urllib.request.urlopen(request) as response, open(path, "wb") as out:
            shutil.copyfileobj(response, out)
    return path


def read_zip(path, usecols=None, keep=None):
    """Read every CSV part in a zip, keeping only the rows `keep` selects, to save memory."""
    parts = []
    with zipfile.ZipFile(path) as z:
        for name in sorted(z.namelist()):
            with z.open(name) as f:
                for chunk in pd.read_csv(io.TextIOWrapper(f, encoding="utf-8"), usecols=usecols, dtype=str, chunksize=250_000, keep_default_na=False):
                    parts.append(chunk[keep(chunk)] if keep else chunk)
    return pd.concat(parts, ignore_index=True)


def is_brand(chunk):
    return chunk["im_desc"].str.upper().str.startswith(BRAND)


def by_product(lines):
    num = lines.assign(sales_dollars=lines["sales_dollars"].astype(float), sales_bottles=lines["sales_bottles"].astype(float), sales_liters=lines["sales_liters"].astype(float))
    g = num.groupby(["item_no", "im_desc", "bottle_volume_ml"]).agg(
        sales_dollars=("sales_dollars", "sum"), sales_bottles=("sales_bottles", "sum"), sales_liters=("sales_liters", "sum"),
        stores=("store_no", "nunique"), first_sale=("ordered_on", "min"), last_sale=("ordered_on", "max")).reset_index()
    g["sales_dollars"] = g["sales_dollars"].round(2)
    g["sales_liters"] = g["sales_liters"].round(2)
    g["sales_bottles"] = g["sales_bottles"].astype(int)
    return g.sort_values("item_no")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", help="folder to keep the raw downloads in")
    args = ap.parse_args()
    folder = args.keep or tempfile.mkdtemp()
    os.makedirs(folder, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)

    lines = {year: read_zip(fetch(i, folder), COLS, is_brand) for year, i in SALES.items()}

    main_year = lines[2025].sort_values(["ordered_on", "invoice_id"])
    main_year.to_csv(os.path.join(OUT, "lines_2025.csv"), index=False)
    by_product(lines[2024]).to_csv(os.path.join(OUT, "by_product_2024.csv"), index=False)
    by_product(lines[2026]).to_csv(os.path.join(OUT, "by_product_2026.csv"), index=False)
    through = lines[2026]["ordered_on"].max()

    products = read_zip(fetch(PRODUCTS, folder), None, is_brand)
    keep = ["item_no", "im_desc", "category_name", "bottle_volume_ml", "pack", "inner_pack", "proof", "list_on", "state_bottle_cost", "state_bottle_retail", "report_as_of"]
    products[keep].drop_duplicates(["item_no"]).sort_values("item_no").to_csv(os.path.join(OUT, "product_list.csv"), index=False)

    print(f"lines_2025.csv        {len(main_year):,} invoice lines")
    print(f"by_product_2024.csv   {lines[2024]['item_no'].nunique()} products")
    print(f"by_product_2026.csv   {lines[2026]['item_no'].nunique()} products, sales through {through}")
    print(f"product_list.csv      {products['item_no'].nunique()} products")


if __name__ == "__main__":
    main()
