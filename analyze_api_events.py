# analysis_api_only.py
# Pandas + Matplotlib (no seaborn), exports PNGs for PowerPoint
# Scope: API events only
# English everywhere except axis labels & titles

import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from pathlib import Path


# =========================
# Helpers
# =========================
def to_utc(series):
    return pd.to_datetime(series, utc=True, errors="coerce")


def _num(x):
    return pd.to_numeric(x, errors="coerce")


def fmt_pct(x):
    return "n/a" if (x is None or (isinstance(x, float) and np.isnan(x))) else f"{x:.1%}"


def fmt_int(x):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{int(x)}"


def fmt_ms(x):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.0f} ms"


# =========================
# Load & filter (API only)
# =========================
def load_api(path_api: str, start: pd.Timestamp, end: pd.Timestamp):
    api = pd.read_excel(path_api)
    api.columns = [c.strip() for c in api.columns]

    for col in ["created", "updated", "expiresAt"]:
        if col in api.columns:
            api[col] = to_utc(api[col])

    api_2d = api.loc[
        api.get("created").notna()
        & (api["created"] >= start)
        & (api["created"] <= end)
    ].copy()

    return api, api_2d


# =========================
# Metrics (API only)
# =========================
def compute_metrics(api_2d: pd.DataFrame, bucket: str):
    # API conversations (unique conversationId)
    if "conversationId" in api_2d.columns:
        n_conversations = api_2d["conversationId"].dropna().astype(str).nunique()
    else:
        n_conversations = np.nan

    # Latencies – only /generation and successfull ones (where conversationId is not null)
    lat = api_2d.copy()
    lat = lat.loc[lat["conversationId"].notna()]
    if "endpoint" in lat.columns:
        lat = lat[lat["endpoint"].astype(str).str.contains("/generation", na=False)]
    lat_ms = _num(lat.get("duration_ms", pd.Series(dtype=float)))
    lat_p50 = float(np.nanpercentile(lat_ms.dropna(), 50)) if lat_ms.notna().any() else np.nan
    lat_p95 = float(np.nanpercentile(lat_ms.dropna(), 95)) if lat_ms.notna().any() else np.nan
    lat_max = float(lat_ms.max()) if lat_ms.notna().any() else np.nan

    # Timeouts
    if "status_code" in api_2d.columns:
        n_timeouts = int(api_2d["status_code"].isin([408, 504, 524]).sum())
    else:
        n_timeouts = 0

    # Error rates
    if "status_code" in api_2d.columns and len(api_2d):
        sc = _num(api_2d["status_code"])
        status_class = (sc // 100) * 100
        total_calls = len(api_2d)
        err_4xx = int((status_class == 400).sum())
        err_5xx = int((status_class == 500).sum())
        errors = err_4xx + err_5xx
        rate_4xx = err_4xx / total_calls
        rate_5xx = err_5xx / total_calls
    else:
        rate_4xx = rate_5xx = np.nan

    # Traffic + error rate by time bucket
    if "created" in api_2d.columns and not api_2d.empty:
        tmp = api_2d.copy()
        # bucket "15min": 10:07 → 10:00
        tmp["ts"] = tmp["created"].dt.floor(bucket)
        by_t = tmp.groupby("ts").agg(
            calls=("id", "count") if "id" in tmp.columns else ("ts", "count"),
            errors=("status_code", lambda s: (_num(s) >= 400).sum()) if "status_code" in tmp.columns else ("ts", lambda s: 0),
        ).reset_index()
        by_t["error_rate"] = by_t["errors"] / by_t["calls"]
    else:
        by_t = pd.DataFrame(columns=["ts", "calls", "errors", "error_rate"])

    # 4xx over time (lines per status code)
    if "status_code" in api_2d.columns and "created" in api_2d.columns:
        e4 = api_2d[(_num(api_2d["status_code"]) >= 400) & (_num(api_2d["status_code"]) < 500)].copy()
        if not e4.empty:
            e4["ts"] = e4["created"].dt.floor(bucket)
            pvt4xx = (
                e4.groupby(["ts", "status_code"])
                .size()
                .reset_index(name="count")
                .pivot(index="ts", columns="status_code", values="count")
                .fillna(0)
            )
        else:
            pvt4xx = pd.DataFrame()
    else:
        pvt4xx = pd.DataFrame()

    # Avg events/calls per conversation
    # same as "conversationId" in api_2d.columns
    if {"conversationId"} <= set(api_2d.columns):
        # excludes errors like 429 where too many requests where made from one ip and maybe a conversationId was supplied but not returned
        # so lets say there were 4 messages from one user so for one conversationId so 4 rows. for the fourth row chatMessages = 8 but then too many requests from the ip as the fifth message was sent from the user then in the array it would still be only value 4
        # since the error has no conversationId only one supplied. chatMessages for the error row is also 0
        # which is correct for now
        # could analyze in future also from standpoint conversationId_supplied 
        cps = api_2d.dropna(subset=["conversationId"]).groupby("conversationId").size()
        api_avg_messages_per_conversation = float(cps.mean()) if not cps.empty else np.nan
    else:
        api_avg_messages_per_conversation = np.nan

    return {
        "n_conversations": n_conversations,
        "lat_ms": lat_ms,
        "lat_p50": lat_p50,
        "lat_p95": lat_p95,
        "lat_max": lat_max,
        "errors": errors,
        "n_timeouts": n_timeouts,
        "rate_4xx": rate_4xx,
        "rate_5xx": rate_5xx,
        "by_t": by_t,
        "pvt4xx": pvt4xx,
        "api_avg_messages_per_conversation": api_avg_messages_per_conversation,
    }


# =========================
# Plots (API only)
# =========================
def save_kpi_tile(outdir: Path, filename: str, title: str, lines, start: pd.Timestamp, end: pd.Timestamp):
    fig = plt.figure(figsize=(10, 6))
    ax = plt.gca()
    ax.axis("off")
    fig.suptitle(title, fontsize=16, y=0.95)
    y = 0.85
    lh = 0.06
    for label, value in lines:
        fig.text(0.08, y, f"{label}", ha="left", va="center", fontsize=12)
        fig.text(0.55, y, f"{value}", ha="left", va="center", fontsize=12, fontweight="bold")
        y -= lh
    fig.text(0.08, 0.06, f"Zeitraum: {start.date()} bis {end.date()} (UTC) | Quelle: api_events", fontsize=9)
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(outdir / filename, dpi=150)
    plt.close(fig)


def make_plots(api_2d: pd.DataFrame, M: dict, bucket: str, outdir: Path, start: pd.Timestamp, end: pd.Timestamp):
    outdir.mkdir(exist_ok=True)

    # KPI tile (API)
    save_kpi_tile(
        outdir,
        f"kpis_api_{start.strftime('%Y-%m-%d')}_{end.strftime('%Y-%m-%d')}.png",
        "KPIs — API (api_events)",
        [
            ("API Calls gesamt",        fmt_int(len(api_2d))),
            ("API Conversations (unique)",   fmt_int(M["n_conversations"])),
            ("Ø Messages/Conversations (API)",  "n/a" if np.isnan(M["api_avg_messages_per_conversation"]) else f"{M['api_avg_messages_per_conversation']:.2f}"),
            ("Antwortzeit p50",         fmt_ms(M["lat_p50"])),
            ("Antwortzeit p95",         fmt_ms(M["lat_p95"])),
            ("Max. Dauer",              fmt_ms(M["lat_max"])),
            ("API Calls mit Fehler",    fmt_int(M["errors"])),
            # ("Timeouts (408/504/524)",  fmt_int(M["n_timeouts"])),
            ("4xx-Rate",                fmt_pct(M["rate_4xx"])),
            ("5xx-Rate",                fmt_pct(M["rate_5xx"])),
        ],
        start,
        end,
    )

    # Traffic + error rate
    by_t = M["by_t"]
    if not by_t.empty:
        plt.figure(figsize=(10, 4))
        ax1 = plt.gca()
        ax2 = ax1.twinx()
        l1, = ax1.plot(by_t["ts"], by_t["calls"], label=f"Requests / {bucket}", linewidth=2)
        l2, = ax2.plot(by_t["ts"], by_t["error_rate"], label="Fehlerrate (≥400)", linestyle="--", linewidth=2)
        ax1.set_title(f"Traffic & Fehlerrate ({bucket}) — {start.date()} bis {end.date()} (UTC)")
        ax1.set_xlabel("Zeit")
        ax1.set_ylabel(f"Requests je {bucket}")
        ax2.set_ylabel("Fehlerrate")
        ax2.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax1.grid(True, alpha=0.3)
        ax1.legend(handles=[l1], loc="upper left")
        ax2.legend(handles=[l2], loc="upper right")
        plt.tight_layout()
        plt.savefig(outdir / f"traffic_error_rate_{start.strftime('%Y-%m-%d')}_{end.strftime('%Y-%m-%d')}.png", dpi=150)
        plt.close()
        
    
    # 4xx over time
    pvt4 = M["pvt4xx"]
    if pvt4 is not None and not pvt4.empty:
        fig, ax = plt.subplots(figsize=(10, 4))

        for code in pvt4.columns.sort_values():
            ax.plot(pvt4.index, pvt4[code], label=str(int(code)), linewidth=2,  marker="o")

        ax.set_title(f"4xx-Fehler über die Zeit ({bucket}) — {start.date()} bis {end.date()} (UTC)")
        ax.set_xlabel("Zeit")
        ax.set_ylabel(f"Anzahl 4xx je {bucket}")

        ax.set_ylim(bottom=0)
        ax.set_xlim(start, end)

        ax.grid(True, alpha=0.3)
        ax.legend(title="HTTP-Status", ncol=min(len(pvt4.columns), 6))

        plt.tight_layout()
        plt.savefig(outdir / f"4xx_over_time_{start.strftime('%Y-%m-%d')}_{end.strftime('%Y-%m-%d')}.png", dpi=150)
        plt.close()


    # Latency boxplot (/generation)
    lat_ms = M["lat_ms"]
    if lat_ms is not None and lat_ms.notna().any():
        mean_ms = float(lat_ms.mean())
        plt.figure(figsize=(6, 5))
        plt.boxplot(lat_ms.dropna().values, vert=True, labels=["/generation"], showfliers=True)
        plt.scatter([1], [mean_ms], zorder=3, label=f"Mittelwert ≈ {mean_ms:.0f} ms")
        if not np.isnan(M["lat_p50"]):
            plt.axhline(M["lat_p50"], linestyle="--", linewidth=1, label=f"p50 ≈ {M['lat_p50']:.0f} ms")
        if not np.isnan(M["lat_p95"]):
            plt.axhline(M["lat_p95"], linestyle=":", linewidth=1, label=f"p95 ≈ {M['lat_p95']:.0f} ms")
        plt.title("Antwortzeiten /generation (UTC)")
        plt.ylabel("Dauer (ms)")
        plt.grid(True, axis="y", alpha=0.3)
        plt.legend(loc="upper right")
        plt.tight_layout()
        plt.savefig(outdir / f"latency_boxplot_annotated_{start.strftime('%Y-%m-%d')}_{end.strftime('%Y-%m-%d')}.png", dpi=150)
        plt.close()

def _prep_generation(api_2d_without_errors: pd.DataFrame) -> pd.DataFrame:
    df = api_2d_without_errors.copy()
    # ensure datetime
    df["created"] = pd.to_datetime(df["created"], utc=True, errors="coerce")
    # filter /generation if column exists
    if "endpoint" in df.columns:
        df = df[df["endpoint"].astype(str).str.contains("/generation", na=False)]
    # numeric latency
    df["duration_ms"] = _num(df.get("duration_ms"))
    # keep only valid rows
    df = df.dropna(subset=["created", "duration_ms"])
    return df

# 5) Latency percentiles over time (p50/p95) — 2 lines
def plot_latency_percentiles_over_time(api_2d_without_errors: pd.DataFrame, bucket: str, outpath):
    df = _prep_generation(api_2d_without_errors)
    if df.empty:
        return

    df["ts"] = df["created"].dt.floor(bucket)

    g = df.groupby("ts")["duration_ms"]
    pct = g.quantile([0.50, 0.95]).unstack()
    pct.columns = ["p50", "p95"]
    pct = pct.sort_index()

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(pct.index, pct["p50"], linewidth=2, marker="o", markersize=3, label="p50")
    ax.plot(pct.index, pct["p95"], linewidth=2, marker="o", markersize=3, label="p95")

    ax.set_title(f"Antwortzeiten /generation — Perzentile ({bucket})")
    ax.set_xlabel("Zeit")
    ax.set_ylabel("Dauer (ms)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    plt.tight_layout()
    plt.savefig(outpath, dpi=150)
    plt.close(fig)

# 6) Latency vs traffic correlation — scatter: calls/bucket vs p95 latency
def plot_latency_vs_traffic(api_2d_without_errors: pd.DataFrame, bucket: str, outpath):
    df = _prep_generation(api_2d_without_errors)
    if df.empty:
        return

    df["ts"] = df["created"].dt.floor(bucket)

    agg = df.groupby("ts").agg(
        calls=("duration_ms", "size"),
        p95=("duration_ms", lambda s: float(np.nanpercentile(s, 95)) if len(s) else np.nan),
    ).dropna()

    if agg.empty:
        return

    fig, ax = plt.subplots(figsize=(6.5, 5))
    ax.scatter(agg["calls"], agg["p95"])
    ax.set_title(f"Traffic vs p95-Latenz ({bucket})")
    ax.set_xlabel(f"Requests je {bucket}")
    ax.set_ylabel("p95 Dauer (ms)")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(outpath, dpi=150)
    plt.close(fig)

# Extra) “Slows down after Nth request in conversation”
# Compute per-conversation sequence index (order by created asc), then plot latency vs sequence index.
def plot_latency_by_conversation_step(api_2d_without_errors: pd.DataFrame, outpath, max_step: int = 30, stat: str = "median"):
    df = _prep_generation(api_2d_without_errors)
    if df.empty or "conversationId" not in df.columns:
        return

    df = df.dropna(subset=["conversationId"])
    df["conversationId"] = df["conversationId"].astype(str)

    # order within each conversation
    df = df.sort_values(["conversationId", "created"])
    df["step"] = df.groupby("conversationId").cumcount() + 1

    # optionally limit steps for readability
    df = df[df["step"] <= max_step]
    if df.empty:
        return

    # aggregate across conversations by step
    if stat == "mean":
        y = df.groupby("step")["duration_ms"].mean()
        label = "Mittelwert"
    elif stat == "p95":
        y = df.groupby("step")["duration_ms"].apply(lambda s: float(np.nanpercentile(s, 95)) if len(s) else np.nan)
        label = "p95"
    else:
        y = df.groupby("step")["duration_ms"].median()
        label = "Median"

    y = y.dropna()
    if y.empty:
        return

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(y.index, y.values, linewidth=2, marker="o", markersize=4)
    ax.set_title("Latenz nach Request-Position in der conversation (/generation)")
    ax.set_xlabel("Request-Index in conversation (geordnet nach Zeit)")
    ax.set_ylabel(f"{label} Dauer (ms)")
    ax.set_xlim(1, max_step)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(outpath, dpi=150)
    plt.close(fig)

def latency_by_step_table(
    api_2d_without_errors: pd.DataFrame,
    max_step: int = 30,
    generation_only: bool = True,
) -> pd.DataFrame:
    df = api_2d_without_errors.copy()

    # required cols
    if "created" not in df.columns or "duration_ms" not in df.columns or "conversationId" not in df.columns:
        return pd.DataFrame(columns=["step", "n", "mean_ms", "p50_ms", "p95_ms", "p99_ms"])

    df["created"] = pd.to_datetime(df["created"], utc=True, errors="coerce")
    df["duration_ms"] = _num(df["duration_ms"])
    df["conversationId"] = df["conversationId"].astype(str)

    # optional filter: only /generation
    if generation_only and "endpoint" in df.columns:
        df = df[df["endpoint"].astype(str).str.contains("/generation", na=False)]

    # keep valid rows
    df = df.dropna(subset=["created", "duration_ms", "conversationId"])
    if df.empty:
        return pd.DataFrame(columns=["step", "n", "mean_ms", "p50_ms", "p95_ms", "p99_ms"])

    # order within conversation and assign step index
    df = df.sort_values(["conversationId", "created"])
    df["step"] = df.groupby("conversationId").cumcount() + 1

    # limit steps for readability
    df = df[df["step"] <= max_step]
    if df.empty:
        return pd.DataFrame(columns=["step", "n", "mean_ms", "p50_ms", "p95_ms", "p99_ms"])

    # aggregate across ALL conversations by step
    g = df.groupby("step")["duration_ms"]
    out = pd.DataFrame({
        "step": g.size().index,
        "n": g.size().values,
        "mean_ms": g.mean().values,
        "p50_ms": g.median().values,
        "p95_ms": g.apply(lambda s: float(np.nanpercentile(s, 95)) if len(s) else np.nan).values,
        "p99_ms": g.apply(lambda s: float(np.nanpercentile(s, 99)) if len(s) else np.nan).values,
    })

    return out.sort_values("step").reset_index(drop=True)

def plot_latency_by_step(
    step_tbl: pd.DataFrame,
    outpath,
    show: str = "mean",          # "mean" or "p50"
    add_p95: bool = True,
    min_n: int = 10,             # hide steps with too few samples
):
    if step_tbl is None or step_tbl.empty:
        return

    df = step_tbl.copy()
    df = df[df["n"] >= min_n]
    if df.empty:
        return

    ycol = "mean_ms" if show == "mean" else "p50_ms"

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(df["step"], df[ycol], linewidth=2, marker="o", markersize=4, label=show)

    if add_p95 and "p95_ms" in df.columns:
        ax.plot(df["step"], df["p95_ms"], linewidth=2, marker="o", markersize=3, label="p95")

    ax.set_title("Latenz nach Request-Position in der conversation (/generation)")
    ax.set_xlabel("Request-Index in conversation (geordnet nach Zeit)")
    ax.set_ylabel("Dauer (ms)")
    ax.set_xlim(1, int(df["step"].max()))
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    ax.legend()
    plt.tight_layout()
    plt.savefig(outpath, dpi=150)
    plt.close(fig)

# Traffic heatmap: calls by weekday x hour (all endpoints or optionally /generation only)
def plot_traffic_heatmap(api_2d_without_errors: pd.DataFrame, outpath, generation_only: bool = False):
    df = api_2d_without_errors.copy()
    df["created"] = pd.to_datetime(df.get("created"), utc=True, errors="coerce")
    df = df.dropna(subset=["created"])

    if generation_only and "endpoint" in df.columns:
        df = df[df["endpoint"].astype(str).str.contains("/generation", na=False)]

    if df.empty:
        return

    # weekday: Mon=0..Sun=6
    df["weekday"] = df["created"].dt.weekday
    df["hour"] = df["created"].dt.hour

    heat = df.groupby(["weekday", "hour"]).size().unstack(fill_value=0).reindex(index=range(7), columns=range(24), fill_value=0)

    fig, ax = plt.subplots(figsize=(12, 4.5))
    im = ax.imshow(heat.values, aspect="auto", origin="upper")

    ax.set_title("Traffic-Heatmap (Requests nach Wochentag × Stunde)")
    ax.set_xlabel("Stunde (UTC)")
    ax.set_ylabel("Wochentag")

    ax.set_xticks(range(24))
    ax.set_xticklabels([str(h) for h in range(24)])

    weekday_labels = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    ax.set_yticks(range(7))
    ax.set_yticklabels(weekday_labels)

    # colorbar (no custom colors specified)
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("Requests")

    plt.tight_layout()
    plt.savefig(outpath, dpi=150)
    plt.close(fig)
    
def analyze_api_events(path_api: str, start: pd.Timestamp, end: pd.Timestamp, bucket: str = "1d", outdir: Path = Path("analysis_plots_api_only")):
    print("Start analyze_api_events()")
    api_all, api_2d = load_api(path_api, start, end)
    print("len(api_2d)", len(api_2d))
    api_2d = api_2d.loc[api_2d["endpoint"] == "/v1/generation/imperia"]
    print("len(api_2d)", len(api_2d))
    
    print(api_2d.head())
    print(api_all.head())
    
    M = compute_metrics(api_2d, bucket)
    make_plots(api_2d, M, bucket, outdir, start, end)
    
    # without errors
    api_2d_without_errors = api_2d.loc[api_2d["conversationId"].notna()]
    plot_latency_percentiles_over_time(api_2d_without_errors, bucket=bucket, outpath=outdir/f"latency_p50_p95_over_time_{start.strftime('%Y-%m-%d')}_{end.strftime('%Y-%m-%d')}.png")
    # in future should also do a plot which considers the error traffic 
    # which could be caused by attacks and drain the server and therefore relevant
    # but only consider response time of the 200ers
    plot_latency_vs_traffic(api_2d_without_errors, bucket=bucket, outpath=outdir/f"traffic_vs_p95_scatter_{start.strftime('%Y-%m-%d')}_{end.strftime('%Y-%m-%d')}.png")
    plot_latency_by_conversation_step(api_2d_without_errors, outpath=outdir/f"latency_by_step_median_{start.strftime('%Y-%m-%d')}_{end.strftime('%Y-%m-%d')}.png", max_step=30, stat="median")
    step_tbl = latency_by_step_table(api_2d_without_errors, max_step=30, generation_only=True)
    plot_latency_by_step(step_tbl, outdir/f"latency_by_step_{start.strftime('%Y-%m-%d')}_{end.strftime('%Y-%m-%d')}.png", show="mean", add_p95=True, min_n=10)
    plot_traffic_heatmap(api_2d_without_errors, outpath=outdir/f"traffic_heatmap_{start.strftime('%Y-%m-%d')}_{end.strftime('%Y-%m-%d')}.png", generation_only=False)

    print("PNG exports written to:", outdir.resolve())
    print("End analyze_api_events()")
    return outdir
    
# =========================
# Main (no hardcoding)
# =========================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", required=True, help="Path to api_events Excel file")
    parser.add_argument("--start", required=True, help="Start timestamp (e.g. 2025-10-10 or 2025-10-10T00:00:00Z)")
    parser.add_argument("--end", required=True, help="End timestamp (inclusive)")
    parser.add_argument("--bucket", default="15min", help="Aggregation bucket (e.g. 15min, 5min, 1H)")
    parser.add_argument("--outdir", default="analysis_plots_api_only", help="Output directory for PNGs")
    args = parser.parse_args()

    START = pd.Timestamp(args.start)
    END = pd.Timestamp(args.end)
    outdir = Path(args.outdir)
    
    outdir = analyze_api_events(path_api=args.api, start=START, end=END, bucket=args.bucket, outdir=outdir)
