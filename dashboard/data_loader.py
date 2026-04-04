from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_ASSIGNMENT_COLS = {
    "window_id",
    "source_path",
    "row_idx",
    "artifact",
    "aggregation",
    "method",
    "linkage",
    "n_clusters",
    "cluster_id",
    "pc1",
    "pc2",
}

REQUIRED_SUMMARY_COLS = {"n_clusters", "cluster_id", "cluster_size", "cluster_frac"}
REQUIRED_FEATURE_COLS = {"n_clusters", "cluster_id", "rank", "feature_name", "delta_vs_global", "cluster_value", "global_value"}
PREFERRED_FEATURE_COLS = {"global_std", "score_std", "direction"}
REQUIRED_WINDOW_METRIC_COLS = {"window_id", "row_idx"}


@dataclass(slots=True)
class DashboardRunBundle:
    run_dir: Path
    manifest: dict[str, Any]
    assignments: pd.DataFrame
    summaries: pd.DataFrame
    features: pd.DataFrame
    window_metrics: pd.DataFrame
    cluster_run_dirs_by_k: dict[int, Path] | None = None


@dataclass(slots=True)
class DashboardRunOption:
    run_dir: Path
    artifact: str
    aggregation: str
    window_s: int | None
    method: str
    source_mode: str
    label: str


def _load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _coerce_int(value: Any) -> int | None:
    series = pd.to_numeric(pd.Series([value]), errors="coerce")
    if series.isna().iloc[0]:
        return None
    return int(series.iloc[0])


def _validate_required_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported dashboard table format: {path}")


@lru_cache(maxsize=256)
def _read_table_cached(path_str: str) -> pd.DataFrame:
    return _read_table(Path(path_str))


def _normalize_assignments(assignments: pd.DataFrame, manifest: dict[str, Any]) -> pd.DataFrame:
    out = assignments.copy()
    if "n_clusters" not in out.columns and "selected_k" in out.columns:
        out["n_clusters"] = pd.to_numeric(out["selected_k"], errors="coerce")
    if "window_id" not in out.columns:
        source_series = out["source_path"].astype(str) if "source_path" in out.columns else pd.Series(["window"] * len(out), index=out.index)
        fallback_row_idx = pd.Series(out.index, index=out.index)
        row_series = pd.to_numeric(out["row_idx"], errors="coerce").fillna(fallback_row_idx).astype(int)
        out["window_id"] = source_series + "::" + row_series.astype(str)
    if "method" not in out.columns:
        out["method"] = manifest.get("method")
    if "linkage" not in out.columns:
        out["linkage"] = manifest.get("linkage")
    return out


def _normalize_summaries(summaries: pd.DataFrame, manifest: dict[str, Any]) -> pd.DataFrame:
    out = summaries.copy()
    if "row_type" in out.columns:
        cluster_rows = out[out["row_type"].astype(str) == "cluster"].copy()
        if not cluster_rows.empty:
            out = cluster_rows
    if "n_clusters" not in out.columns and "selected_k" in out.columns:
        out["n_clusters"] = pd.to_numeric(out["selected_k"], errors="coerce")
    return out


def _normalize_features(features: pd.DataFrame, manifest: dict[str, Any]) -> pd.DataFrame:
    out = features.copy()
    if "n_clusters" not in out.columns and "selected_k" in out.columns:
        out["n_clusters"] = pd.to_numeric(out["selected_k"], errors="coerce")
    missing_preferred = sorted(PREFERRED_FEATURE_COLS - set(out.columns))
    for col in missing_preferred:
        out[col] = pd.NA
    return out


def _cluster_child_run_dirs(run_dir: Path) -> list[Path]:
    return sorted(path for path in run_dir.iterdir() if path.is_dir() and (path / "cluster_manifest__v1.json").exists())


def _selected_k_from_manifest(manifest: dict[str, Any]) -> int | None:
    return _coerce_int(manifest.get("selected_k"))


@lru_cache(maxsize=256)
def _cached_cluster_run_tables(run_dir_str: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    run_dir = Path(run_dir_str)
    manifest = _load_manifest(run_dir / "cluster_manifest__v1.json")
    assignments = _normalize_assignments(_read_table_cached(str(run_dir / "cluster_assignments__v1.parquet")), manifest)
    summaries = _normalize_summaries(_read_table_cached(str(run_dir / "cluster_summary__v1.csv")), manifest)
    features = _normalize_features(_read_table_cached(str(run_dir / "cluster_features__v1.csv")), manifest)
    window_metrics_cols = [col for col in ["window_id", "row_idx", "time_cluster"] if col in assignments.columns]
    window_metrics = assignments[window_metrics_cols].copy() if window_metrics_cols else pd.DataFrame()
    normalized_manifest = {
        **manifest,
        "available_k": [int(manifest["selected_k"])] if manifest.get("selected_k") is not None else [],
        "assignments_file": "cluster_assignments__v1.parquet",
        "summary_file": "cluster_summary__v1.csv",
        "features_file": "cluster_features__v1.csv",
        "window_metrics_file": None,
        "time_col": "time_cluster" if "time_cluster" in assignments.columns else "row_idx",
    }
    return assignments, summaries, features, window_metrics, normalized_manifest


def _load_collection_child_bundle(run_dir: Path) -> DashboardRunBundle:
    assignments, summaries, features, window_metrics, manifest = _cached_cluster_run_tables(str(run_dir))
    _validate_required_columns(assignments, REQUIRED_ASSIGNMENT_COLS, "assignments")
    _validate_required_columns(summaries, REQUIRED_SUMMARY_COLS, "summaries")
    _validate_required_columns(features, REQUIRED_FEATURE_COLS, "features")
    if not window_metrics.empty:
        _validate_required_columns(window_metrics, REQUIRED_WINDOW_METRIC_COLS, "window_metrics")
    return DashboardRunBundle(
        run_dir=run_dir,
        manifest=manifest,
        assignments=assignments.copy(),
        summaries=summaries.copy(),
        features=features.copy(),
        window_metrics=window_metrics.copy(),
    )


def _include_cluster_k(selected_k: int | None) -> bool:
    return selected_k is None or not (2 <= int(selected_k) <= 6)


def _infer_run_context_from_path(run_dir: Path) -> tuple[str, str, int | None]:
    parts = run_dir.parts
    for marker in ("dashboard", "clustering"):
        if marker in parts:
            idx = parts.index(marker)
            if idx >= 3:
                artifact = str(parts[idx - 3])
                aggregation = str(parts[idx - 2])
                window_raw = str(parts[idx - 1]).rstrip("s")
                window_s = _coerce_int(window_raw)
                return artifact, aggregation, window_s
    return str(run_dir.name), "", None


def _build_run_label(*, artifact: str, aggregation: str, window_s: int | None, method: str) -> str:
    parts = [artifact]
    if aggregation:
        parts.append(aggregation)
    if window_s is not None:
        parts.append(f"{window_s}s")
    if method:
        parts.append(method)
    return " | ".join(parts)


def _describe_run(run_dir: Path) -> DashboardRunOption:
    child_cluster_runs = _cluster_child_run_dirs(run_dir) if run_dir.exists() and run_dir.is_dir() else []
    inferred_artifact, inferred_aggregation, inferred_window_s = _infer_run_context_from_path(run_dir)

    if child_cluster_runs:
        child_manifests = [
            _load_manifest(child_dir / "cluster_manifest__v1.json")
            for child_dir in child_cluster_runs
            if _include_cluster_k(_selected_k_from_manifest(_load_manifest(child_dir / "cluster_manifest__v1.json")))
        ]
        if not child_manifests:
            raise FileNotFoundError(f"No supported cluster child runs found under: {run_dir}")
        manifest = max(child_manifests, key=lambda item: _selected_k_from_manifest(item) or -1)
        source_mode = "cluster_collection"
    else:
        dashboard_manifest_path = run_dir / "dashboard_manifest__v1.json"
        cluster_manifest_path = run_dir / "cluster_manifest__v1.json"
        if dashboard_manifest_path.exists():
            manifest = _load_manifest(dashboard_manifest_path)
            source_mode = "dashboard_export"
        elif cluster_manifest_path.exists():
            manifest = _load_manifest(cluster_manifest_path)
            source_mode = "cluster_run"
        else:
            raise FileNotFoundError(f"Missing dashboard manifest under: {run_dir}")

    artifact = str(manifest.get("artifact") or inferred_artifact)
    aggregation = str(manifest.get("aggregation") or inferred_aggregation)
    window_s = _coerce_int(manifest.get("window_s"))
    if window_s is None:
        window_s = inferred_window_s
    method = str(manifest.get("method") or run_dir.name)

    return DashboardRunOption(
        run_dir=run_dir,
        artifact=artifact,
        aggregation=aggregation,
        window_s=window_s,
        method=method,
        source_mode=source_mode,
        label=_build_run_label(artifact=artifact, aggregation=aggregation, window_s=window_s, method=method),
    )


def _load_cluster_run(run_dir: Path, manifest: dict[str, Any]) -> DashboardRunBundle:
    return _load_collection_child_bundle(run_dir)


def _load_cluster_collection_run(run_dir: Path) -> DashboardRunBundle:
    child_dirs = _cluster_child_run_dirs(run_dir)
    if not child_dirs:
        raise FileNotFoundError(f"No cluster child runs found under: {run_dir}")
    child_entries = [
        (child_dir, _load_manifest(child_dir / "cluster_manifest__v1.json"))
        for child_dir in child_dirs
    ]
    child_entries = [(child_dir, manifest) for child_dir, manifest in child_entries if _include_cluster_k(_selected_k_from_manifest(manifest))]
    if not child_entries:
        raise FileNotFoundError(f"No supported cluster child runs found under: {run_dir}")
    latest_manifest = max(child_entries, key=lambda item: _selected_k_from_manifest(item[1]) or -1)[1]
    available_k = sorted(
        {
            int(k)
            for _, manifest in child_entries
            for k in [manifest.get("selected_k")]
            if pd.notna(k)
        }
    )
    manifest = {
        **latest_manifest,
        "selected_k": None,
        "available_k": available_k,
        "source_mode": "cluster_collection",
        "time_col": "time_cluster",
    }

    return DashboardRunBundle(
        run_dir=run_dir,
        manifest=manifest,
        assignments=pd.DataFrame(),
        summaries=pd.DataFrame(),
        features=pd.DataFrame(),
        window_metrics=pd.DataFrame(),
        cluster_run_dirs_by_k={int(_selected_k_from_manifest(manifest) or -1): child_dir for child_dir, manifest in child_entries},
    )


def load_dashboard_run(run_dir: Path) -> DashboardRunBundle:
    run_dir = Path(run_dir)
    child_cluster_runs = _cluster_child_run_dirs(run_dir) if run_dir.exists() and run_dir.is_dir() else []
    if child_cluster_runs:
        return _load_cluster_collection_run(run_dir)
    manifest_path = run_dir / "dashboard_manifest__v1.json"
    cluster_manifest_path = run_dir / "cluster_manifest__v1.json"
    if manifest_path.exists():
        manifest = _load_manifest(manifest_path)

        assignments = _normalize_assignments(_read_table(run_dir / str(manifest["assignments_file"])), manifest)
        summaries = _normalize_summaries(_read_table(run_dir / str(manifest["summary_file"])), manifest)
        features = _normalize_features(_read_table(run_dir / str(manifest["features_file"])), manifest)
        window_metrics_file = manifest.get("window_metrics_file")
        window_metrics = _read_table(run_dir / str(window_metrics_file)) if window_metrics_file else pd.DataFrame()

        _validate_required_columns(assignments, REQUIRED_ASSIGNMENT_COLS, "assignments")
        _validate_required_columns(summaries, REQUIRED_SUMMARY_COLS, "summaries")
        _validate_required_columns(features, REQUIRED_FEATURE_COLS, "features")
        if not window_metrics.empty:
            _validate_required_columns(window_metrics, REQUIRED_WINDOW_METRIC_COLS, "window_metrics")

        return DashboardRunBundle(
            run_dir=run_dir,
            manifest=manifest,
            assignments=assignments,
            summaries=summaries,
            features=features,
            window_metrics=window_metrics,
        )
    if cluster_manifest_path.exists():
        return _load_cluster_run(run_dir, _load_manifest(cluster_manifest_path))
    raise FileNotFoundError(f"Missing dashboard manifest: {manifest_path} or cluster manifest: {cluster_manifest_path}")


def discover_dashboard_runs(root: Path) -> list[Path]:
    root = Path(root)
    dashboard_runs = {path.parent for path in root.rglob("dashboard_manifest__v1.json")}
    cluster_manifest_paths = list(root.rglob("cluster_manifest__v1.json"))
    single_cluster_runs = {path.parent for path in cluster_manifest_paths}
    collection_runs = {path.parent.parent for path in cluster_manifest_paths}
    filtered_single_cluster_runs = {path for path in single_cluster_runs if path.parent not in collection_runs}
    filtered_single_cluster_runs = {
        path
        for path in filtered_single_cluster_runs
        if _include_cluster_k(_selected_k_from_manifest(_load_manifest(path / "cluster_manifest__v1.json")))
    }
    collection_runs = {path for path in collection_runs if path.name != "clustering"}
    runs = dashboard_runs | collection_runs | filtered_single_cluster_runs

    def _run_mtime(path: Path) -> float:
        candidates = [path / "dashboard_manifest__v1.json", path / "cluster_manifest__v1.json"]
        candidates.extend(child / "cluster_manifest__v1.json" for child in _cluster_child_run_dirs(path))
        existing = [candidate for candidate in candidates if candidate.exists()]
        return max(candidate.stat().st_mtime for candidate in existing) if existing else 0.0

    sorted_runs = sorted(runs, key=_run_mtime, reverse=True)
    seen: set[Path] = set()
    ordered: list[Path] = []
    for run in sorted_runs:
        if run in seen:
            continue
        seen.add(run)
        ordered.append(run)
    return ordered


def discover_dashboard_run_options(root: Path) -> list[DashboardRunOption]:
    options: list[DashboardRunOption] = []
    for run_dir in discover_dashboard_runs(root):
        try:
            options.append(_describe_run(run_dir))
        except FileNotFoundError:
            continue
    return options
