from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .clustering_service import get_assignments, get_cluster_detail_rows, get_cluster_summary, get_cluster_top_features
from .data_loader import DashboardRunBundle
from .ui_helpers import (
    cluster_color_map,
    render_cluster_summary_context,
    render_cluster_summary_dataframe,
    render_feature_overview_table,
)


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item") and callable(getattr(value, "item")):
        try:
            return _normalize_json_value(value.item())
        except (TypeError, ValueError):
            pass
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return value


def _sanitize_filename_component(value: Any, *, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    return "".join("_" if char.isspace() else char for char in text)


def _resolve_cluster_ids(assignments: pd.DataFrame) -> list[int]:
    if assignments.empty or "cluster_id" not in assignments.columns:
        return []
    return sorted(pd.to_numeric(assignments["cluster_id"], errors="coerce").dropna().astype(int).unique().tolist())


def _build_cluster_metadata(
    summary_df: pd.DataFrame,
    context_view: pd.DataFrame,
    cluster_id: int,
    *,
    cluster_color: str,
) -> dict[str, Any]:
    cluster_rows = summary_df[pd.to_numeric(summary_df["cluster_id"], errors="coerce").fillna(-1).astype(int) == int(cluster_id)]
    if cluster_rows.empty:
        return {"cluster_id": int(cluster_id), "cluster_color": cluster_color}

    rendered_row = render_cluster_summary_dataframe(cluster_rows).iloc[0].to_dict()
    raw_row = cluster_rows.iloc[0]
    metadata: dict[str, Any] = {"cluster_id": int(cluster_id), "cluster_color": cluster_color}
    metadata.update(rendered_row)

    for _, context_row in context_view.iterrows():
        field = str(context_row["field"])
        if field in metadata:
            continue
        metadata[field] = raw_row[field] if field in raw_row.index else context_row["value"]
    return metadata


def _try_parse_datetime(value: Any) -> pd.Timestamp | None:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        numeric = pd.to_numeric(pd.Series([stripped]), errors="coerce").iloc[0]
        if pd.notna(numeric) and all(char not in stripped for char in ("-", "/", ":", "T")):
            return None
    parsed = pd.to_datetime(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else pd.Timestamp(parsed)


def _build_ts_bounds(row: pd.Series, *, window_s: int | None) -> tuple[Any, Any]:
    time_value = row["time_cluster"] if "time_cluster" in row.index else pd.NA
    parsed_dt = _try_parse_datetime(time_value)
    if parsed_dt is not None:
        ts_start = parsed_dt.isoformat()
        ts_end = (parsed_dt + pd.Timedelta(seconds=int(window_s))).isoformat() if window_s and int(window_s) > 0 else None
        return ts_start, ts_end
    if "time_cluster" in row.index:
        return _normalize_json_value(time_value), None
    return _normalize_json_value(row.get("row_idx")), None


def _build_ts_objects(detail_rows: pd.DataFrame, *, window_s: int | None) -> list[dict[str, Any]]:
    if detail_rows.empty:
        return []
    detail_source = detail_rows.reset_index(drop=True)
    records: list[dict[str, Any]] = []
    for idx in range(len(detail_source)):
        ts_start, ts_end = _build_ts_bounds(detail_source.iloc[idx], window_s=window_s)
        record = {"ts_start": ts_start, "ts_end": ts_end}
        records.append(_normalize_json_value(record))
    return records


def _build_top_features(bundle: DashboardRunBundle, n_clusters: int, cluster_id: int) -> list[dict[str, Any]]:
    features = get_cluster_top_features(bundle, n_clusters, cluster_id)
    if features.empty:
        return []
    features_view = render_feature_overview_table(features, include_cluster_id=False)
    return [_normalize_json_value(record) for record in features_view.to_dict(orient="records")]


def build_cluster_export_payload(bundle: DashboardRunBundle, n_clusters: int) -> dict[str, Any]:
    assignments = get_assignments(bundle, n_clusters)
    summary = get_cluster_summary(bundle, n_clusters)
    cluster_ids = _resolve_cluster_ids(assignments)
    cluster_colors = cluster_color_map(cluster_ids)
    context_view = render_cluster_summary_context(summary)
    window_s = pd.to_numeric(pd.Series([bundle.manifest.get("window_s")]), errors="coerce").iloc[0]
    window_s_value = None if pd.isna(window_s) else int(window_s)

    payload: dict[str, Any] = {}
    for cluster_id in cluster_ids:
        detail_rows, _ = get_cluster_detail_rows(bundle, n_clusters, cluster_id, limit=None)
        payload[f"cluster_{cluster_id}"] = {
            "metadata": _normalize_json_value(
                _build_cluster_metadata(
                    summary,
                    context_view,
                    cluster_id,
                    cluster_color=cluster_colors.get(cluster_id, "rgb(220,220,220)"),
                )
            ),
            "ts_objects": _build_ts_objects(detail_rows, window_s=window_s_value),
            "top_features": _build_top_features(bundle, n_clusters, cluster_id),
        }
    return payload


def build_cluster_export_filename(bundle: DashboardRunBundle, n_clusters: int) -> str:
    artifact = _sanitize_filename_component(bundle.manifest.get("artifact"), fallback="run")
    aggregation = _sanitize_filename_component(bundle.manifest.get("aggregation"), fallback="unknown")
    window_s = pd.to_numeric(pd.Series([bundle.manifest.get("window_s")]), errors="coerce").iloc[0]
    window_label = f"{int(window_s)}s" if pd.notna(window_s) else "unknowns"
    return f"{artifact}__{aggregation}__{window_label}__k{int(n_clusters)}__clusters.json"
