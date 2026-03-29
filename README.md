# ADFIR Cluster Dashboard

Standalone Streamlit dashboard for browsing precomputed ADFIR agglomerative cluster exports.

The repository contains one bundled export: `Magnet_CTF_2022_Windows_Laptop | sum | 60s | k=10..30`

## Included

- Streamlit dashboard UI
- bundled dashboard export data for immediate use
- standalone `pyproject.toml`
- standalone `uv.lock`

The dashboard reads one export directory containing:

- `dashboard_manifest__v1.json`
- `window_assignments_long__v1.csv`
- `cluster_summary_long__v1.csv`
- `cluster_features_top10_long__v1.csv`

## Quick Start

Requirements:

- Python 3.11+
- `uv`

## Install uv

Official uv installation docs:

- https://docs.astral.sh/uv/getting-started/installation/

Recommended install methods:

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Windows with WinGet:

```powershell
winget install --id=astral-sh.uv -e
```

macOS / Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After installation, open a new terminal and verify:

```powershell
uv --version
```

Run:

```powershell
uv sync
uv run streamlit run app.py
```

After launch, the bundled export is selected automatically.

## Use Your Own Export

One export directory:

```powershell
uv run streamlit run app.py -- --run-dir path\to\dashboard\agglomerative
```

Root with multiple exports:

```powershell
uv run streamlit run app.py -- --runs-root path\to\dashboard_exports
```

You can also paste the export path directly into the sidebar.

## Bundled Data

Bundled export path:

```text
data/dashboard_exports/Magnet_CTF_2022_Windows_Laptop/sum/60s/dashboard/agglomerative
```

## Intended Scope

- visualization only
- no clustering is executed inside this repository
- export generation stays in the main analysis repository

## Minimal Export Contract

The dashboard expects the same schema as the bundled files. At minimum:

- assignments CSV with `window_id`, `time_cluster` or `row_idx`, `n_clusters`, `cluster_id`
- summary CSV with `n_clusters`, `cluster_id`, `cluster_size`, `cluster_frac`
- features CSV with `n_clusters`, `cluster_id`, `rank`, `feature_name`, `delta_vs_global`, `cluster_value`, `global_value`
- manifest JSON pointing to those files

## Troubleshooting

If dependencies are not present:

```powershell
uv sync
```

If you want to rebuild the environment from scratch:

```powershell
Remove-Item -Recurse -Force .venv
uv sync
```
