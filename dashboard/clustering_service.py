from __future__ import annotations

from typing import Any

import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype

from .data_loader import DashboardRunBundle, load_dashboard_run


DETAIL_PRIORITY_COLS: tuple[str, ...] = (
    "time_cluster",
    "distance_from_incident_anchor_human",
    "distance_from_incident_anchor",
    "abs_distance_from_incident_anchor",
    "incident_phase",
    "row_idx",
    "source_path",
    "window_id",
    "cluster_id",
    "n_clusters",
)
BOUNDARY_WINDOW_THRESHOLD = 2


def _format_distance_human(distance_windows: object, *, window_s: int | None) -> str | None:
    value = pd.to_numeric(pd.Series([distance_windows]), errors="coerce").iloc[0]
    if pd.isna(value) or not window_s:
        return None
    total_seconds = int(round(float(value) * float(window_s)))
    sign = "-" if total_seconds < 0 else ""
    seconds_abs = abs(total_seconds)
    months, rem = divmod(seconds_abs, 30 * 86400)
    days, rem = divmod(rem, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)

    parts: list[str] = []
    if months:
        parts.append(f"{months}mo")
    if days or parts:
        parts.append(f"{days}d")
    if hours or parts:
        parts.append(f"{hours}h")
    if minutes or parts:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return f"{sign}{' '.join(parts)}"


def _load_child_bundle_for_k(bundle: DashboardRunBundle, n_clusters: int) -> DashboardRunBundle | None:
    child_map = bundle.cluster_run_dirs_by_k or {}
    child_run_dir = child_map.get(int(n_clusters))
    if child_run_dir is None:
        return None
    return load_dashboard_run(child_run_dir)


def _coerce_time_values(series: pd.Series) -> tuple[pd.Series, str | None]:
    if series.empty:
        return series.astype("Float64"), None
    if is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce"), "datetime"
    if is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce").astype("Float64"), "numeric"
    parsed_dt = pd.to_datetime(series, errors="coerce")
    if parsed_dt.notna().any():
        return parsed_dt, "datetime"
    parsed_num = pd.to_numeric(series, errors="coerce")
    if parsed_num.notna().any():
        return parsed_num.astype("Float64"), "numeric"
    return pd.Series([pd.NA] * len(series), index=series.index, dtype="Float64"), None


def _incident_phase_mask(series: pd.Series) -> pd.Series:
    normalized = series.astype("string").str.strip().str.lower()
    return normalized.isin({"incident_window", "incident", "1"})


def _resolve_anchor_time(assignments_df: pd.DataFrame, *, time_col: str) -> tuple[Any, str | None]:
    if time_col not in assignments_df.columns:
        return None, None
    time_values, time_mode = _coerce_time_values(assignments_df[time_col])
    if time_mode is None:
        return None, None
    if "incident_phase" in assignments_df.columns:
        incident_times = time_values.loc[_incident_phase_mask(assignments_df["incident_phase"])].dropna()
        if not incident_times.empty:
            return incident_times.min(), time_mode
    return None, time_mode


def _distance_from_anchor(
    time_values: pd.Series,
    *,
    anchor_time: Any,
    time_mode: str | None,
    window_s: int | None,
) -> pd.Series:
    if anchor_time is None or time_mode is None:
        return pd.Series([pd.NA] * len(time_values), index=time_values.index, dtype="Float64")
    if time_mode == "datetime":
        if not window_s:
            return pd.Series([pd.NA] * len(time_values), index=time_values.index, dtype="Float64")
        deltas = (pd.to_datetime(time_values, errors="coerce") - anchor_time).dt.total_seconds() / float(window_s)
        return deltas.astype("Float64")
    distances = pd.to_numeric(time_values, errors="coerce") - float(anchor_time)
    return distances.astype("Float64")


def get_timeline_axis_info(assignments_df: pd.DataFrame, *, time_col: str) -> dict[str, Any]:
    if assignments_df.empty:
        return {
            "time_mode": None,
            "data_min": None,
            "data_max": None,
            "anchor_time": None,
        }
    if time_col not in assignments_df.columns:
        time_col = "row_idx"
    time_values, time_mode = _coerce_time_values(assignments_df[time_col])
    non_na = time_values.dropna()
    anchor_time, _ = _resolve_anchor_time(assignments_df, time_col=time_col)
    return {
        "time_mode": time_mode,
        "data_min": non_na.min() if not non_na.empty else None,
        "data_max": non_na.max() if not non_na.empty else None,
        "anchor_time": anchor_time,
    }


def get_default_timeline_viewport(
    assignments_df: pd.DataFrame,
    *,
    time_col: str,
    window_s: int | None,
    anchor_half_span_hours: int = 6,
) -> dict[str, Any]:
    axis = get_timeline_axis_info(assignments_df, time_col=time_col)
    data_min = axis["data_min"]
    data_max = axis["data_max"]
    anchor_time = axis["anchor_time"]
    time_mode = axis["time_mode"]
    if data_min is None or data_max is None:
        return {
            **axis,
            "x_min": None,
            "x_max": None,
        }

    x_min = data_min
    x_max = data_max
    if anchor_time is not None:
        if time_mode == "datetime":
            span = pd.Timedelta(hours=int(anchor_half_span_hours))
            x_min = max(data_min, anchor_time - span)
            x_max = min(data_max, anchor_time + span)
        elif time_mode == "numeric" and window_s and int(window_s) > 0:
            half_span = float(anchor_half_span_hours * 3600) / float(window_s)
            x_min = max(float(data_min), float(anchor_time) - half_span)
            x_max = min(float(data_max), float(anchor_time) + half_span)
    return {
        **axis,
        "x_min": x_min,
        "x_max": x_max,
    }


def filter_timeline_to_viewport(
    timeline_df: pd.DataFrame,
    *,
    x_min: Any,
    x_max: Any,
    window_s: int | None,
    padding_windows: int = 1,
) -> pd.DataFrame:
    if timeline_df.empty or x_min is None or x_max is None or "timeline_x" not in timeline_df.columns:
        return timeline_df.copy()
    time_values, time_mode = _coerce_time_values(timeline_df["timeline_x"])
    if time_mode is None:
        return timeline_df.copy()

    if time_mode == "datetime":
        left = pd.to_datetime(x_min, errors="coerce")
        right = pd.to_datetime(x_max, errors="coerce")
        if pd.isna(left) or pd.isna(right):
            return timeline_df.copy()
        padding = pd.Timedelta(seconds=int(window_s) * int(padding_windows)) if window_s and int(window_s) > 0 else pd.Timedelta(0)
        mask = (time_values >= left - padding) & (time_values <= right + padding)
    else:
        left = pd.to_numeric(pd.Series([x_min]), errors="coerce").iloc[0]
        right = pd.to_numeric(pd.Series([x_max]), errors="coerce").iloc[0]
        if pd.isna(left) or pd.isna(right):
            return timeline_df.copy()
        padding = float(int(window_s) * int(padding_windows)) if window_s and int(window_s) > 0 else 0.0
        numeric_values = pd.to_numeric(time_values, errors="coerce")
        mask = (numeric_values >= float(left) - padding) & (numeric_values <= float(right) + padding)
    return timeline_df.loc[mask.fillna(False)].copy().reset_index(drop=True)


def get_available_k(bundle: DashboardRunBundle) -> list[int]:
    manifest_values = [int(x) for x in bundle.manifest.get("available_k", [])]
    filtered_manifest_values = [value for value in manifest_values if not (2 <= int(value) <= 6)]
    if filtered_manifest_values:
        return sorted(filtered_manifest_values)
    if manifest_values:
        return sorted(manifest_values)
    assignment_values = sorted(bundle.assignments["n_clusters"].dropna().astype(int).unique().tolist())
    filtered_assignment_values = [value for value in assignment_values if not (2 <= int(value) <= 6)]
    return filtered_assignment_values or assignment_values


def get_assignments(bundle: DashboardRunBundle, n_clusters: int) -> pd.DataFrame:
    if bundle.assignments.empty and bundle.cluster_run_dirs_by_k:
        child_bundle = _load_child_bundle_for_k(bundle, n_clusters)
        if child_bundle is None:
            return pd.DataFrame()
        return get_assignments(child_bundle, n_clusters)
    out = bundle.assignments[pd.to_numeric(bundle.assignments["n_clusters"], errors="coerce").fillna(-1).astype(int) == int(n_clusters)].copy()
    if out.empty:
        return out
    time_col = str(bundle.manifest.get("time_col", "time_cluster"))
    sort_cols = [col for col in [time_col, "row_idx"] if col in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols, ascending=[True] * len(sort_cols)).reset_index(drop=True)
    return out


def _sort_cluster_detail_rows(detail_df: pd.DataFrame, *, time_col: str) -> pd.DataFrame:
    out = detail_df.copy()
    if "cluster_id" in out.columns:
        out["cluster_id"] = pd.to_numeric(out["cluster_id"], errors="coerce").fillna(-1).astype(int)
    if "n_clusters" in out.columns:
        out["n_clusters"] = pd.to_numeric(out["n_clusters"], errors="coerce").fillna(-1).astype(int)
    if "distance_from_incident_anchor" in out.columns:
        out["abs_distance_from_incident_anchor"] = pd.to_numeric(out["distance_from_incident_anchor"], errors="coerce").abs()
    else:
        out["abs_distance_from_incident_anchor"] = pd.Series([pd.NA] * len(out), index=out.index, dtype="Float64")
    sort_cols = [col for col in ["abs_distance_from_incident_anchor", time_col, "row_idx"] if col in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols, ascending=[True] * len(sort_cols), na_position="last").reset_index(drop=True)
    return out


def _build_boundary_metrics(assignments_df: pd.DataFrame, summary_df: pd.DataFrame, *, time_col: str, window_s: int | None) -> pd.DataFrame:
    out = summary_df.copy()
    if out.empty or "cluster_id" not in out.columns:
        return out
    anchor_time, time_mode = _resolve_anchor_time(assignments_df, time_col=time_col)
    if anchor_time is None or time_col not in assignments_df.columns:
        out["incident_anchor_time"] = pd.NA
        out["closest_abs_distance_to_anchor"] = pd.NA
        out["frames_within_anchor_pm2"] = pd.NA
        out["frames_within_anchor_pm2_frac"] = pd.NA
        out["pre_anchor_within_pm2_count"] = pd.NA
        out["post_anchor_within_pm2_count"] = pd.NA
        out["incident_within_anchor_pm2_count"] = pd.NA
        return out

    detail = assignments_df.copy()
    detail["cluster_id"] = pd.to_numeric(detail["cluster_id"], errors="coerce").fillna(-1).astype(int)
    time_values, _ = _coerce_time_values(detail[time_col])
    detail["distance_from_incident_anchor"] = _distance_from_anchor(
        time_values,
        anchor_time=anchor_time,
        time_mode=time_mode,
        window_s=window_s,
    )
    detail["abs_distance_from_incident_anchor"] = pd.to_numeric(detail["distance_from_incident_anchor"], errors="coerce").abs()
    within_mask = detail["abs_distance_from_incident_anchor"] <= float(BOUNDARY_WINDOW_THRESHOLD)
    incident_mask = (
        _incident_phase_mask(detail["incident_phase"])
        if "incident_phase" in detail.columns
        else pd.Series(False, index=detail.index, dtype="boolean")
    )

    metrics_rows: list[dict[str, Any]] = []
    for cluster_id in pd.to_numeric(out["cluster_id"], errors="coerce").fillna(-1).astype(int).tolist():
        cluster_rows = detail[detail["cluster_id"] == int(cluster_id)].copy()
        cluster_within = cluster_rows[within_mask.loc[cluster_rows.index]].copy()
        closest = pd.to_numeric(cluster_rows["abs_distance_from_incident_anchor"], errors="coerce").dropna()
        metrics_rows.append(
            {
                "cluster_id": int(cluster_id),
                "incident_anchor_time": anchor_time,
                "closest_abs_distance_to_anchor": float(closest.min()) if not closest.empty else pd.NA,
                "frames_within_anchor_pm2": int(len(cluster_within)),
                "frames_within_anchor_pm2_frac": float(len(cluster_within) / len(cluster_rows)) if len(cluster_rows) else pd.NA,
                "pre_anchor_within_pm2_count": int((pd.to_numeric(cluster_within["distance_from_incident_anchor"], errors="coerce") < 0).sum()),
                "post_anchor_within_pm2_count": int((pd.to_numeric(cluster_within["distance_from_incident_anchor"], errors="coerce") > 0).sum()),
                "incident_within_anchor_pm2_count": int(incident_mask.loc[cluster_within.index].fillna(False).sum()),
            }
        )
    metrics_df = pd.DataFrame(metrics_rows)
    return out.merge(metrics_df, on="cluster_id", how="left")


def get_cluster_detail_rows(bundle: DashboardRunBundle, n_clusters: int, cluster_id: int, *, limit: int = 50) -> tuple[pd.DataFrame, int]:
    assignments = get_assignments(bundle, n_clusters)
    if assignments.empty:
        return assignments, 0
    detail = assignments[pd.to_numeric(assignments["cluster_id"], errors="coerce").fillna(-1).astype(int) == int(cluster_id)].copy()
    if detail.empty:
        return detail, 0
    time_col = str(bundle.manifest.get("time_col", "time_cluster"))
    anchor_time, time_mode = _resolve_anchor_time(assignments, time_col=time_col)
    if anchor_time is not None and time_col in detail.columns:
        time_values, _ = _coerce_time_values(detail[time_col])
        detail["distance_from_incident_anchor"] = _distance_from_anchor(
            time_values,
            anchor_time=anchor_time,
            time_mode=time_mode,
            window_s=int(bundle.manifest.get("window_s", 0) or 0),
        )
    else:
        detail["distance_from_incident_anchor"] = pd.Series([pd.NA] * len(detail), index=detail.index, dtype="Float64")
    detail["abs_distance_from_incident_anchor"] = pd.to_numeric(detail["distance_from_incident_anchor"], errors="coerce").abs()
    detail["distance_from_incident_anchor_human"] = [
        _format_distance_human(value, window_s=int(bundle.manifest.get("window_s", 0) or 0))
        for value in detail["distance_from_incident_anchor"].tolist()
    ]
    detail["abs_distance_from_incident_anchor_human"] = [
        _format_distance_human(value, window_s=int(bundle.manifest.get("window_s", 0) or 0))
        for value in detail["abs_distance_from_incident_anchor"].tolist()
    ]
    detail = _sort_cluster_detail_rows(detail, time_col=time_col)
    total_rows = int(len(detail))
    limited = detail.head(int(limit)).reset_index(drop=True)
    return limited, total_rows


def get_cluster_summary(bundle: DashboardRunBundle, n_clusters: int) -> pd.DataFrame:
    if bundle.summaries.empty and bundle.cluster_run_dirs_by_k:
        child_bundle = _load_child_bundle_for_k(bundle, n_clusters)
        if child_bundle is None:
            return pd.DataFrame()
        return get_cluster_summary(child_bundle, n_clusters)
    out = bundle.summaries[pd.to_numeric(bundle.summaries["n_clusters"], errors="coerce").fillna(-1).astype(int) == int(n_clusters)].copy()
    if out.empty:
        return out
    assignments = get_assignments(bundle, n_clusters)
    time_col = str(bundle.manifest.get("time_col", "time_cluster"))
    out = _build_boundary_metrics(assignments, out, time_col=time_col, window_s=int(bundle.manifest.get("window_s", 0) or 0))
    if "cluster_id" in out.columns:
        out = out.sort_values("cluster_id").reset_index(drop=True)
    return out


def get_cluster_top_features(bundle: DashboardRunBundle, n_clusters: int, cluster_id: int) -> pd.DataFrame:
    if bundle.features.empty and bundle.cluster_run_dirs_by_k:
        child_bundle = _load_child_bundle_for_k(bundle, n_clusters)
        if child_bundle is None:
            return pd.DataFrame()
        return get_cluster_top_features(child_bundle, n_clusters, cluster_id)
    out = bundle.features[
        (pd.to_numeric(bundle.features["n_clusters"], errors="coerce").fillna(-1).astype(int) == int(n_clusters))
        & (pd.to_numeric(bundle.features["cluster_id"], errors="coerce").fillna(-1).astype(int) == int(cluster_id))
    ].copy()
    if out.empty:
        return out
    if "rank" in out.columns:
        out["rank"] = pd.to_numeric(out["rank"], errors="coerce")
        out = out.sort_values(["rank", "feature_name"], ascending=[True, True]).reset_index(drop=True)
    elif "score_std" in out.columns:
        out = out.assign(_abs_score_std=pd.to_numeric(out["score_std"], errors="coerce").abs()).sort_values(
            ["_abs_score_std", "score_std", "feature_name"], ascending=[False, False, True]
        ).drop(columns="_abs_score_std")
    else:
        out = out.assign(_abs_delta=pd.to_numeric(out["delta_vs_global"], errors="coerce").abs()).sort_values(
            ["_abs_delta", "feature_name"], ascending=[False, True]
        ).drop(columns="_abs_delta")
    return out


def get_all_cluster_top_features(bundle: DashboardRunBundle, n_clusters: int) -> pd.DataFrame:
    if bundle.features.empty and bundle.cluster_run_dirs_by_k:
        child_bundle = _load_child_bundle_for_k(bundle, n_clusters)
        if child_bundle is None:
            return pd.DataFrame()
        return get_all_cluster_top_features(child_bundle, n_clusters)
    out = bundle.features[pd.to_numeric(bundle.features["n_clusters"], errors="coerce").fillna(-1).astype(int) == int(n_clusters)].copy()
    if out.empty:
        return out
    out["cluster_id"] = pd.to_numeric(out["cluster_id"], errors="coerce").fillna(-1).astype(int)
    if "rank" in out.columns:
        out["rank"] = pd.to_numeric(out["rank"], errors="coerce")
        out = out.sort_values(["cluster_id", "rank", "feature_name"], ascending=[True, True, True]).reset_index(drop=True)
    elif "score_std" in out.columns:
        out = out.assign(_abs_score_std=pd.to_numeric(out["score_std"], errors="coerce").abs()).sort_values(
            ["cluster_id", "_abs_score_std", "score_std", "feature_name"], ascending=[True, False, False, True]
        ).drop(columns="_abs_score_std").reset_index(drop=True)
    return out


def get_window_metrics(bundle: DashboardRunBundle, n_clusters: int | None = None) -> pd.DataFrame:
    if bundle.window_metrics.empty and bundle.cluster_run_dirs_by_k and n_clusters is not None:
        child_bundle = _load_child_bundle_for_k(bundle, n_clusters)
        if child_bundle is None:
            return pd.DataFrame()
        return get_window_metrics(child_bundle, n_clusters)
    return bundle.window_metrics.copy()


def build_entropy_timeline_df(bundle: DashboardRunBundle, n_clusters: int | None = None) -> pd.DataFrame:
    out = get_window_metrics(bundle, n_clusters).copy()
    if out.empty:
        return out
    entropy_col = str(bundle.manifest.get("entropy_default_col") or "global_shannon_entropy")
    if entropy_col not in out.columns:
        return pd.DataFrame(columns=["timeline_x", "row_idx", entropy_col])
    time_col = "time_cluster" if "time_cluster" in out.columns else "row_idx"
    out["timeline_x"] = out[time_col]
    sort_cols = [col for col in [time_col, "row_idx"] if col in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols, ascending=[True] * len(sort_cols)).reset_index(drop=True)
    return out


def build_timeline_df(assignments_df: pd.DataFrame, *, time_col: str) -> pd.DataFrame:
    timeline = assignments_df.copy()
    if time_col not in timeline.columns:
        time_col = "row_idx"
    timeline["timeline_x"] = timeline[time_col]
    timeline["cluster_id"] = pd.to_numeric(timeline["cluster_id"], errors="coerce").fillna(-1).astype(int)
    return timeline


def build_summary_metrics(assignments_df: pd.DataFrame, summary_df: pd.DataFrame, active_cluster: int | None) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "total_windows": int(len(assignments_df)),
        "cluster_count": int(summary_df["cluster_id"].nunique()) if "cluster_id" in summary_df.columns else 0,
        "active_cluster_size": 0,
    }
    if active_cluster is not None and not summary_df.empty:
        match = summary_df[pd.to_numeric(summary_df["cluster_id"], errors="coerce").fillna(-1).astype(int) == int(active_cluster)]
        if not match.empty and "cluster_size" in match.columns:
            metrics["active_cluster_size"] = int(pd.to_numeric(match.iloc[0]["cluster_size"], errors="coerce"))
    return metrics
