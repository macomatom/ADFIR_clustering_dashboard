from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.data_loader import SCORE_COMPARISON_FILENAME, SCORE_COMPARISON_SHEET, discover_dashboard_run_options


def _cluster_child_run_dirs(run_dir: Path) -> list[Path]:
    return sorted(path for path in run_dir.iterdir() if path.is_dir() and (path / "cluster_manifest__v1.json").exists())


def _extract_run_scores(child_run_dir: Path) -> dict[str, float | int]:
    manifest = json.loads((child_run_dir / "cluster_manifest__v1.json").read_text(encoding="utf-8"))
    selected_k = int(pd.to_numeric(pd.Series([manifest.get("selected_k")]), errors="coerce").iloc[0])
    summary_path = child_run_dir / "cluster_summary__v1.csv"
    summary_df = pd.read_csv(summary_path)
    if "row_type" in summary_df.columns:
        run_rows = summary_df[summary_df["row_type"].astype(str) == "run"].copy()
        row = run_rows.iloc[0] if not run_rows.empty else summary_df.iloc[0]
    else:
        row = summary_df.iloc[0]
    return {
        "selected_k": selected_k,
        "silhouette_score": float(pd.to_numeric(pd.Series([row.get("silhouette_score")]), errors="coerce").iloc[0]),
        "davies_bouldin_score": float(pd.to_numeric(pd.Series([row.get("davies_bouldin_score")]), errors="coerce").iloc[0]),
        "calinski_harabasz_score": float(pd.to_numeric(pd.Series([row.get("calinski_harabasz_score")]), errors="coerce").iloc[0]),
    }


def build_score_comparison_df(run_dir: Path) -> pd.DataFrame:
    rows = [_extract_run_scores(child_run_dir) for child_run_dir in _cluster_child_run_dirs(run_dir)]
    if not rows:
        return pd.DataFrame(columns=["selected_k", "silhouette_score", "davies_bouldin_score", "calinski_harabasz_score"])
    out = pd.DataFrame(rows).drop_duplicates(subset=["selected_k"]).sort_values("selected_k", ascending=True).reset_index(drop=True)
    out["silhouette_rank"] = out["silhouette_score"].rank(method="dense", ascending=False).astype("Int64")
    out["davies_bouldin_rank"] = out["davies_bouldin_score"].rank(method="dense", ascending=True).astype("Int64")
    out["calinski_harabasz_rank"] = out["calinski_harabasz_score"].rank(method="dense", ascending=False).astype("Int64")
    out["is_selected_k"] = False
    ordered_cols = [
        "selected_k",
        "silhouette_score",
        "davies_bouldin_score",
        "calinski_harabasz_score",
        "silhouette_rank",
        "davies_bouldin_rank",
        "calinski_harabasz_rank",
        "is_selected_k",
    ]
    return out[ordered_cols]


def write_score_comparison_excel(run_dir: Path) -> Path:
    out_df = build_score_comparison_df(run_dir)
    out_path = run_dir / SCORE_COMPARISON_FILENAME
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        out_df.to_excel(writer, sheet_name=SCORE_COMPARISON_SHEET, index=False)
    return out_path


def _default_root() -> Path:
    return PROJECT_ROOT / "data" / "dashboard_exports"


def _iter_target_run_dirs(root: Path, explicit_run_dir: Path | None) -> list[Path]:
    if explicit_run_dir is not None:
        return [explicit_run_dir]
    options = discover_dashboard_run_options(root)
    return [option.run_dir for option in options if option.source_mode == "cluster_collection"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate precomputed clustering score comparison Excel files for dashboard run directories.")
    parser.add_argument("--root", type=Path, default=_default_root(), help="Root directory containing dashboard exports.")
    parser.add_argument("--run-dir", type=Path, default=None, help="Optional single run directory to process instead of walking the root.")
    args = parser.parse_args()

    run_dirs = _iter_target_run_dirs(args.root, args.run_dir)
    if not run_dirs:
        print("No cluster collection run directories found.")
        return 0

    generated = 0
    for run_dir in run_dirs:
        out_path = write_score_comparison_excel(run_dir)
        generated += 1
        print(f"[ok] {out_path}")
    print(f"Generated {generated} score comparison Excel file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
