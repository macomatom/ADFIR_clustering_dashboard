from __future__ import annotations

import json
from dataclasses import dataclass
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


@dataclass(slots=True)
class DashboardRunBundle:
    run_dir: Path
    manifest: dict[str, Any]
    assignments: pd.DataFrame
    summaries: pd.DataFrame
    features: pd.DataFrame


def _load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def load_dashboard_run(run_dir: Path) -> DashboardRunBundle:
    run_dir = Path(run_dir)
    manifest_path = run_dir / "dashboard_manifest__v1.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing dashboard manifest: {manifest_path}")
    manifest = _load_manifest(manifest_path)

    assignments = _read_table(run_dir / str(manifest["assignments_file"]))
    summaries = _read_table(run_dir / str(manifest["summary_file"]))
    features = _read_table(run_dir / str(manifest["features_file"]))

    _validate_required_columns(assignments, REQUIRED_ASSIGNMENT_COLS, "assignments")
    _validate_required_columns(summaries, REQUIRED_SUMMARY_COLS, "summaries")
    _validate_required_columns(features, REQUIRED_FEATURE_COLS, "features")

    return DashboardRunBundle(
        run_dir=run_dir,
        manifest=manifest,
        assignments=assignments,
        summaries=summaries,
        features=features,
    )


def discover_dashboard_runs(root: Path) -> list[Path]:
    return sorted(path.parent for path in Path(root).rglob("dashboard_manifest__v1.json"))
