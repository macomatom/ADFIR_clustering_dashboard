from __future__ import annotations

import html
from urllib.parse import quote
from typing import Any

import pandas as pd
import plotly.express as px


def cluster_color_map(cluster_ids: list[int]) -> dict[int, str]:
    palette = (
        px.colors.qualitative.Bold
        + px.colors.qualitative.Vivid
        + px.colors.qualitative.Dark24
        + px.colors.qualitative.Alphabet
    )
    return {cluster_id: palette[idx % len(palette)] for idx, cluster_id in enumerate(sorted(cluster_ids))}


def to_rgba(color: str, alpha: float) -> str:
    if color.startswith("rgba("):
        parts = [part.strip() for part in color[5:-1].split(",")]
        if len(parts) >= 3:
            return f"rgba({parts[0]},{parts[1]},{parts[2]},{alpha})"
    if color.startswith("rgb("):
        parts = [part.strip() for part in color[4:-1].split(",")]
        if len(parts) >= 3:
            return f"rgba({parts[0]},{parts[1]},{parts[2]},{alpha})"
    if color.startswith("#") and len(color) == 7:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        return f"rgba({r},{g},{b},{alpha})"
    return color


def format_cluster_label(cluster_id: int) -> str:
    return f"Cluster {cluster_id}"


def humanize_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("_", " ")


def build_cluster_option_labels(cluster_ids: list[int]) -> dict[str, int]:
    return {format_cluster_label(cluster_id): cluster_id for cluster_id in sorted(cluster_ids)}


def render_feature_overview_table(features_df: pd.DataFrame, *, include_cluster_id: bool = True) -> pd.DataFrame:
    if features_df.empty:
        return features_df
    preferred_cols = [
        "rank",
        "feature_name",
        "direction",
        "score_std",
        "delta_vs_global",
        "cluster_value",
        "global_value",
        "global_std",
    ]
    keep = ([c for c in ["cluster_id"] if include_cluster_id and c in features_df.columns]) + [c for c in preferred_cols if c in features_df.columns]
    out = features_df[keep].copy()
    for col in ["rank", "score_std", "delta_vs_global", "cluster_value", "global_value", "global_std"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    if "rank" in out.columns:
        sort_cols = ["rank"]
        ascending = [True]
        if "cluster_id" in out.columns:
            sort_cols = ["cluster_id", "rank"]
            ascending = [True, True]
        out = out.sort_values(sort_cols, ascending=ascending, na_position="last")
    return out.groupby("cluster_id", group_keys=False).head(10).reset_index(drop=True) if "cluster_id" in out.columns else out.head(10)


def render_cluster_summary_table(summary_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df.empty:
        return summary_df
    repeated_context_cols = [
        "row_type",
        "scope",
        "artifact",
        "aggregation",
        "window_s",
        "selected_k",
        "rows",
        "features_total",
        "silhouette_score",
        "davies_bouldin_score",
        "calinski_harabasz_score",
        "largest_cluster_size",
        "largest_cluster_frac",
        "attack_rate_global",
        "artifact_count",
        "incident_anchor_time",
        "time_cluster_min",
        "time_cluster_max",
        "status",
        "warnings",
        "best_cluster_attack_rate",
        "best_cluster_attack_lift",
        "n_clusters",
        "method",
        "linkage",
    ]
    priority = [
        "cluster_id",
        "cluster_size",
        "cluster_frac",
        "attack_count",
        "attack_rate",
        "attack_lift_vs_global",
        "closest_abs_distance_to_anchor",
        "frames_within_anchor_pm2",
        "frames_within_anchor_pm2_frac",
        "pre_anchor_within_pm2_count",
        "post_anchor_within_pm2_count",
        "incident_within_anchor_pm2_count",
    ]
    leading = [col for col in priority if col in summary_df.columns]
    remaining = [col for col in summary_df.columns if col not in leading and col not in repeated_context_cols]
    return summary_df[leading + remaining].copy()


def render_cluster_summary_context(summary_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df.empty:
        return pd.DataFrame(columns=["field", "value"])
    context_cols = [
        "row_type",
        "scope",
        "artifact",
        "aggregation",
        "window_s",
        "selected_k",
        "rows",
        "features_total",
        "silhouette_score",
        "davies_bouldin_score",
        "calinski_harabasz_score",
        "largest_cluster_size",
        "largest_cluster_frac",
        "attack_rate_global",
        "artifact_count",
        "incident_anchor_time",
        "time_cluster_min",
        "time_cluster_max",
        "status",
        "warnings",
        "best_cluster_attack_rate",
        "best_cluster_attack_lift",
        "n_clusters",
        "method",
        "linkage",
    ]
    rows: list[dict[str, Any]] = []
    first_row = summary_df.iloc[0]
    for col in context_cols:
        if col not in summary_df.columns:
            continue
        series = summary_df[col]
        non_na = series.dropna()
        if non_na.empty:
            value = ""
        else:
            value = first_row[col]
        rows.append({"field": str(col), "value": "" if pd.isna(value) else str(value)})
    return pd.DataFrame(rows)


def render_cluster_summary_dataframe(summary_df: pd.DataFrame) -> pd.DataFrame:
    return render_cluster_summary_table(summary_df)


def render_cluster_detail_table(detail_df: pd.DataFrame) -> pd.DataFrame:
    if detail_df.empty:
        return detail_df
    priority = [
        "time_cluster",
        "distance_from_incident_anchor",
        "abs_distance_from_incident_anchor",
        "incident_phase",
        "row_idx",
        "source_path",
        "window_id",
        "cluster_id",
        "n_clusters",
    ]
    leading = [col for col in priority if col in detail_df.columns]
    remaining = [
        col
        for col in detail_df.columns
        if col not in leading and col not in {"is_attack_related", "incident_phase_3class"}
    ]
    out = detail_df[leading + remaining].copy()
    if "distance_from_incident_anchor_human" in out.columns and "distance_from_incident_anchor" in out.columns:
        out["distance_from_incident_anchor"] = out["distance_from_incident_anchor_human"]
    if "abs_distance_from_incident_anchor_human" in out.columns and "abs_distance_from_incident_anchor" in out.columns:
        out["abs_distance_from_incident_anchor"] = out["abs_distance_from_incident_anchor_human"]
    for col in ["row_idx", "cluster_id", "n_clusters"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    drop_cols = [col for col in ["distance_from_incident_anchor_human", "abs_distance_from_incident_anchor_human"] if col in out.columns]
    if drop_cols:
        out = out.drop(columns=drop_cols)
    return out


def render_cluster_color_legend_html(cluster_ids: list[int], cluster_colors: dict[int, str]) -> str:
    chips: list[str] = []
    for cluster_id in cluster_ids:
        color = cluster_colors.get(int(cluster_id), "rgb(220,220,220)")
        chips.append(
            '<span style="display:inline-flex;align-items:center;gap:6px;'
            'padding:4px 8px;margin:0 8px 8px 0;border:1px solid #ececec;border-radius:999px;'
            'background:#fff;font-size:0.9rem;">'
            f'<span style="display:inline-block;width:12px;height:12px;border-radius:3px;'
            f'background:{color};border:1px solid rgba(0,0,0,0.08);"></span>'
            f'cluster {cluster_id}'
            '</span>'
        )
    return f'<div style="margin:0 0 10px 0;">{"".join(chips)}</div>'


def _cluster_color_swatch_data_uri(color: str) -> str:
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 16 16'>"
        f"<rect x='1' y='1' width='14' height='14' rx='3' ry='3' fill='{color}' "
        "stroke='rgba(0,0,0,0.12)' stroke-width='1'/>"
        "</svg>"
    )
    return f"data:image/svg+xml;utf8,{quote(svg)}"


def fill_cluster_summary_color_column(display_df: pd.DataFrame, cluster_colors: dict[int, str]) -> pd.DataFrame:
    if display_df.empty:
        return display_df
    out = display_df.copy()
    cluster_series = pd.to_numeric(out.get("cluster_id"), errors="coerce")
    swatches = [
        _cluster_color_swatch_data_uri(cluster_colors.get(int(cluster_series.iloc[idx]), "rgb(220,220,220)"))
        if pd.notna(cluster_series.iloc[idx])
        else _cluster_color_swatch_data_uri("rgb(220,220,220)")
        for idx in range(len(out))
    ]
    color_col = "cluster_col"
    if color_col in out.columns:
        out[color_col] = swatches
    else:
        out.insert(0, color_col, swatches)
    return out


def render_cluster_highlight_html(cluster_id: int, color: str, *, title: str) -> str:
    return (
        '<div style="margin:8px 0 10px 0;padding:10px 12px;border-left:6px solid '
        f'{color};background:rgba(0,0,0,0.03);border-radius:6px;">'
        f'<strong>{title}</strong>'
        f'<div style="font-size:0.9rem;opacity:0.8;">cluster {cluster_id}</div>'
        "</div>"
    )


def render_cluster_label_with_color(cluster_id: int, color: str) -> str:
    return (
        '<span style="display:inline-flex;align-items:center;gap:8px;">'
        f'<span style="display:inline-block;width:12px;height:12px;border-radius:999px;'
        f'background:{color};border:1px solid rgba(0,0,0,0.12);"></span>'
        f'<strong>Cluster {cluster_id}</strong>'
        "</span>"
    )


def _format_feature_cell(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def render_feature_table_html(features_df: pd.DataFrame, *, color: str, title: str) -> str:
    if features_df.empty:
        return "<p>No feature rows available.</p>"
    header_cells = "".join(
        f'<th style="text-align:left;padding:8px 10px;background:{color};color:#fff;white-space:nowrap;">'
        f"{html.escape(str(col))}</th>"
        for col in features_df.columns
    )
    body_rows: list[str] = []
    for _, row in features_df.iterrows():
        data_cells = "".join(
            f'<td style="padding:7px 10px;border-bottom:1px solid #eef1f4;white-space:nowrap;">'
            f"{html.escape(_format_feature_cell(row[col]))}</td>"
            for col in features_df.columns
        )
        body_rows.append(f"<tr>{data_cells}</tr>")
    return (
        f'<div style="margin:8px 0 14px 0;border:2px solid {color};border-radius:10px;overflow-x:auto;">'
        f'<div style="padding:10px 12px;background:{color};color:#fff;font-weight:700;">{html.escape(title)}</div>'
        '<table style="border-collapse:collapse;width:max-content;min-width:100%;font-size:0.92rem;background:#fff;">'
        f"<thead><tr>{header_cells}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )


def render_cluster_detail_table_html(detail_df: pd.DataFrame, *, color: str, title: str) -> str:
    if detail_df.empty:
        return "<p>No row details available.</p>"
    header_cells = "".join(
        f'<th style="text-align:left;padding:8px 10px;background:{color};color:#fff;white-space:nowrap;">'
        f"{html.escape(str(col))}</th>"
        for col in detail_df.columns
    )
    body_rows: list[str] = []
    for _, row in detail_df.iterrows():
        data_cells = "".join(
            f'<td style="padding:7px 10px;border-bottom:1px solid #eef1f4;white-space:nowrap;">'
            f"{html.escape(_format_feature_cell(row[col]))}</td>"
            for col in detail_df.columns
        )
        body_rows.append(f"<tr>{data_cells}</tr>")
    return (
        f'<div style="margin:8px 0 14px 0;border:2px solid {color};border-radius:10px;overflow-x:auto;">'
        f'<div style="padding:10px 12px;background:{color};color:#fff;font-weight:700;">{html.escape(title)}</div>'
        '<table style="border-collapse:collapse;width:max-content;min-width:100%;font-size:0.92rem;background:#fff;">'
        f"<thead><tr>{header_cells}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )


def sanitize_for_streamlit(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    for col in out.columns:
        dtype_name = str(out[col].dtype).lower()
        if dtype_name in {"str", "string", "string[python]", "string[pyarrow]", "object"}:
            out[col] = out[col].astype(object)
            out[col] = out[col].where(pd.notna(out[col]), None)
    return out
