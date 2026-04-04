# ADFIR Cluster Dashboard

Standalone Streamlit dashboard for exploring precomputed ADFIR clustering outputs.

This repository is self-contained: it includes the Streamlit app, bundled clustering data under `data/dashboard_exports/`, and methodology notes in `metodika.md`.

## What's included

- a standalone Streamlit dashboard application
- bundled clustering exports for multiple datasets in `data/dashboard_exports/`
- support for browsing datasets, cluster counts, cluster summaries, feature importance, and cluster window details
- boundary diagnostics around the estimated attack start
- methodology notes in `metodika.md`

## Quick start

### 1. Clone the repository

```powershell
git clone https://github.com/macomatom/ADFIR_clustering_dashboard.git
cd ADFIR_clustering_dashboard
```

### 2. Install `uv`

Project requirements:

- Python `>=3.11,<3.14`
- `uv`

Official installation guide:

- https://docs.astral.sh/uv/getting-started/installation/

Examples:

```powershell
winget install --id=astral-sh.uv -e
```

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 3. Install dependencies

```powershell
uv sync
```

### 4. Run the Streamlit dashboard

```powershell
uv run streamlit run app.py
```

The app starts a standalone Streamlit dashboard and loads the newest compatible bundled run from `data/dashboard_exports/` by default.

## Using the dashboard

The bundled data are available out of the box. After startup, the left sidebar lets you choose:

- the dataset
- the number of clusters
- how many cluster detail rows to show

The dashboard currently supports:

- cluster summaries for the selected run
- dual-view feature importance for each cluster
- a `Cluster windows` table with time context and original parquet row references
- boundary diagnostics showing which frames lie close to the estimated attack start
- a Shannon entropy view when entropy data are present in the loaded export

## Using your own data

The app can load both:

- dashboard bundles that contain `dashboard_manifest__v1.json`
- direct clustering outputs that contain `cluster_manifest__v1.json`

The simplest approach is to place your data under a structure similar to:

```text
data/dashboard_exports/<dataset>/sum/60s/clustering/agglomerative/k10
data/dashboard_exports/<dataset>/sum/60s/clustering/agglomerative/k11
...
```

The dashboard can also work with a collection root such as:

```text
data/dashboard_exports/<dataset>/sum/60s/clustering/agglomerative
```

and discover the available `k` values from its subdirectories.

## Methodology

Methodology notes for the current clustering and interpretation setup are included in:

- `metodika.md`

## Not implemented yet

- no in-app recomputation of clustering; the dashboard only explores precomputed outputs
- no automatic fetch or sync of newly generated exports from the main research repository
- no editing or relabeling workflow directly inside the dashboard

## Update to latest changes

To force your local checkout to match the newest `origin/main`:

```powershell
git fetch
git reset --hard origin/main
```

Use this only if you want to discard all local uncommitted changes.
