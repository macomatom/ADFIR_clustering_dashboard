from __future__ import annotations

from typing import Any

import pandas as pd

from .data_loader import DashboardRunBundle


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
    out = bundle.assignments[pd.to_numeric(bundle.assignments["n_clusters"], errors="coerce").fillna(-1).astype(int) == int(n_clusters)].copy()
    if out.empty:
        return out
    time_col = str(bundle.manifest.get("time_col", "time_cluster"))
    sort_cols = [col for col in [time_col, "row_idx"] if col in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols, ascending=[True] * len(sort_cols)).reset_index(drop=True)
    return out


def get_cluster_summary(bundle: DashboardRunBundle, n_clusters: int) -> pd.DataFrame:
    out = bundle.summaries[pd.to_numeric(bundle.summaries["n_clusters"], errors="coerce").fillna(-1).astype(int) == int(n_clusters)].copy()
    if out.empty:
        return out
    if "cluster_id" in out.columns:
        out = out.sort_values("cluster_id").reset_index(drop=True)
    return out


def get_cluster_top_features(bundle: DashboardRunBundle, n_clusters: int, cluster_id: int) -> pd.DataFrame:
    out = bundle.features[
        (pd.to_numeric(bundle.features["n_clusters"], errors="coerce").fillna(-1).astype(int) == int(n_clusters))
        & (pd.to_numeric(bundle.features["cluster_id"], errors="coerce").fillna(-1).astype(int) == int(cluster_id))
    ].copy()
    if out.empty:
        return out
    if "rank" in out.columns:
        out["rank"] = pd.to_numeric(out["rank"], errors="coerce")
        out = out.sort_values(["rank", "feature_name"], ascending=[True, True]).reset_index(drop=True)
    else:
        out = out.assign(_abs_delta=pd.to_numeric(out["delta_vs_global"], errors="coerce").abs()).sort_values(
            ["_abs_delta", "feature_name"], ascending=[False, True]
        ).drop(columns="_abs_delta")
    return out


def get_all_cluster_top_features(bundle: DashboardRunBundle, n_clusters: int) -> pd.DataFrame:
    out = bundle.features[pd.to_numeric(bundle.features["n_clusters"], errors="coerce").fillna(-1).astype(int) == int(n_clusters)].copy()
    if out.empty:
        return out
    out["cluster_id"] = pd.to_numeric(out["cluster_id"], errors="coerce").fillna(-1).astype(int)
    if "rank" in out.columns:
        out["rank"] = pd.to_numeric(out["rank"], errors="coerce")
        out = out.sort_values(["cluster_id", "rank", "feature_name"], ascending=[True, True, True]).reset_index(drop=True)
    return out


def get_window_metrics(bundle: DashboardRunBundle) -> pd.DataFrame:
    return bundle.window_metrics.copy()


def build_entropy_timeline_df(bundle: DashboardRunBundle) -> pd.DataFrame:
    out = bundle.window_metrics.copy()
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
