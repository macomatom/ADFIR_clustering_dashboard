# ADFIR Cluster Dashboard

Standalone Streamlit dashboard for browsing precomputed ADFIR cluster outputs.

The repository already contains bundled data for:

- `Magnet_CTF_2022_Windows_Laptop`
- aggregation `sum`
- window size `60s`
- agglomerative clustering
- `k = 10..30`

The application can read both:

- standalone dashboard exports with `dashboard_manifest__v1.json`
- direct clustering outputs with `cluster_manifest__v1.json`

## What Is Included

- Streamlit dashboard UI
- standalone `pyproject.toml`
- standalone `uv.lock`
- bundled data under `data/dashboard_exports/...`

## Installation

### 1. Prerequisites

Required:

- Python `3.11+`
- `uv`

Project metadata currently targets:

- Python `>=3.11,<3.14`

### 2. Clone the Repository

```powershell
git clone https://github.com/macomatom/ADFIR_clustering_dashboard.git
cd ADFIR_clustering_dashboard
```

### 3. Install `uv`

Official docs:

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

Verify installation:

```powershell
uv --version
```

### 4. Install Project Dependencies

```powershell
uv sync
```

This creates the local virtual environment and installs all required packages.

## Running the Dashboard

### 5. Start Streamlit

```powershell
uv run streamlit run app.py
```

After startup, the dashboard will automatically select the newest bundled run from `data/dashboard_exports`.

## Troubleshooting

If dependencies are missing:

```powershell
uv sync
```

If you want to rebuild the environment:

```powershell
Remove-Item -Recurse -Force .venv
uv sync
```
