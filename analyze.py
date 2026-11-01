#!/usr/bin/env python3
import os
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

df = pd.read_csv("results/summary.csv").sort_values(["version", "cache", "users"])
os.makedirs("results/charts", exist_ok=True)
COL = {"python": "#3776ab", "ruby": "#cc342d"}
TITLE = {"hit": "COM cache (hit)", "miss": "SEM cache (miss)"}

def panel(fname, title, ylabel, metrics, logy=False):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)
    for ax, cache in zip(axes, ["hit", "miss"]):
        for ver, g in df[df.cache == cache].groupby("version"):
            for (m, label, ls) in metrics:
                ax.plot(g.users, g[m], ls, color=COL.get(ver), marker="o", ms=4, label=f"{ver} {label}")
        ax.set_title(TITLE[cache]); ax.set_xlabel("Usuários virtuais"); ax.set_xscale("log")
        if logy: ax.set_yscale("log")
        ax.grid(alpha=.3); ax.legend(fontsize=8)
    axes[0].set_ylabel(ylabel); fig.suptitle(title); fig.tight_layout()
    fig.savefig(f"results/charts/{fname}.png", dpi=150); plt.close(fig)

panel("latencia", "Tempo de resposta vs carga", "ms (escala log)",
      [("median_ms", "p50", "-"), ("p95_ms", "p95", "--"), ("p99_ms", "p99", ":")], logy=True)
panel("throughput", "Vazão (req/s) vs carga", "req/s", [("rps", "req/s", "-")])
panel("falhas", "Taxa de falhas vs carga", "% de falhas", [("fail_pct", "falhas", "-")])
panel("cpu", "CPU do container da API (máx.)", "% de CPU", [("cpu_max_pct", "CPU máx", "-")])

# Ganho do cache: mediana(miss) / mediana(hit)
m = df.pivot_table(index=["version", "users"], columns="cache", values="median_ms").dropna().reset_index()
m["speedup"] = m["miss"] / m["hit"]
fig, ax = plt.subplots(figsize=(8, 4.5)); w = 0.38
us = sorted(m.users.unique()); xs = range(len(us))
for k, (ver, g) in enumerate(m.groupby("version")):
    g = g.set_index("users").reindex(us)
    ax.bar([x + (k - .5) * w for x in xs], g.speedup, w, label=ver, color=COL.get(ver))
ax.set_xticks(list(xs)); ax.set_xticklabels(us); ax.set_xlabel("Usuários virtuais")
ax.set_ylabel("Speedup (mediana sem cache ÷ com cache)"); ax.axhline(1, color="k", lw=.8)
ax.legend(); ax.grid(alpha=.3, axis="y"); ax.set_title("Ganho proporcionado pelo cache")
fig.tight_layout(); fig.savefig("results/charts/speedup_cache.png", dpi=150)

# Capacidade: maior carga com <1% de falhas e p95 < 1s
ok = df[(df.fail_pct < 1) & (df.p95_ms < 1000)]
print("\nMaior carga sustentada (falhas<1%, p95<1s) e req/s máx:")
print(ok.groupby(["version", "cache"]).agg(max_users=("users", "max"), max_rps=("rps", "max")))
print("\nGráficos em results/charts/")
