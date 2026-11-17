"""Draws the six charts in charts/. Blue marks the thing to look at, gray is context.

    python charts.py

Set CHART_FONT_DIR to a folder of .ttf files to use your own typeface.
"""
import glob
import logging
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter

import cuts as c

logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "charts")
INK, MUTED, GRID, BLUE, GRAY, PALE = "#000000", "#5f5f5f", "#e4e4e4", "#1433ff", "#9a9a9a", "#b9c4ff"

for path in glob.glob(os.path.join(os.environ.get("CHART_FONT_DIR", ""), "*.ttf")) if os.environ.get("CHART_FONT_DIR") else []:
    font_manager.fontManager.addfont(path)
plt.rcParams.update({
    "font.family": ["Geist", "Inter", "Arial", "DejaVu Sans"],
    "font.size": 10.5, "text.color": INK, "axes.labelcolor": MUTED,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.edgecolor": GRID,
    "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
})


def money(v, _=None):
    if abs(v) >= 1e6:
        return f"${v / 1e6:g}M"
    if abs(v) >= 1e3:
        return f"${v / 1e3:g}K"
    return f"${v:g}"


def frame(title, subtitle, height=4.4, left=0.08, right=0.95, bottom=0.12, top=0.80):
    fig, ax = plt.subplots(figsize=(8, height), dpi=200)
    fig.subplots_adjust(left=left, right=right, top=top, bottom=bottom)
    fig.text(0.04, 1 - 0.24 / height, title, fontsize=14, fontweight=500, ha="left", va="top")
    fig.text(0.04, 1 - 0.55 / height, subtitle, fontsize=10, color=MUTED, ha="left", va="top")
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#bdbdbd")
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0, labelsize=9.5)
    return fig, ax


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    fig.savefig(path)
    plt.close(fig)
    return path


def chart_tail(r, f):
    p = r["p"]
    small = set(r["smallest_all"])
    fig, ax = frame("51 products, ranked by what stores bought in 2025",
                    f"The five biggest are {f['top5_share']:.0%} of sales. The ten smallest, in blue, are {f['smallest_all_share']:.1%}.")
    colors = [BLUE if k in small else GRAY for k in p.index]
    ax.bar(range(1, len(p) + 1), p["sales"], color=colors, width=0.72)
    ax.yaxis.set_major_formatter(FuncFormatter(money))
    ax.set_xlim(0.2, len(p) + 0.8)
    ax.set_xticks([1, 10, 20, 30, 40, 51])
    ax.set_xlabel("Rank by sales", fontsize=9.5)
    ax.annotate(p["name"].iloc[0], (1.5, p["sales"].iloc[0]), xytext=(8, -4), textcoords="offset points", fontsize=9.5, va="top")
    ax.annotate(f"The ten smallest:\n{money(round(f['smallest_all_sales'], -3))} between them", (46.5, p["sales"].iloc[41]),
                xytext=(0, 46), textcoords="offset points", fontsize=9.5, ha="center",
                arrowprops={"arrowstyle": "-", "color": "#bdbdbd", "linewidth": 0.8})
    fig.subplots_adjust(bottom=0.15)
    return save(fig, "1-the-tail.png")


def chart_per_liter(r, f):
    rows = [("375 ml", f["per_liter_375"]), ("200 ml", f["per_liter_200"]), ("750 ml", f["per_liter_750"]),
            ("1 L", f["per_liter_1000"]), ("Minis, 50 ml", f["per_liter_minis"]), ("1.75 L", f["per_liter_1750"])]
    fig, ax = frame("What a liter earns in each bottle size",
                    "Dollars per liter at the price stores pay the state. Minis counted as the sleeves of ten they are sold in.",
                    height=3.5, left=0.17, right=0.9, bottom=0.06, top=0.74)
    ax.grid(False)
    ax.spines["bottom"].set_visible(False)
    for i, (name, v) in enumerate(rows):
        y = len(rows) - 1 - i
        ax.barh(y, v, height=0.5, color=BLUE if i == 0 else GRAY)
        ax.text(v + 0.25, y, f"${v:.2f}", va="center", fontsize=10, fontweight=500)
    ax.set_yticks(range(len(rows)), [x[0] for x in rows][::-1], fontsize=10, color=INK)
    ax.set_xticks([])
    ax.set_xlim(0, 23)
    return save(fig, "2-per-liter.png")


def chart_small_vs_price(r, f):
    p = r["p"]
    small = set(r["smallest_all"])
    fig, ax = frame("Do the smallest sellers earn the most per liter? No.",
                    f"Each dot is a product. The ten smallest sellers, in blue, earn ${f['per_liter_smallest_all']:.2f} a liter between them.",
                    left=0.08, right=0.95, bottom=0.15)
    rest = p[~p.index.isin(small)]
    blue = p[p.index.isin(small)]
    ax.scatter(rest["sales"], rest["per_liter"], s=42, color=GRAY, edgecolor="white", linewidth=1.2, label="Other products", zorder=3)
    ax.scatter(blue["sales"], blue["per_liter"], s=48, color=BLUE, edgecolor="white", linewidth=1.2, label="Ten smallest sellers", zorder=4)
    ax.axhline(f["per_liter_brand"], color=INK, linewidth=0.8)
    ax.text(p["sales"].min() * 0.8, f["per_liter_brand"] + 0.12, f"All Smirnoff: ${f['per_liter_brand']:.2f} a liter", fontsize=9.5, va="bottom")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(FuncFormatter(money))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:g}"))
    ax.set_ylim(11.5, 21)
    ax.set_xlabel("2025 sales, log scale", fontsize=9.5)
    for key, dx, dy, ha in (("37994", -8, 0, "right"), ("38008", -8, 0, "right"), ("37993", -8, 0, "right"), ("39866", 8, 0, "left")):
        ax.annotate(p.loc[key, "name"], (p.loc[key, "sales"], p.loc[key, "per_liter"]), xytext=(dx, dy), textcoords="offset points", fontsize=9, ha=ha, va="center")
    ax.legend(loc="upper left", frameon=False, fontsize=9, handletextpad=0.2, borderaxespad=0.1, bbox_to_anchor=(0.0, 0.93))
    return save(fig, "3-small-vs-price.png")


def chart_reach(r, f):
    p = r["p"]
    small = set(r["smallest"])
    fig, ax = frame("Small because few stores stock it, or small everywhere?",
                    "Stores that bought each product in 2025, against what each of those stores spent on it.",
                    left=0.09, right=0.95, bottom=0.15)
    rest = p[~p.index.isin(small)]
    blue = p[p.index.isin(small)]
    ax.scatter(rest["stores"], rest["per_store"], s=42, color=GRAY, edgecolor="white", linewidth=1.2, label="Other products", zorder=3)
    ax.scatter(blue["stores"], blue["per_store"], s=48, color=BLUE, edgecolor="white", linewidth=1.2, label="Ten smallest sellers", zorder=4)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_major_formatter(FuncFormatter(money))
    ax.set_xticks([30, 100, 300, 1000])
    ax.set_yticks([30, 100, 300, 1000, 3000])
    ax.set_xlabel("Stores that bought it, log scale", fontsize=9.5)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    for key, dx, dy, ha in (("77699", 8, 0, "left"), ("77648", 8, 0, "left"), ("38008", -8, 0, "right"), ("37994", -8, 12, "right")):
        ax.annotate(p.loc[key, "name"], (p.loc[key, "stores"], p.loc[key, "per_store"]), xytext=(dx, dy), textcoords="offset points", fontsize=9, ha=ha, va="center")
    ax.set_ylim(25, 4200)
    ax.legend(loc="lower right", frameon=False, fontsize=9, handletextpad=0.2, borderaxespad=0.3)
    return save(fig, "4-reach-and-rate.png")


def chart_where(r, f):
    rows = [("Ten smallest sellers", "smallest"), ("Ten with the lowest loss", "lowest"), ("The nine that stopped selling", "gone")]
    kinds = [("same_flavor", "Same flavor, another size", BLUE), ("other", "Only other Smirnoff", PALE), ("nowhere", "No other Smirnoff", "#d9d9d9")]
    fig, ax = frame("Where the store could turn if the product went",
                    "Share of each cut's sales, by what else the store that bought it already stocks.",
                    height=3.3, left=0.31, right=0.96, bottom=0.2, top=0.72)
    ax.grid(False)
    ax.spines["bottom"].set_visible(False)
    for i, (label, key) in enumerate(rows):
        y, x = len(rows) - 1 - i, 0.0
        for kind, name, color in kinds:
            v = f[f"{key}_{kind}"]
            ax.barh(y, v, left=x, height=0.52, color=color, edgecolor="white", linewidth=2, label=name if i == 0 else None)
            if v > 0.06:
                ax.text(x + v / 2, y, f"{v:.0%}", ha="center", va="center", fontsize=10, fontweight=500, color="white" if color == BLUE else INK)
            x += v
    ax.set_yticks(range(len(rows)), [x[0] for x in rows][::-1], fontsize=10, color=INK)
    ax.set_xticks([])
    ax.set_xlim(0, 1)
    ax.legend(loc="upper left", bbox_to_anchor=(-0.01, -0.02), frameon=False, fontsize=9, ncols=3, handlelength=1, columnspacing=1.2)
    return save(fig, "5-where-buyers-go.png")


def chart_outcome(r, f):
    p = r["p"]
    rows = p[p["rank"] >= 35].sort_values("rank")
    cols = [("Ten smallest\nsellers", set(r["smallest"]), INK), ("Ten with the\nlowest loss", set(r["lowest"]), INK), ("Stopped selling\nin 2026", set(r["gone"]), BLUE)]
    n = len(rows)
    fig, ax = plt.subplots(figsize=(8, 6.4), dpi=200)
    fig.subplots_adjust(left=0.46, right=0.93, top=0.80, bottom=0.03)
    fig.text(0.04, 0.965, "The 17 smallest sellers, and what happened to them", fontsize=14, fontweight=500, ha="left", va="top")
    fig.text(0.04, 0.915, "A filled dot means the product is on that list. Sales rank runs from 35 to 51.", fontsize=10, color=MUTED, ha="left", va="top")
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    for i, (key, row) in enumerate(rows.iterrows()):
        y = n - 1 - i
        ax.axhline(y - 0.5, color=GRID, linewidth=0.8)
        note = "  (new in 2025)" if row["is_new"] else ""
        ax.text(-0.62, y, f"{row['name']}{note}", ha="right", va="center", fontsize=9.5)
        ax.text(-0.5, y, money(round(row["sales"], -3)), ha="left", va="center", fontsize=9, color=MUTED)
        for j, (_, members, color) in enumerate(cols):
            if key in members:
                ax.scatter(j, y, s=70, color=color, zorder=3)
            else:
                ax.scatter(j, y, s=70, facecolor="white", edgecolor="#c9c9c9", linewidth=1, zorder=3)
    for j, (label, _, _) in enumerate(cols):
        ax.text(j, n - 0.25, label, ha="center", va="bottom", fontsize=9.5, fontweight=500)
    ax.set_xlim(-0.55, len(cols) - 0.5)
    ax.set_ylim(-0.6, n + 0.6)
    ax.set_xticks([])
    ax.set_yticks([])
    return save(fig, "6-what-happened.png")


def main():
    r = c.run()
    f = c.facts(r)
    for fn in (chart_tail, chart_per_liter, chart_small_vs_price, chart_reach, chart_where, chart_outcome):
        print(fn(r, f))


if __name__ == "__main__":
    main()
