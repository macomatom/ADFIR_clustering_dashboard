from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .ui_helpers import cluster_color_map, to_rgba

TIMELINE_BAR_Y0 = 0.38
TIMELINE_BAR_Y1 = 0.62
TIMELINE_BAR_HEIGHT = TIMELINE_BAR_Y1 - TIMELINE_BAR_Y0
TIMELINE_BAR_WIDTH_DEFAULT = 1.02
ENTROPY_BAR_WIDTH_DEFAULT = 1.0
TIMELINE_DENSE_MAX_PRESENT_ROWS = 5000
TIMELINE_DENSE_MAX_SLOTS = 10000
TIMELINE_MAX_RENDER_BARS = 2200
TIMELINE_MAX_RENDER_MISSING_BARS = 120


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


def _compress_timeline_rows(df: pd.DataFrame, *, window_s: int | None, max_bars: int) -> pd.DataFrame:
    if df.empty or len(df) <= max_bars:
        return df
    work = df.copy()
    timeline_x = work["timeline_x"]
    is_datetime = pd.api.types.is_datetime64_any_dtype(timeline_x) or pd.to_datetime(timeline_x, errors="coerce").notna().all()
    if is_datetime:
        x_num = pd.to_datetime(timeline_x, errors="coerce").astype("int64")
        width_scale = 1_000_000.0
    else:
        x_num = pd.to_numeric(timeline_x, errors="coerce")
        width_scale = 1.0
    valid_mask = pd.Series(x_num, index=work.index).notna()
    if valid_mask.sum() <= max_bars:
        return work
    work = work.loc[valid_mask].copy()
    work["_x_num"] = pd.Series(x_num, index=df.index).loc[valid_mask].astype("float64")
    x_min = float(work["_x_num"].min())
    x_max = float(work["_x_num"].max())
    if not pd.notna(x_min) or not pd.notna(x_max) or x_max <= x_min:
        return work.drop(columns="_x_num")
    bucket_width = max((x_max - x_min) / float(max_bars), 1.0)
    work["_bucket"] = ((work["_x_num"] - x_min) / bucket_width).astype(int)

    compressed_rows: list[dict[str, object]] = []
    for bucket_id, bucket_df in work.groupby("_bucket", sort=True):
        row = bucket_df.iloc[0].copy()
        row_idx_values = (
            pd.to_numeric(bucket_df["row_idx"], errors="coerce")
            if "row_idx" in bucket_df.columns
            else pd.Series([len(bucket_df)], index=bucket_df.index, dtype="float64")
        )
        row["row_idx"] = int(row_idx_values.fillna(0).sum()) or int(len(bucket_df))
        phase_mode = bucket_df["incident_phase_3class"].astype(str).mode(dropna=False)
        row["incident_phase_3class"] = phase_mode.iloc[0] if not phase_mode.empty else row.get("incident_phase_3class", "")
        if "_is_missing" in bucket_df.columns and bool(bucket_df["_is_missing"].all()):
            row["cluster_id"] = pd.NA
            row["_is_missing"] = True
            row["_color"] = "rgb(220,220,220)"
            if is_datetime:
                center_values_num = pd.to_datetime(bucket_df["timeline_x"], errors="coerce").astype("int64").astype("float64")
            else:
                center_values_num = pd.to_numeric(bucket_df["timeline_x"], errors="coerce").astype("float64")
            bar_width_values = (
                pd.to_numeric(bucket_df["_bar_width"], errors="coerce")
                if "_bar_width" in bucket_df.columns
                else pd.Series([bucket_width / width_scale] * len(bucket_df.index), index=bucket_df.index, dtype="float64")
            )
            widths_num = bar_width_values.fillna(0).astype("float64") * width_scale
            left_edges = center_values_num - (widths_num / 2.0)
            right_edges = center_values_num + (widths_num / 2.0)
            cover_left = float(left_edges.min())
            cover_right = float(right_edges.max())
            center_num = (cover_left + cover_right) / 2.0
            if is_datetime:
                row["timeline_x"] = pd.to_datetime(center_num, unit="ns", errors="coerce")
            else:
                row["timeline_x"] = float(center_num)
            row["_bar_width"] = float((cover_right - cover_left) / width_scale) or float(bucket_width / width_scale)
        else:
            bucket_center_num = x_min + (float(bucket_id) + 0.5) * bucket_width
            if is_datetime:
                row["timeline_x"] = pd.to_datetime(bucket_center_num, unit="ns", errors="coerce")
            else:
                row["timeline_x"] = float(bucket_center_num)
            present = bucket_df[~bucket_df["_is_missing"]].copy() if "_is_missing" in bucket_df.columns else bucket_df.copy()
            cluster_mode = pd.to_numeric(present["cluster_id"], errors="coerce").dropna().astype(int).mode()
            if not cluster_mode.empty:
                chosen_cluster = int(cluster_mode.iloc[0])
                row["cluster_id"] = chosen_cluster
                if "_color" in present.columns:
                    match = present[pd.to_numeric(present["cluster_id"], errors="coerce").fillna(-1).astype(int) == chosen_cluster]
                    if not match.empty:
                        row["_color"] = match.iloc[0]["_color"]
            row["_is_missing"] = False
            row["_bar_width"] = float(bucket_width / width_scale)
        row["_hover"] = [
            f"{bucket_df['timeline_x'].iloc[0]} -> {bucket_df['timeline_x'].iloc[-1]}",
            str(row.get("cluster_id", "missing")) if pd.notna(row.get("cluster_id", pd.NA)) else "missing",
            str(row.get("incident_phase_3class", "")),
            int(row["row_idx"]),
        ]
        compressed_rows.append(row.to_dict())
    compressed = pd.DataFrame(compressed_rows)
    drop_cols = [col for col in ["_bucket", "_x_num"] if col in compressed.columns]
    if drop_cols:
        compressed = compressed.drop(columns=drop_cols)
    return compressed.reset_index(drop=True)


def _coarsen_missing_gaps(df: pd.DataFrame, *, window_s: int | None) -> pd.DataFrame:
    if df.empty or "_bar_width" not in df.columns or not window_s or int(window_s) <= 0:
        return df
    work = df.copy()
    is_datetime = pd.api.types.is_datetime64_any_dtype(work["timeline_x"]) or pd.to_datetime(work["timeline_x"], errors="coerce").notna().all()
    unit_width = float(int(window_s) * 1000) if is_datetime else float(int(window_s))
    min_group_width = unit_width
    group_key = None
    if "_x_num" in work.columns:
        group_key = "_x_num"
    else:
        if is_datetime:
            numeric_x = pd.to_datetime(work["timeline_x"], errors="coerce").astype("int64").astype("float64")
        else:
            numeric_x = pd.to_numeric(work["timeline_x"], errors="coerce").astype("float64")
        work["_x_num"] = numeric_x
        group_key = "_x_num"
    work = work.sort_values(group_key).reset_index(drop=True)
    bucket_ids: list[int] = []
    current_bucket = 0
    bucket_end = None
    for x_num, bar_width in zip(work[group_key].tolist(), pd.to_numeric(work["_bar_width"], errors="coerce").fillna(unit_width).tolist(), strict=False):
        if bucket_end is None or x_num > bucket_end + min_group_width:
            current_bucket += 1
            bucket_end = x_num + max(float(bar_width), min_group_width)
        else:
            bucket_end = max(bucket_end, x_num + max(float(bar_width), min_group_width))
        bucket_ids.append(current_bucket)
    work["_missing_bucket"] = bucket_ids
    rows: list[dict[str, object]] = []
    for _, bucket_df in work.groupby("_missing_bucket", sort=True):
        row = bucket_df.iloc[len(bucket_df) // 2].copy()
        row["_bar_width"] = float(pd.to_numeric(bucket_df["_bar_width"], errors="coerce").fillna(unit_width).sum())
        if len(bucket_df) > 1:
            row_count = int(pd.to_numeric(bucket_df.get("row_idx"), errors="coerce").fillna(0).sum())
            row["row_idx"] = row_count if row_count > 0 else int(len(bucket_df))
            row["incident_phase_3class"] = f"missing ({row['row_idx']} windows)"
            row["_hover"] = [
                f"{bucket_df['timeline_x'].iloc[0]} -> {bucket_df['timeline_x'].iloc[-1]}",
                "missing",
                str(row["incident_phase_3class"]),
                int(row["row_idx"]),
            ]
        rows.append(row.to_dict())
    return pd.DataFrame(rows).drop(columns=[col for col in ["_missing_bucket", "_x_num"] if col in rows[0]], errors="ignore").reset_index(drop=True)


def _estimate_visible_window_count(source_df: pd.DataFrame, *, window_s: int | None) -> int | None:
    if source_df.empty or "timeline_x" not in source_df.columns or not window_s or int(window_s) <= 0:
        return None
    series = pd.Series(source_df["timeline_x"])
    if pd.api.types.is_datetime64_any_dtype(series) or pd.to_datetime(series, errors="coerce").notna().all():
        values = pd.to_datetime(series, errors="coerce").dropna()
        if values.empty:
            return None
        return int(round((values.max() - values.min()).total_seconds() / int(window_s))) + 1
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None
    return int(round((float(numeric.max()) - float(numeric.min())) / int(window_s))) + 1


def _build_dense_timeline_slots(
    timeline_df: pd.DataFrame,
    *,
    missing_source_df: pd.DataFrame,
    window_s: int | None,
) -> pd.DataFrame:
    def _fallback_without_dense() -> pd.DataFrame:
        out = timeline_df.copy()
        out["is_missing_window"] = False
        if "time_cluster" not in out.columns and "timeline_x" in out.columns:
            out["time_cluster"] = out["timeline_x"]
        return out

    def _build_sparse_missing_gap_slots(source_df: pd.DataFrame) -> pd.DataFrame:
        out = _fallback_without_dense()
        if source_df.empty or not window_s or int(window_s) <= 0 or "timeline_x" not in source_df.columns:
            return out
        source_x = pd.Series(source_df["timeline_x"])
        step_seconds = float(int(window_s))

        if pd.api.types.is_datetime64_any_dtype(source_x) or pd.to_datetime(source_x, errors="coerce").notna().any():
            centers = pd.to_datetime(source_x, errors="coerce").dropna().drop_duplicates().sort_values().reset_index(drop=True)
            if len(centers) < 2:
                return out
            gaps = centers.diff().iloc[1:]
            gap_rows: list[dict[str, object]] = []
            prev_values = centers.iloc[:-1].reset_index(drop=True)
            next_values = centers.iloc[1:].reset_index(drop=True)
            for prev_time, next_time, gap in zip(prev_values, next_values, gaps, strict=False):
                total_seconds = gap.total_seconds()
                missing_count = int(round(total_seconds / step_seconds)) - 1
                if missing_count <= 0:
                    continue
                midpoint = prev_time + (gap / 2)
                gap_rows.append(
                    {
                        "timeline_x": midpoint,
                        "time_cluster": f"{prev_time} -> {next_time}",
                        "cluster_id": pd.NA,
                        "incident_phase_3class": f"missing ({missing_count} windows)",
                        "row_idx": missing_count,
                        "is_missing_window": True,
                        "_bar_width": float(missing_count * step_seconds * 1000),
                    }
                )
        else:
            numeric_x = pd.to_numeric(source_x, errors="coerce").dropna().drop_duplicates().sort_values().reset_index(drop=True)
            if len(numeric_x) < 2:
                return out
            diffs = numeric_x.diff().iloc[1:]
            prev_values = numeric_x.iloc[:-1].reset_index(drop=True)
            next_values = numeric_x.iloc[1:].reset_index(drop=True)
            gap_rows = []
            for prev_value, next_value, gap in zip(prev_values, next_values, diffs, strict=False):
                total_seconds = float(gap)
                missing_count = int(round(total_seconds / step_seconds)) - 1
                if missing_count <= 0:
                    continue
                midpoint = float(prev_value + gap / 2.0)
                gap_rows.append(
                    {
                        "timeline_x": midpoint,
                        "time_cluster": f"{prev_value} -> {next_value}",
                        "cluster_id": pd.NA,
                        "incident_phase_3class": f"missing ({missing_count} windows)",
                        "row_idx": missing_count,
                        "is_missing_window": True,
                        "_bar_width": float(missing_count * step_seconds),
                    }
                )
        if not gap_rows:
            return out
        gaps_df = pd.DataFrame(gap_rows)
        return pd.concat([out, gaps_df], ignore_index=True, sort=False)

    if len(timeline_df) > TIMELINE_DENSE_MAX_PRESENT_ROWS:
        return _build_sparse_missing_gap_slots(missing_source_df)
    source_x = pd.to_datetime(missing_source_df.get("timeline_x"), errors="coerce")
    if source_x.notna().any() and window_s and int(window_s) > 0:
        slot_count = int(((source_x.dropna().max() - source_x.dropna().min()).total_seconds() / int(window_s))) + 1
        if slot_count > TIMELINE_DENSE_MAX_SLOTS:
            return _build_sparse_missing_gap_slots(missing_source_df)
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

    return _fallback_without_dense()


def build_timeline_plot(
    timeline_df: pd.DataFrame,
    *,
    highlighted_clusters: list[int],
    mute_non_selected: bool,
    title: str,
    window_s: int | None = None,
    missing_source_df: pd.DataFrame | None = None,
    max_present_bars: int | None = None,
    max_missing_bars: int | None = None,
    xaxis_range: list[object] | tuple[object, object] | None = None,
    height: int = 300,
) -> go.Figure:
    fig = go.Figure()
    if timeline_df.empty:
        fig.update_layout(title=title)
        return fig

    cluster_ids = sorted(pd.to_numeric(timeline_df["cluster_id"], errors="coerce").dropna().astype(int).unique().tolist())
    colors = cluster_color_map(cluster_ids)
    highlighted = set(int(x) for x in highlighted_clusters)
    hover_cols = ["time_cluster", "cluster_id", "incident_phase_3class", "row_idx"]
    missing_source = missing_source_df if missing_source_df is not None else timeline_df
    dense_timeline = _build_dense_timeline_slots(timeline_df, missing_source_df=missing_source, window_s=window_s)
    for col in hover_cols:
        if col not in dense_timeline.columns:
            dense_timeline[col] = ""
    dense_timeline = dense_timeline.copy()
    cluster_numeric = pd.to_numeric(dense_timeline.get("cluster_id"), errors="coerce")
    is_missing_series = (
        dense_timeline["is_missing_window"].astype(bool)
        if "is_missing_window" in dense_timeline.columns
        else pd.Series(False, index=dense_timeline.index)
    )
    dense_timeline["_is_missing"] = is_missing_series | cluster_numeric.isna()

    def _row_color(cluster_value: object, is_missing_window: object) -> str:
        if bool(is_missing_window) or pd.isna(cluster_value):
            return "rgb(220,220,220)"
        cluster_id = int(cluster_value)
        is_selected = not highlighted or cluster_id in highlighted
        if is_selected:
            return colors[cluster_id]
        return to_rgba(colors[cluster_id], 0.08) if mute_non_selected else to_rgba(colors[cluster_id], 0.35)

    dense_timeline["_color"] = [
        _row_color(cluster_value, is_missing)
        for cluster_value, is_missing in zip(cluster_numeric.tolist(), dense_timeline["_is_missing"].tolist(), strict=False)
    ]

    hover_frame = dense_timeline[[col for col in hover_cols if col in dense_timeline.columns]].copy()
    if "time_cluster" in hover_frame.columns:
        hover_frame["time_cluster"] = hover_frame["time_cluster"].astype(str)
    if "cluster_id" in hover_frame.columns:
        hover_frame["cluster_id"] = hover_frame["cluster_id"].astype(str)
    dense_timeline["_hover"] = hover_frame.to_numpy().tolist()

    missing_df = dense_timeline[dense_timeline["_is_missing"]].copy()
    present_df = dense_timeline[~dense_timeline["_is_missing"]].copy()
    present_bar_budget = int(max_present_bars or TIMELINE_MAX_RENDER_BARS)
    missing_bar_budget = int(max_missing_bars or TIMELINE_MAX_RENDER_MISSING_BARS)
    visible_window_count = _estimate_visible_window_count(missing_source, window_s=window_s)
    should_render_full_detail = visible_window_count is not None and visible_window_count <= present_bar_budget
    if not should_render_full_detail:
        missing_df = _compress_timeline_rows(missing_df, window_s=window_s, max_bars=missing_bar_budget)
        missing_df = _coarsen_missing_gaps(missing_df, window_s=window_s)
        present_df = _compress_timeline_rows(present_df, window_s=window_s, max_bars=present_bar_budget)

    missing_width_default = (
        missing_df["_bar_width"].tolist()
        if not missing_df.empty and "_bar_width" in missing_df.columns and missing_df["_bar_width"].notna().any()
        else _compute_bar_width_values(pd.Series(missing_df["timeline_x"]), window_s=window_s, bar_width_fraction=TIMELINE_BAR_WIDTH_DEFAULT)
        if not missing_df.empty
        else None
    )
    present_width_default = (
        present_df["_bar_width"].tolist()
        if not present_df.empty and "_bar_width" in present_df.columns and present_df["_bar_width"].notna().any()
        else _compute_bar_width_values(pd.Series(present_df["timeline_x"]), window_s=window_s, bar_width_fraction=TIMELINE_BAR_WIDTH_DEFAULT)
        if not present_df.empty
        else None
    )

    if not missing_df.empty:
        fig.add_trace(
            go.Bar(
                x=missing_df["timeline_x"],
                y=[TIMELINE_BAR_HEIGHT] * len(missing_df),
                base=TIMELINE_BAR_Y0,
                width=missing_width_default,
                name="missing data",
                marker={"color": ["rgb(220,220,220)"] * len(missing_df), "line": {"width": 0}},
                customdata=missing_df["_hover"].tolist(),
                hovertemplate=(
                    "time_cluster=%{customdata[0]}<br>"
                    "cluster_id=%{customdata[1]}<br>"
                    "incident_phase_3class=%{customdata[2]}<br>"
                    "row_idx=%{customdata[3]}<extra></extra>"
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
                    "incident_phase_3class=%{customdata[2]}<br>"
                    "row_idx=%{customdata[3]}<extra></extra>"
                ),
                showlegend=False,
            )
        )

    attack_window_trace = _build_attack_window_trace(timeline_df)
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
        height=height,
        legend_title_text="clusters",
        yaxis={
            "visible": False,
            "showgrid": False,
            "showticklabels": False,
            "zeroline": False,
            "range": [0.25, 0.75],
        },
    )
    if xaxis_range is not None and len(xaxis_range) == 2:
        fig.update_xaxes(range=list(xaxis_range))
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
