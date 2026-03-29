from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .ui_helpers import cluster_color_map, to_rgba

TIMELINE_BAR_Y0 = 0.38
TIMELINE_BAR_Y1 = 0.62
TIMELINE_BAR_HEIGHT = TIMELINE_BAR_Y1 - TIMELINE_BAR_Y0
TIMELINE_BAR_WIDTH_DEFAULT = 1.02


def _build_attack_window_trace(timeline_df: pd.DataFrame) -> go.Scatter | None:
    if timeline_df.empty or "incident_phase_3class" not in timeline_df.columns or "timeline_x" not in timeline_df.columns:
        return None

    phase_values = timeline_df["incident_phase_3class"].astype(str).str.strip().str.lower()
    attack_df = timeline_df.loc[phase_values == "incident_window", ["timeline_x"]].copy()
    if attack_df.empty:
        return None

    x_values = attack_df["timeline_x"].dropna().drop_duplicates().sort_values()
    if x_values.empty:
        return None

    xs: list[object] = []
    ys: list[float | None] = []
    for x_value in x_values.tolist():
        xs.extend([x_value, x_value, None])
        ys.extend([TIMELINE_BAR_Y0 - 0.06, TIMELINE_BAR_Y1 + 0.06, None])

    return go.Scatter(
        x=xs,
        y=ys,
        mode="lines",
        name="attack window",
        line={"color": "rgb(214,39,40)", "width": 4, "dash": "dash"},
        hoverinfo="skip",
        showlegend=True,
    )


def _build_separator_trace(x_values: pd.Series, *, window_s: int | None) -> go.Scatter | None:
    if x_values.empty or not window_s or int(window_s) <= 0:
        return None
    xs: list[object] = []
    ys: list[float | None] = []
    if pd.api.types.is_datetime64_any_dtype(x_values):
        centers = pd.to_datetime(x_values, errors="coerce").dropna().drop_duplicates().sort_values()
        if len(centers) < 2:
            return None
        half_step = pd.Timedelta(seconds=int(window_s) / 2.0)
        boundaries = [center + half_step for center in centers.iloc[:-1]]
    else:
        numeric_x = pd.to_numeric(x_values, errors="coerce").dropna().drop_duplicates().sort_values()
        if len(numeric_x) < 2:
            return None
        half_step = int(window_s) / 2.0
        boundaries = [float(center) + half_step for center in numeric_x.iloc[:-1]]

    for boundary in boundaries:
        xs.extend([boundary, boundary, None])
        ys.extend([TIMELINE_BAR_Y0, TIMELINE_BAR_Y1, None])

    return go.Scatter(
        x=xs,
        y=ys,
        mode="lines",
        name="separators",
        line={"color": "rgba(255,255,255,0.95)", "width": 1},
        hoverinfo="skip",
        showlegend=False,
        visible=False,
    )


def _compute_bar_width_values(x_values: pd.Series, *, window_s: int | None, bar_width_fraction: float) -> list[float] | None:
    if x_values.empty:
        return None
    if pd.api.types.is_datetime64_any_dtype(x_values):
        if not window_s or int(window_s) <= 0:
            return None
        return [float(int(window_s) * 1000 * bar_width_fraction)] * len(x_values)

    numeric_x = pd.to_numeric(x_values, errors="coerce")
    if numeric_x.notna().all():
        if window_s and int(window_s) > 0:
            return [float(int(window_s) * bar_width_fraction)] * len(x_values)
        return [bar_width_fraction] * len(x_values)
    return None


def _build_dense_timeline_slots(
    timeline_df: pd.DataFrame,
    *,
    missing_source_df: pd.DataFrame,
    window_s: int | None,
) -> pd.DataFrame:
    source_x = pd.to_datetime(missing_source_df.get("timeline_x"), errors="coerce")
    if source_x.notna().any() and window_s and int(window_s) > 0:
        base = pd.DataFrame(
            {
                "timeline_x": pd.date_range(
                    start=source_x.dropna().min(),
                    end=source_x.dropna().max(),
                    freq=pd.Timedelta(seconds=int(window_s)),
                )
            }
        )
        present = timeline_df.copy()
        present["timeline_x"] = pd.to_datetime(present["timeline_x"], errors="coerce")
        merged = base.merge(present, on="timeline_x", how="left", sort=True)
        merged["is_missing_window"] = merged["cluster_id"].isna()
        if "time_cluster" not in merged.columns:
            merged["time_cluster"] = merged["timeline_x"]
        return merged

    out = timeline_df.copy()
    out["is_missing_window"] = False
    if "time_cluster" not in out.columns and "timeline_x" in out.columns:
        out["time_cluster"] = out["timeline_x"]
    return out


def build_timeline_plot(
    timeline_df: pd.DataFrame,
    *,
    highlighted_clusters: list[int],
    mute_non_selected: bool,
    title: str,
    window_s: int | None = None,
    missing_source_df: pd.DataFrame | None = None,
) -> go.Figure:
    fig = go.Figure()
    if timeline_df.empty:
        fig.update_layout(title=title)
        return fig

    cluster_ids = sorted(pd.to_numeric(timeline_df["cluster_id"], errors="coerce").dropna().astype(int).unique().tolist())
    colors = cluster_color_map(cluster_ids)
    highlighted = set(int(x) for x in highlighted_clusters)
    hover_cols = ["time_cluster", "cluster_id", "n_clusters", "incident_phase_3class", "is_attack_related", "row_idx"]
    missing_source = missing_source_df if missing_source_df is not None else timeline_df
    dense_timeline = _build_dense_timeline_slots(timeline_df, missing_source_df=missing_source, window_s=window_s)
    for col in hover_cols:
        if col not in dense_timeline.columns:
            dense_timeline[col] = ""

    missing_mask: list[bool] = []
    color_values: list[str] = []
    hover_rows: list[list[object]] = []
    for row in dense_timeline.itertuples(index=False):
        row_dict = row._asdict()
        cluster_value = pd.to_numeric(pd.Series([row_dict.get("cluster_id")]), errors="coerce").iloc[0]
        is_missing_window = bool(row_dict.get("is_missing_window", False))
        if is_missing_window or pd.isna(cluster_value):
            missing_mask.append(True)
            color_values.append("rgb(220,220,220)")
            hover_rows.append(
                [
                    row_dict.get("time_cluster", row_dict.get("timeline_x", "")),
                    "missing",
                    row_dict.get("n_clusters", ""),
                    "",
                    "",
                    "",
                ]
            )
            continue

        missing_mask.append(False)
        cluster_id = int(cluster_value)
        is_selected = not highlighted or cluster_id in highlighted
        if is_selected:
            color_values.append(colors[cluster_id])
        else:
            color_values.append(to_rgba(colors[cluster_id], 0.08) if mute_non_selected else to_rgba(colors[cluster_id], 0.35))
        hover_rows.append([row_dict.get(col, "") for col in hover_cols])

    dense_timeline = dense_timeline.copy()
    dense_timeline["_is_missing"] = missing_mask
    dense_timeline["_color"] = color_values
    dense_timeline["_hover"] = hover_rows

    missing_df = dense_timeline[dense_timeline["_is_missing"]].copy()
    present_df = dense_timeline[~dense_timeline["_is_missing"]].copy()

    missing_width_default = _compute_bar_width_values(
        pd.Series(missing_df["timeline_x"]), window_s=window_s, bar_width_fraction=TIMELINE_BAR_WIDTH_DEFAULT
    ) if not missing_df.empty else None
    present_width_default = _compute_bar_width_values(
        pd.Series(present_df["timeline_x"]), window_s=window_s, bar_width_fraction=TIMELINE_BAR_WIDTH_DEFAULT
    ) if not present_df.empty else None

    if not missing_df.empty:
        fig.add_trace(
            go.Bar(
                x=missing_df["timeline_x"],
                y=[TIMELINE_BAR_HEIGHT] * len(missing_df),
                base=TIMELINE_BAR_Y0,
                width=missing_width_default,
                name="missing data",
                marker={"color": missing_df["_color"].tolist(), "line": {"width": 0}},
                customdata=missing_df["_hover"].tolist(),
                hovertemplate=(
                    "time_cluster=%{customdata[0]}<br>"
                    "cluster_id=%{customdata[1]}<br>"
                    "n_clusters=%{customdata[2]}<br>"
                    "incident_phase_3class=%{customdata[3]}<br>"
                    "is_attack_related=%{customdata[4]}<br>"
                    "row_idx=%{customdata[5]}<extra></extra>"
                ),
                showlegend=False,
            )
        )

    if not present_df.empty:
        fig.add_trace(
            go.Bar(
                x=present_df["timeline_x"],
                y=[TIMELINE_BAR_HEIGHT] * len(present_df),
                base=TIMELINE_BAR_Y0,
                width=present_width_default,
                name="timeline",
                marker={"color": present_df["_color"].tolist(), "line": {"width": 0}},
                customdata=present_df["_hover"].tolist(),
                hovertemplate=(
                    "time_cluster=%{customdata[0]}<br>"
                    "cluster_id=%{customdata[1]}<br>"
                    "n_clusters=%{customdata[2]}<br>"
                    "incident_phase_3class=%{customdata[3]}<br>"
                    "is_attack_related=%{customdata[4]}<br>"
                    "row_idx=%{customdata[5]}<extra></extra>"
                ),
                showlegend=False,
            )
        )

    attack_window_trace = _build_attack_window_trace(present_df)
    if attack_window_trace is not None:
        fig.add_trace(attack_window_trace)

    separator_trace = _build_separator_trace(dense_timeline["timeline_x"], window_s=window_s)
    separator_trace_index: int | None = None
    if separator_trace is not None:
        fig.add_trace(separator_trace)
        separator_trace_index = len(fig.data) - 1

    fig.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode="markers",
            name="missing data",
            marker={"size": 10, "color": "rgb(220,220,220)"},
            hoverinfo="skip",
        )
    )
    for cluster_id in cluster_ids:
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                name=f"cluster {cluster_id}",
                marker={"size": 10, "color": colors[cluster_id]},
                hoverinfo="skip",
            )
        )

    fig.update_layout(
        title=title,
        barmode="overlay",
        bargap=0.0,
        bargroupgap=0.0,
        uirevision="timeline-static",
        updatemenus=[
            {
                "type": "buttons",
                "direction": "right",
                "x": 1.0,
                "xanchor": "right",
                "y": 1.18,
                "yanchor": "top",
                "buttons": [
                    {
                        "label": "Continuous",
                        "method": "restyle",
                        "args": [{"visible": False}, [separator_trace_index]] if separator_trace_index is not None else [{}, []],
                    },
                    {
                        "label": "Thin Separators",
                        "method": "restyle",
                        "args": [{"visible": True}, [separator_trace_index]] if separator_trace_index is not None else [{}, []],
                    },
                ],
                "showactive": True,
            }
        ],
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis={
            "title": "time",
            "showgrid": False,
            "zeroline": False,
        },
        yaxis_title="",
        height=300,
        legend_title_text="clusters",
        yaxis={
            "visible": False,
            "showgrid": False,
            "showticklabels": False,
            "zeroline": False,
            "range": [0.25, 0.75],
        },
    )
    return fig
