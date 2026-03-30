from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .ui_helpers import cluster_color_map, to_rgba

TIMELINE_BAR_Y0 = 0.38
TIMELINE_BAR_Y1 = 0.62
TIMELINE_BAR_HEIGHT = TIMELINE_BAR_Y1 - TIMELINE_BAR_Y0
TIMELINE_BAR_WIDTH_DEFAULT = 1.02
ENTROPY_BAR_WIDTH_DEFAULT = 1.0


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


def build_entropy_plot(
    entropy_df: pd.DataFrame,
    *,
    entropy_col: str,
    window_s: int | None = None,
    title: str = "Shannon Entropy Over Time",
) -> go.Figure:
    fig = go.Figure()
    if entropy_df.empty or entropy_col not in entropy_df.columns:
        fig.update_layout(title=title)
        return fig

    plot_df = entropy_df.copy()
    plot_df[entropy_col] = pd.to_numeric(plot_df[entropy_col], errors="coerce")
    plot_df = plot_df.dropna(subset=["timeline_x"])
    if plot_df.empty:
        fig.update_layout(title=title)
        return fig

    if pd.api.types.is_datetime64_any_dtype(plot_df["timeline_x"]) or pd.to_datetime(plot_df["timeline_x"], errors="coerce").notna().all():
        plot_df["timeline_x"] = pd.to_datetime(plot_df["timeline_x"], errors="coerce")
        if window_s and int(window_s) > 0:
            full_x = pd.date_range(
                start=plot_df["timeline_x"].dropna().min(),
                end=plot_df["timeline_x"].dropna().max(),
                freq=pd.Timedelta(seconds=int(window_s)),
            )
            plot_df = pd.DataFrame({"timeline_x": full_x}).merge(plot_df, on="timeline_x", how="left", sort=True)
    else:
        numeric_x = pd.to_numeric(plot_df["timeline_x"], errors="coerce")
        if numeric_x.notna().all() and window_s and int(window_s) > 0:
            start = int(numeric_x.min())
            end = int(numeric_x.max())
            full_x = list(range(start, end + int(window_s), int(window_s)))
            plot_df = pd.DataFrame({"timeline_x": full_x}).merge(plot_df, on="timeline_x", how="left", sort=True)

    plot_df["_is_missing"] = plot_df[entropy_col].isna()
    observed_values = pd.to_numeric(plot_df.loc[~plot_df["_is_missing"], entropy_col], errors="coerce").dropna()
    dataset_mean = float(observed_values.mean()) if not observed_values.empty else float("nan")
    dataset_median = float(observed_values.median()) if not observed_values.empty else float("nan")
    plot_df[entropy_col] = pd.to_numeric(plot_df[entropy_col], errors="coerce")
    plot_top = max(
        float(observed_values.max()) if not observed_values.empty else 0.0,
        dataset_mean if pd.notna(dataset_mean) else 0.0,
        dataset_median if pd.notna(dataset_median) else 0.0,
        0.1,
    )
    plot_df["_missing_height"] = plot_top

    missing_df = plot_df[plot_df["_is_missing"]].copy()
    present_df = plot_df[~plot_df["_is_missing"]].copy()

    missing_width = (
        _compute_bar_width_values(
            pd.Series(missing_df["timeline_x"]),
            window_s=window_s,
            bar_width_fraction=ENTROPY_BAR_WIDTH_DEFAULT,
        )
        if not missing_df.empty
        else None
    )
    present_width = (
        _compute_bar_width_values(
            pd.Series(present_df["timeline_x"]),
            window_s=window_s,
            bar_width_fraction=ENTROPY_BAR_WIDTH_DEFAULT,
        )
        if not present_df.empty
        else None
    )

    if not missing_df.empty:
        missing_hover = pd.DataFrame(
            {
                "time_cluster": missing_df.get("time_cluster", missing_df["timeline_x"]).astype(str),
                "row_idx": missing_df.get("row_idx", pd.Series([""] * len(missing_df), index=missing_df.index)),
            }
        ).to_numpy()
        fig.add_trace(
            go.Bar(
                x=missing_df["timeline_x"],
                y=missing_df["_missing_height"],
                width=missing_width,
                marker={"color": "rgb(220,220,220)", "line": {"width": 0}},
                customdata=missing_hover,
                hovertemplate=(
                    "time_cluster=%{customdata[0]}<br>"
                    "row_idx=%{customdata[1]}<br>"
                    "missing data<extra></extra>"
                ),
                name="missing data",
            )
        )

    if not present_df.empty:
        hover_time = present_df["time_cluster"] if "time_cluster" in present_df.columns else present_df["timeline_x"]
        hover_row = present_df["row_idx"] if "row_idx" in present_df.columns else pd.Series([""] * len(present_df), index=present_df.index)
        customdata = pd.DataFrame(
            {
                "time_cluster": hover_time.astype(str),
                "row_idx": hover_row,
                "entropy": present_df[entropy_col],
            }
        ).to_numpy()

        fig.add_trace(
            go.Bar(
                x=present_df["timeline_x"],
                y=present_df[entropy_col],
                width=present_width,
                marker={"color": "rgb(52, 152, 219)", "line": {"width": 0}},
                customdata=customdata,
                hovertemplate=(
                    "time_cluster=%{customdata[0]}<br>"
                    "row_idx=%{customdata[1]}<br>"
                    "global_shannon_entropy=%{customdata[2]:.6g}<extra></extra>"
                ),
                name="global_shannon_entropy",
            )
        )

    ref_line_indices: list[int] = []
    if not plot_df.empty and "timeline_x" in plot_df.columns:
        line_x = [plot_df["timeline_x"].min(), plot_df["timeline_x"].max()]
    else:
        line_x = [0, 1]
    if pd.notna(dataset_mean):
        fig.add_trace(
            go.Scatter(
                x=line_x,
                y=[dataset_mean, dataset_mean],
                mode="lines",
                name="dataset mean",
                line={"color": "rgb(214,39,40)", "width": 2, "dash": "dash"},
                hoverinfo="skip",
                visible=True,
            )
        )
        ref_line_indices.append(len(fig.data) - 1)
    if pd.notna(dataset_median):
        fig.add_trace(
            go.Scatter(
                x=line_x,
                y=[dataset_median, dataset_median],
                mode="lines",
                name="dataset median",
                line={"color": "rgb(214,39,40)", "width": 2, "dash": "dash"},
                hoverinfo="skip",
                visible=False,
            )
        )
        ref_line_indices.append(len(fig.data) - 1)

    mean_annotation = {
        "xref": "paper",
        "yref": "y",
        "x": 0,
        "y": dataset_mean,
        "xanchor": "right",
        "xshift": -8,
        "text": f"{dataset_mean:.4f}",
        "showarrow": False,
        "font": {"color": "rgb(214,39,40)", "size": 12},
        "bgcolor": "rgba(255,255,255,0.9)",
        "visible": bool(pd.notna(dataset_mean)),
    }
    median_annotation = {
        "xref": "paper",
        "yref": "y",
        "x": 0,
        "y": dataset_median,
        "xanchor": "right",
        "xshift": -8,
        "text": f"{dataset_median:.4f}",
        "showarrow": False,
        "font": {"color": "rgb(214,39,40)", "size": 12},
        "bgcolor": "rgba(255,255,255,0.9)",
        "visible": False,
    }

    default_annotations = []
    if pd.notna(dataset_mean):
        default_annotations.append(mean_annotation)
    if pd.notna(dataset_median):
        default_annotations.append(median_annotation)

    fig.update_layout(
        title=title,
        barmode="overlay",
        plot_bgcolor="white",
        paper_bgcolor="white",
        updatemenus=[
            {
                "type": "buttons",
                "direction": "right",
                "x": 1.0,
                "xanchor": "right",
                "y": 1.22,
                "yanchor": "top",
                "showactive": True,
                "buttons": [
                    {
                        "label": "Mean",
                        "method": "update",
                        "args": [
                            {"visible": [True, False]},
                            {"annotations": [mean_annotation, median_annotation]},
                            ref_line_indices,
                        ],
                    },
                    {
                        "label": "Median",
                        "method": "update",
                        "args": [
                            {"visible": [False, True]},
                            {
                                "annotations": [
                                    {**mean_annotation, "visible": False},
                                    {**median_annotation, "visible": True},
                                ]
                            },
                            ref_line_indices,
                        ],
                    },
                ],
            }
        ] if len(ref_line_indices) == 2 else [],
        xaxis={"title": "time", "showgrid": False, "zeroline": False},
        yaxis={"title": "global_shannon_entropy", "showgrid": False, "zeroline": False},
        height=320,
        bargap=0.0,
        uirevision="entropy-static",
        showlegend=True,
        margin={"t": 80},
        annotations=default_annotations,
    )
    return fig
