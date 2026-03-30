from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.clustering_service import (
    build_summary_metrics,
    build_entropy_timeline_df,
    build_timeline_df,
    get_all_cluster_top_features,
    get_assignments,
    get_available_k,
    get_cluster_summary,
    get_cluster_top_features,
)
from dashboard.data_loader import DashboardRunBundle, discover_dashboard_runs, load_dashboard_run
from dashboard.grid_helpers import aggrid_available, render_feature_aggrid
from dashboard.plots import build_entropy_plot, build_timeline_plot
from dashboard.ui_helpers import (
    build_cluster_option_labels,
    cluster_color_map,
    fill_cluster_summary_color_column,
    humanize_label,
    render_cluster_label_with_color,
    render_cluster_summary_dataframe,
    render_cluster_summary_context,
    render_feature_overview_table,
    sanitize_for_streamlit,
)


@st.cache_data(show_spinner=False)
def _load_bundle(run_dir: str) -> DashboardRunBundle:
    return load_dashboard_run(Path(run_dir))


@st.cache_data(show_spinner=False)
def _get_cached_all_features(run_dir: str, n_clusters: int) -> pd.DataFrame:
    bundle = _load_bundle(run_dir)
    return get_all_cluster_top_features(bundle, n_clusters)


@st.cache_data(show_spinner=False)
def _get_cached_invariant_timeline(run_dir: str, time_col: str) -> pd.DataFrame:
    bundle = _load_bundle(run_dir)
    invariant_source = bundle.assignments.copy()
    dedupe_cols = [col for col in [time_col, "row_idx", "window_id"] if col in invariant_source.columns]
    if dedupe_cols:
        invariant_source = invariant_source.drop_duplicates(subset=dedupe_cols, keep="first")
    return build_timeline_df(invariant_source, time_col=time_col)


def _resolve_default_run(root: Path) -> str:
    runs = discover_dashboard_runs(root)
    return str(runs[0]) if runs else ""


def _resolve_default_root() -> Path:
    candidates = [
        PROJECT_ROOT.parent / "analysis_outputs" / "clustering" / "with_entropy",
        PROJECT_ROOT / "data" / "dashboard_exports",
    ]
    for candidate in candidates:
        if candidate.exists() and discover_dashboard_runs(candidate):
            return candidate
    return candidates[0]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--run-dir", default="", help="Path to one dashboard export directory.")
    parser.add_argument("--runs-root", default="", help="Root directory containing one or more dashboard exports.")
    args, _ = parser.parse_known_args(sys.argv[1:])
    return args


def main() -> None:
    st.set_page_config(page_title="ADFIR Cluster Dashboard", layout="wide")
    st.title("ADFIR Cluster Dashboard")

    args = _parse_args()
    default_root = Path(args.runs_root) if args.runs_root else _resolve_default_root()
    default_run = args.run_dir or _resolve_default_run(default_root)

    st.sidebar.header("Data")
    run_dir = st.sidebar.text_input("Dashboard run directory", value=default_run)
    if not run_dir:
        st.info("Provide a dashboard run directory containing dashboard_manifest__v1.json.")
        return

    try:
        bundle = _load_bundle(run_dir)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Unable to load dashboard run: {type(exc).__name__}: {exc}")
        return

    available_k = get_available_k(bundle)
    if not available_k:
        st.warning("No available cluster counts in this dashboard run.")
        return

    if not aggrid_available():
        st.info("Feature tables are using fallback rendering. Install/sync `streamlit-aggrid` to enable colored sortable grids.")

    default_k = min([k for k in available_k if 10 <= k <= 30], default=available_k[0])
    n_clusters = st.sidebar.selectbox("Number of clusters", options=available_k, index=available_k.index(default_k))

    assignments = get_assignments(bundle, n_clusters)
    summary = get_cluster_summary(bundle, n_clusters)
    if assignments.empty:
        st.warning(f"No assignments found for k={n_clusters}.")
        return

    cluster_ids = sorted(pd.to_numeric(assignments["cluster_id"], errors="coerce").dropna().astype(int).unique().tolist())
    cluster_colors = cluster_color_map(cluster_ids)
    cluster_options = build_cluster_option_labels(cluster_ids)
    highlighted_labels = st.sidebar.multiselect("Highlighted clusters", options=list(cluster_options.keys()))
    highlighted_clusters = [cluster_options[label] for label in highlighted_labels]
    mute_non_selected = st.sidebar.checkbox("Mute non-selected clusters", value=True)

    active_cluster = highlighted_clusters[0] if highlighted_clusters else cluster_ids[0]

    artifact_label = humanize_label(bundle.manifest.get("artifact", "run"))
    aggregation_label = humanize_label(bundle.manifest.get("aggregation", ""))
    window_label = f"{bundle.manifest.get('window_s', '')}s"
    st.subheader(f"{artifact_label} | {aggregation_label} | {window_label} | k={n_clusters}")
    st.caption(f"Run directory: {bundle.run_dir}")

    metrics = build_summary_metrics(assignments, summary, active_cluster)
    clusters_tab, entropy_tab = st.tabs(["Clusters", "Shannon Entropy"])

    with clusters_tab:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Selected k", n_clusters)
        col2.metric("Total windows", metrics["total_windows"])
        col3.metric("Clusters", metrics["cluster_count"])
        col4.metric("Active cluster size", metrics["active_cluster_size"])

        timeline_df = build_timeline_df(assignments, time_col=str(bundle.manifest.get("time_col", "time_cluster")))
        time_col = str(bundle.manifest.get("time_col", "time_cluster"))
        invariant_timeline_df = _get_cached_invariant_timeline(run_dir, time_col)
        fig = build_timeline_plot(
            timeline_df,
            highlighted_clusters=highlighted_clusters,
            mute_non_selected=mute_non_selected,
            title=f"Timeline assignments for k={n_clusters}",
            window_s=int(bundle.manifest.get("window_s", 0) or 0),
            missing_source_df=invariant_timeline_df,
        )
        st.plotly_chart(fig, width="stretch")

        with st.expander("Run context", expanded=False):
            context_view = sanitize_for_streamlit(render_cluster_summary_context(summary))
            st.dataframe(context_view, width="stretch", hide_index=True)

        st.subheader("Cluster summary")
        summary_view = sanitize_for_streamlit(render_cluster_summary_dataframe(summary))
        summary_view = fill_cluster_summary_color_column(summary_view, cluster_colors)
        st.dataframe(
            summary_view,
            width="stretch",
            hide_index=True,
            column_config={
                "cluster_col": st.column_config.ImageColumn("cluster_col", help="Cluster color", width="small"),
            },
        )

        selected_feature_clusters = highlighted_clusters if highlighted_clusters else cluster_ids
        selected_feature_clusters = list(dict.fromkeys(int(cluster_id) for cluster_id in selected_feature_clusters))
        selected_features_df = _get_cached_all_features(run_dir, n_clusters)
        selected_features_df = selected_features_df[
            pd.to_numeric(selected_features_df["cluster_id"], errors="coerce").fillna(-1).astype(int).isin(selected_feature_clusters)
        ].copy()

        if len(selected_feature_clusters) == 1:
            st.subheader("Top 10 features for active cluster")
            active_features = get_cluster_top_features(bundle, n_clusters, selected_feature_clusters[0])
            if active_features.empty:
                st.info("No feature rows available for the selected cluster.")
            else:
                active_features_view = sanitize_for_streamlit(render_feature_overview_table(active_features, include_cluster_id=False))
                st.markdown(f"**Top 10 features | cluster {selected_feature_clusters[0]}**")
                render_feature_aggrid(
                    active_features_view,
                    color=cluster_colors.get(selected_feature_clusters[0], "rgb(220,220,220)"),
                    key=f"features_active_k{n_clusters}_c{selected_feature_clusters[0]}",
                )
        else:
            st.subheader("Top 10 features for selected clusters")
            compare_tab_labels = ["Compare"] + [f"Cluster {cluster_id}" for cluster_id in selected_feature_clusters]
            compare_tab, *cluster_tabs = st.tabs(compare_tab_labels)
            with compare_tab:
                if selected_features_df.empty:
                    st.info("No feature rows available for the selected clusters.")
                else:
                    st.dataframe(
                        sanitize_for_streamlit(render_feature_overview_table(selected_features_df, include_cluster_id=True)),
                        width="stretch",
                        hide_index=True,
                        column_config={
                            "delta_vs_global": st.column_config.NumberColumn("delta_vs_global", width="large"),
                            "cluster_value": st.column_config.NumberColumn("cluster_value", width="large"),
                            "global_value": st.column_config.NumberColumn("global_value", width="large"),
                        },
                    )
            for cluster_id, tab in zip(selected_feature_clusters, cluster_tabs, strict=False):
                with tab:
                    cluster_features = get_cluster_top_features(bundle, n_clusters, cluster_id)
                    if cluster_features.empty:
                        st.info(f"No feature rows available for cluster {cluster_id}.")
                    else:
                        cluster_features_view = sanitize_for_streamlit(render_feature_overview_table(cluster_features, include_cluster_id=False))
                        st.markdown(f"**Top 10 features | cluster {cluster_id}**")
                        render_feature_aggrid(
                            cluster_features_view,
                            color=cluster_colors.get(cluster_id, "rgb(220,220,220)"),
                            key=f"features_selected_k{n_clusters}_c{cluster_id}",
                        )

        with st.expander("Top 10 features for all clusters", expanded=False):
            all_features = _get_cached_all_features(run_dir, n_clusters)
            if all_features.empty:
                st.info("No feature rows available for this k.")
            else:
                for cluster_id in cluster_ids:
                    cluster_features = all_features[all_features["cluster_id"] == int(cluster_id)].copy()
                    cluster_features_view = sanitize_for_streamlit(render_feature_overview_table(cluster_features, include_cluster_id=False))
                    st.markdown(
                        render_cluster_label_with_color(
                            cluster_id,
                            cluster_colors.get(cluster_id, "rgb(220,220,220)"),
                        ),
                        unsafe_allow_html=True,
                    )
                    st.dataframe(cluster_features_view, width="stretch", hide_index=True)

    with entropy_tab:
        st.subheader("Shannon Entropy Over Time")
        entropy_col = str(bundle.manifest.get("entropy_default_col") or "global_shannon_entropy")
        entropy_df = build_entropy_timeline_df(bundle)
        if entropy_df.empty or entropy_col not in entropy_df.columns:
            st.info("Entropy data is not available in this dashboard export.")
        else:
            entropy_fig = build_entropy_plot(
                entropy_df,
                entropy_col=entropy_col,
                window_s=int(bundle.manifest.get("window_s", 0) or 0),
                title="Shannon Entropy Over Time",
            )
            st.plotly_chart(entropy_fig, width="stretch")


if __name__ == "__main__":
    main()
