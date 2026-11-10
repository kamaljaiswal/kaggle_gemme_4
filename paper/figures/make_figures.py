"""Figures for paper/writeup.md. Numbers are the ones in the paper (Sections 3, 4, 6, 7)."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
INK, GREY, BLUE, ORANGE, RED = "#1f2937", "#9ca3af", "#2563eb", "#d97706", "#b91c1c"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": GREY,
                     "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK, "text.color": INK})

def clean(ax):
    for s in ("top", "right"): ax.spines[s].set_visible(False)

# ---- Figure 1: three findings
fig, axs = plt.subplots(1, 3, figsize=(13, 4.3), gridspec_kw={"width_ratios": [1, 1.15, 1.15]})
ax = axs[0]
b = ax.bar(["Plain\nnotebook", "Scorer-like\nsandbox"], [52, 127], color=[RED, BLUE], width=0.55)
ax.axhline(129, color=GREY, ls="--", lw=1); ax.text(-0.42, 131, "all 129 tasks", ha="left", va="bottom", fontsize=9, color=GREY)
for r, v in zip(b, [52, 127]): ax.text(r.get_x()+r.get_width()/2, v+2, str(v), ha="center", fontweight="bold")
ax.set_ylim(0, 145); ax.set_ylabel("Reference fixes that pass"); ax.set_title("(a) Local grading", loc="left", fontweight="bold"); clean(ax)

ax = axs[1]
labels = ["Solved", "Wrong fix,\nright file", "Never edited", "Edited only\nother files"]
vals = [15, 12, 10, 4]; cols = [BLUE, ORANGE, RED, GREY]
b = ax.barh(labels[::-1], vals[::-1], color=cols[::-1], height=0.6)
for r, v in zip(b, vals[::-1]): ax.text(v+0.3, r.get_y()+r.get_height()/2, str(v), va="center", fontweight="bold")
ax.set_xlim(0, 18); ax.set_xlabel("Tasks (of 41)"); ax.set_title("(b) v12a outcome per task", loc="left", fontweight="bold"); clean(ax)

ax = axs[2]
vers = ["BM25 +\nsymbols", "+ aux dirs\ndown-weighted", "+ boilerplate\nstripped"]
tops = {"Top 1": [12, 15, 16], "Top 3": [19, 24, 30], "Top 5": [23, 28, 36]}
w = 0.26
for i, (k, c) in enumerate(zip(tops, ["#93c5fd", "#3b82f6", "#1d4ed8"])):
    xs = [j+(i-1)*w for j in range(3)]
    bars = ax.bar(xs, tops[k], w, color=c, label=k)
    for x, v in zip(xs, tops[k]): ax.text(x, v+0.5, str(v), ha="center", fontsize=9)
ax.set_xticks(range(3)); ax.set_xticklabels(vers, fontsize=9.5); ax.set_ylim(0, 44)
ax.set_ylabel("Tasks with a gold file in top-k (of 41)"); ax.legend(frameon=False, loc="upper left", fontsize=9)
ax.set_title("(c) Offline locate benchmark", loc="left", fontweight="bold"); clean(ax)
fig.tight_layout(); fig.savefig("figures/fig1_findings.png", dpi=200); plt.close(fig)

# ---- Figure 2: our public scores vs noise band
names = ["v3", "v9", "x_lb024", "v11", "v12a", "v15"]
tasks = [7, 9, 10, 8, 9, 6]
board = ["0.12", "0.15", "0.17", "0.13", "0.15", "0.10"]  # leaderboard scores as shown (truncated)
fig, ax = plt.subplots(figsize=(8.5, 4))
ax.axhspan(8, 10, color="#dbeafe", zorder=0); ax.text(5.45, 10.12, "8–10 tasks: one agent within ±2-task noise", ha="right", fontsize=9, color=BLUE)
cols = [GREY if n in ("v3", "v15") else BLUE for n in names]
b = ax.bar(names, tasks, color=cols, width=0.55, zorder=2)
for r, v, s in zip(b, tasks, board): ax.text(r.get_x()+r.get_width()/2, v+0.15, f"{v}  ({s})", ha="center", fontsize=10, fontweight="bold")
ax.text(0, 0.35, "summaries\nhidden", ha="center", fontsize=8.5, color="white")
ax.text(5, 0.35, "helper\nscripts", ha="center", fontsize=8.5, color="white")
ax.set_ylim(0, 12.5); ax.set_ylabel("Public tasks solved (of 58)")
ax.set_xlabel("Bundle (v12b timed out; v9 counted on its finished run)", fontsize=9.5); clean(ax)
ax.set_title("Public scores of our finished submissions", loc="left", fontweight="bold")
fig.tight_layout(); fig.savefig("figures/fig2_public_scores.png", dpi=200); plt.close(fig)
