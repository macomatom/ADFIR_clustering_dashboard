from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.clustering_service import (
    build_summary_metrics,
    build_entropy_timeline_df,
    build_timeline_df,
    filter_timeline_to_viewport,
    get_default_timeline_viewport,
    get_all_cluster_top_features,
    get_assignments,
    get_available_k,
    get_cluster_detail_rows,
    get_cluster_summary,
    get_cluster_top_features,
)
from dashboard.data_loader import DashboardRunBundle, DashboardRunOption, discover_dashboard_run_options, discover_dashboard_runs, load_dashboard_run
from dashboard.dendrogram_runtime import ensure_dendrogram_artifacts
from dashboard.grid_helpers import aggrid_available, render_feature_aggrid
from dashboard.plots import build_entropy_plot, build_timeline_plot
from dashboard.ui_helpers import (
    build_cluster_option_labels,
    cluster_color_map,
    fill_cluster_summary_color_column,
    humanize_label,
    render_cluster_detail_table_html,
    render_cluster_label_with_color,
    render_cluster_detail_table,
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
def _get_cached_invariant_timeline(run_dir: str, n_clusters: int, time_col: str) -> pd.DataFrame:
    bundle = _load_bundle(run_dir)
    invariant_source = get_assignments(bundle, n_clusters).copy()
    dedupe_cols = [col for col in [time_col, "row_idx", "window_id"] if col in invariant_source.columns]
    if dedupe_cols:
        invariant_source = invariant_source.drop_duplicates(subset=dedupe_cols, keep="first")
    return build_timeline_df(invariant_source, time_col=time_col)


@st.cache_data(show_spinner=False)
def _get_cached_present_timeline(run_dir: str, n_clusters: int, time_col: str) -> pd.DataFrame:
    bundle = _load_bundle(run_dir)
    assignments = get_assignments(bundle, n_clusters).copy()
    return build_timeline_df(assignments, time_col=time_col)


@st.cache_data(show_spinner=False)
def _get_cached_timeline_defaults(run_dir: str, n_clusters: int, time_col: str, window_s: int) -> dict[str, Any]:
    bundle = _load_bundle(run_dir)
    assignments = get_assignments(bundle, n_clusters).copy()
    return get_default_timeline_viewport(assignments, time_col=time_col, window_s=window_s)


@st.cache_data(show_spinner=False)
def _resolve_selected_run_dir(run_dir: str, n_clusters: int) -> str:
    bundle = _load_bundle(run_dir)
    child_map = bundle.cluster_run_dirs_by_k or {}
    selected_run_dir = child_map.get(int(n_clusters))
    return str(selected_run_dir or bundle.run_dir)


def _resolve_default_run(root: Path) -> str:
    options = _preferred_run_options(_discover_run_options(str(root)))
    return str(options[0].run_dir) if options else ""


@st.cache_data(show_spinner=False)
def _discover_run_options(root: str) -> list[DashboardRunOption]:
    return discover_dashboard_run_options(Path(root))


def _preferred_run_options(options: list[DashboardRunOption]) -> list[DashboardRunOption]:
    preferred = [
        option
        for option in options
        if option.window_s == 60 and option.method == "agglomerative"
    ]
    return preferred or options


def _build_dataset_option_map(options: list[DashboardRunOption]) -> dict[str, list[DashboardRunOption]]:
    labels: dict[str, list[DashboardRunOption]] = {}
    for option in options:
        labels.setdefault(option.artifact, []).append(option)
    return labels


def _resolve_default_root() -> Path:
    candidate = PROJECT_ROOT / "data" / "dashboard_exports"
    if candidate.exists() and discover_dashboard_runs(candidate):
        return candidate
    return candidate


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--run-dir", default="", help="Path to one dashboard export directory.")
    parser.add_argument("--runs-root", default="", help="Root directory containing one or more dashboard exports.")
    args, _ = parser.parse_known_args(sys.argv[1:])
    return args


def _default_active_cluster(summary: pd.DataFrame, cluster_ids: list[int]) -> int:
    if not cluster_ids:
        raise ValueError("cluster_ids must not be empty")
    if summary.empty or "cluster_id" not in summary.columns:
        return int(cluster_ids[0])
    ranked = summary.copy()
    ranked["cluster_id"] = pd.to_numeric(ranked["cluster_id"], errors="coerce")
    ranked = ranked[ranked["cluster_id"].notna()].copy()
    if ranked.empty:
        return int(cluster_ids[0])
    ranked["closest_abs_distance_to_anchor"] = pd.to_numeric(ranked.get("closest_abs_distance_to_anchor"), errors="coerce")
    ranked["attack_rate"] = pd.to_numeric(ranked.get("attack_rate"), errors="coerce")
    ranked["cluster_size"] = pd.to_numeric(ranked.get("cluster_size"), errors="coerce")
    ranked = ranked.sort_values(
        ["closest_abs_distance_to_anchor", "attack_rate", "cluster_size", "cluster_id"],
        ascending=[True, False, False, True],
        na_position="last",
    )
    return int(ranked.iloc[0]["cluster_id"])


def _serialize_axis_value(value: Any, *, time_mode: str | None) -> str | float | int | None:
    if value is None or pd.isna(value):
        return None
    if time_mode == "datetime":
        return pd.Timestamp(value).isoformat()
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return None
    return float(numeric)


def _deserialize_axis_value(value: Any, *, time_mode: str | None) -> Any:
    if value in (None, ""):
        return None
    if time_mode == "datetime":
        parsed = pd.to_datetime(value, errors="coerce")
        return None if pd.isna(parsed) else parsed
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(parsed) else float(parsed)


def _timeline_state_key(run_dir: str, n_clusters: int) -> str:
    return f"timeline_viewport::{run_dir}::{n_clusters}"


def _ensure_timeline_state(
    run_dir: str,
    n_clusters: int,
    *,
    defaults: dict[str, Any],
) -> dict[str, Any]:
    state_key = _timeline_state_key(run_dir, n_clusters)
    if state_key not in st.session_state:
        st.session_state[state_key] = {
            "x_min": _serialize_axis_value(defaults.get("x_min"), time_mode=defaults.get("time_mode")),
            "x_max": _serialize_axis_value(defaults.get("x_max"), time_mode=defaults.get("time_mode")),
            "container_width_px": 1100,
            "initialized": True,
        }
    return st.session_state[state_key]


def _viewport_changed(old_value: Any, new_value: Any, *, time_mode: str | None) -> bool:
    old_parsed = _deserialize_axis_value(old_value, time_mode=time_mode)
    new_parsed = _deserialize_axis_value(new_value, time_mode=time_mode)
    if old_parsed is None and new_parsed is None:
        return False
    if old_parsed is None or new_parsed is None:
        return True
    if time_mode == "datetime":
        return pd.Timestamp(old_parsed) != pd.Timestamp(new_parsed)
    return abs(float(old_parsed) - float(new_parsed)) > 1e-9


def _compute_target_bars(container_width_px: Any) -> int:
    width = pd.to_numeric(pd.Series([container_width_px]), errors="coerce").iloc[0]
    if pd.isna(width):
        return 600
    # Use fewer bars than raw pixels so zooming progressively reveals detail.
    return int(min(1400, max(300, int(float(width) * 0.55))))


def _format_visible_span(x_min: Any, x_max: Any, *, time_mode: str | None) -> str:
    if x_min is None or x_max is None:
        return "full range"
    if time_mode == "datetime":
        delta = pd.Timestamp(x_max) - pd.Timestamp(x_min)
        total_seconds = int(delta.total_seconds())
        days, rem = divmod(max(total_seconds, 0), 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        if days:
            return f"{days}d {hours:02d}:{minutes:02d}"
        return f"{hours:02d}:{minutes:02d}"
    return f"{float(x_max) - float(x_min):.2f}"


def main() -> None:
    st.set_page_config(page_title="ADFIR Cluster Dashboard", layout="wide")
    st.title("ADFIR Cluster Dashboard")

    args = _parse_args()
    default_root = Path(args.runs_root) if args.runs_root else _resolve_default_root()
    default_run = args.run_dir or _resolve_default_run(default_root)

    st.sidebar.header("Data")
    run_options = _preferred_run_options(_discover_run_options(str(default_root)))
    if not run_options and default_run:
        run_options = [DashboardRunOption(Path(default_run), "run", "", None, "", "manual", "run")]
    option_map = _build_dataset_option_map(run_options)
    if option_map:
        selected_dataset_label = st.sidebar.selectbox("Dataset", options=list(option_map.keys()), index=0)
    else:
        selected_dataset_label = ""
    dataset_options = option_map.get(selected_dataset_label, [])
    aggregation_map = {option.aggregation: option for option in dataset_options}
    aggregation_options = [agg for agg in ["sum", "max"] if agg in aggregation_map]
    aggregation_options.extend(sorted(agg for agg in aggregation_map if agg not in {"sum", "max"}))
    if aggregation_options:
        default_aggregation = "sum" if "sum" in aggregation_options else aggregation_options[0]
        selected_aggregation = st.sidebar.selectbox(
            "Aggregation",
            options=aggregation_options,
            index=aggregation_options.index(default_aggregation),
        )
    else:
        selected_aggregation = ""
    selected_option = aggregation_map.get(selected_aggregation) if aggregation_map else None
    run_dir = str(selected_option.run_dir) if selected_option else default_run
    if run_dir:
        st.sidebar.caption(f"Run: `{run_dir}`")
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

    default_k = min([k for k in available_k if 10 <= k <= 50], default=available_k[0])
    n_clusters = st.sidebar.selectbox("Number of clusters", options=available_k, index=available_k.index(default_k))
    cluster_row_limit = st.sidebar.selectbox("Rows to show", options=[10, 25, 50, 100, 250], index=0)

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

    active_cluster = highlighted_clusters[0] if highlighted_clusters else _default_active_cluster(summary, cluster_ids)

    artifact_label = humanize_label(bundle.manifest.get("artifact", "run"))
    aggregation_label = humanize_label(bundle.manifest.get("aggregation", ""))
    window_label = f"{bundle.manifest.get('window_s', '')}s"
    st.subheader(f"{artifact_label} | {aggregation_label} | {window_label} | k={n_clusters}")
    st.caption(f"Run directory: {bundle.run_dir}")
    st.caption("Feature tables show raw interpretation (`cluster_value`, `global_value`, `delta_vs_global`) and standardized ranking (`score_std`).")

    metrics = build_summary_metrics(assignments, summary, active_cluster)
    clusters_tab, entropy_tab = st.tabs(["Clusters", "Shannon Entropy"])

    with clusters_tab:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Selected k", n_clusters)
        col2.metric("Total windows", metrics["total_windows"])
        col3.metric("Clusters", metrics["cluster_count"])
        col4.metric("Active cluster size", metrics["active_cluster_size"])

        time_col = str(bundle.manifest.get("time_col", "time_cluster"))
        window_s = int(bundle.manifest.get("window_s", 0) or 0)
        timeline_df = _get_cached_present_timeline(run_dir, n_clusters, time_col)
        invariant_timeline_df = _get_cached_invariant_timeline(run_dir, n_clusters, time_col)
        timeline_defaults = _get_cached_timeline_defaults(run_dir, n_clusters, time_col, window_s)
        timeline_state = _ensure_timeline_state(run_dir, n_clusters, defaults=timeline_defaults)
        time_mode = timeline_defaults.get("time_mode")
        current_x_min = _deserialize_axis_value(timeline_state.get("x_min"), time_mode=time_mode)
        current_x_max = _deserialize_axis_value(timeline_state.get("x_max"), time_mode=time_mode)
        overview_fig = build_timeline_plot(
            timeline_df,
            highlighted_clusters=highlighted_clusters,
            mute_non_selected=mute_non_selected,
            title=f"Timeline overview for k={n_clusters}",
            cluster_colors=cluster_colors,
            window_s=window_s,
            missing_source_df=invariant_timeline_df,
            max_present_bars=900,
            max_missing_bars=90,
        )
        st.subheader("Timeline overview")
        st.plotly_chart(overview_fig, width="stretch")

        control_col1, control_col2, control_col3 = st.columns([1, 1, 3])
        if control_col1.button("Reset viewport", key=f"reset_viewport_{n_clusters}"):
            timeline_state["x_min"] = _serialize_axis_value(timeline_defaults.get("x_min"), time_mode=time_mode)
            timeline_state["x_max"] = _serialize_axis_value(timeline_defaults.get("x_max"), time_mode=time_mode)
            st.rerun()
        if control_col2.button(
            "Jump to incident anchor",
            key=f"jump_anchor_{n_clusters}",
            disabled=timeline_defaults.get("anchor_time") is None,
        ):
            timeline_state["x_min"] = _serialize_axis_value(timeline_defaults.get("x_min"), time_mode=time_mode)
            timeline_state["x_max"] = _serialize_axis_value(timeline_defaults.get("x_max"), time_mode=time_mode)
            st.rerun()
        control_col3.caption(
            f"Visible span: {_format_visible_span(current_x_min, current_x_max, time_mode=time_mode)}"
        )

        detail_present_df = filter_timeline_to_viewport(
            timeline_df,
            x_min=current_x_min,
            x_max=current_x_max,
            window_s=window_s,
            padding_windows=1,
        )
        detail_missing_df = filter_timeline_to_viewport(
            invariant_timeline_df,
            x_min=current_x_min,
            x_max=current_x_max,
            window_s=window_s,
            padding_windows=1,
        )
        target_bars = _compute_target_bars(timeline_state.get("container_width_px"))
        detail_fig = build_timeline_plot(
            detail_present_df,
            highlighted_clusters=highlighted_clusters,
            mute_non_selected=mute_non_selected,
            title=f"Timeline detail for k={n_clusters}",
            cluster_colors=cluster_colors,
            window_s=window_s,
            missing_source_df=detail_missing_df,
            max_present_bars=target_bars,
            max_missing_bars=max(40, target_bars // 10),
            xaxis_range=[current_x_min, current_x_max] if current_x_min is not None and current_x_max is not None else None,
            height=340,
        )
        st.subheader("Timeline detail")
        st.plotly_chart(detail_fig, width="stretch")

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
                "closest_abs_distance_to_anchor": st.column_config.NumberColumn("closest_abs_distance_to_anchor", width="large"),
                "frames_within_anchor_pm2": st.column_config.NumberColumn("frames_within_anchor_pm2", width="medium"),
                "frames_within_anchor_pm2_frac": st.column_config.NumberColumn("frames_within_anchor_pm2_frac", width="large"),
                "pre_anchor_within_pm2_count": st.column_config.NumberColumn("pre_anchor_within_pm2_count", width="large"),
                "post_anchor_within_pm2_count": st.column_config.NumberColumn("post_anchor_within_pm2_count", width="large"),
                "incident_within_anchor_pm2_count": st.column_config.NumberColumn("incident_within_anchor_pm2_count", width="large"),
            },
        )

        st.subheader("Cluster windows")
        window_tab_labels = [f"Cluster {cluster_id}" for cluster_id in cluster_ids]
        window_tabs = st.tabs(window_tab_labels)
        for cluster_id, tab in zip(cluster_ids, window_tabs, strict=False):
            with tab:
                detail_rows, total_detail_rows = get_cluster_detail_rows(bundle, n_clusters, cluster_id, limit=int(cluster_row_limit))
                if detail_rows.empty:
                    st.info(f"No row details available for cluster {cluster_id}.")
                    continue
                cluster_summary = summary[pd.to_numeric(summary["cluster_id"], errors="coerce").fillna(-1).astype(int) == int(cluster_id)]
                if not cluster_summary.empty:
                    summary_row = cluster_summary.iloc[0]
                    anchor_time = summary_row.get("incident_anchor_time", pd.NA)
                    closest_distance = summary_row.get("closest_abs_distance_to_anchor", pd.NA)
                    boundary_count = summary_row.get("frames_within_anchor_pm2", pd.NA)
                    pre_count = summary_row.get("pre_anchor_within_pm2_count", pd.NA)
                    post_count = summary_row.get("post_anchor_within_pm2_count", pd.NA)
                    incident_count = summary_row.get("incident_within_anchor_pm2_count", pd.NA)
                    if pd.isna(anchor_time):
                        st.caption("Boundary diagnostics: unavailable for this dataset because no incident anchor is present in the bundled labels.")
                    else:
                        caption = (
                            f"Boundary diagnostics (+/-2 windows): within={boundary_count}, pre={pre_count}, "
                            f"post={post_count}, incident={incident_count}, closest={closest_distance}, anchor={anchor_time}"
                        )
                        if pd.notna(boundary_count) and float(boundary_count) == 0.0 and pd.notna(closest_distance):
                            caption += " | No rows from this cluster fall within +/-2 windows of the incident anchor."
                        st.caption(caption)
                st.caption(f"Showing {len(detail_rows)} of {total_detail_rows} rows for cluster {cluster_id}.")
                detail_view = sanitize_for_streamlit(render_cluster_detail_table(detail_rows))
                st.markdown(
                    render_cluster_detail_table_html(
                        detail_view,
                        color=cluster_colors.get(cluster_id, "rgb(220,220,220)"),
                        title=f"Cluster windows | cluster {cluster_id}",
                    ),
                    unsafe_allow_html=True,
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
                            "direction": st.column_config.TextColumn("direction", width="medium"),
                            "score_std": st.column_config.NumberColumn("score_std", width="large"),
                            "delta_vs_global": st.column_config.NumberColumn("delta_vs_global", width="large"),
                            "cluster_value": st.column_config.NumberColumn("cluster_value", width="large"),
                            "global_value": st.column_config.NumberColumn("global_value", width="large"),
                            "global_std": st.column_config.NumberColumn("global_std", width="large"),
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

        st.subheader("Dendrogram")
        selected_run_dir = _resolve_selected_run_dir(run_dir, n_clusters)
        selected_run_bundle = _load_bundle(selected_run_dir)
        if selected_run_bundle.linkage_matrix_path is None:
            st.info("This export does not include dendrogram linkage data yet. Regenerate and sync the run with `cluster_linkage_matrix__v1.npy`.")
        else:
            title = (
                f"{selected_run_bundle.manifest.get('scope', '')} "
                f"{selected_run_bundle.manifest.get('artifact', '')} "
                f"{selected_run_bundle.manifest.get('aggregation', '')} "
                f"{selected_run_bundle.manifest.get('method', '')}"
            ).strip()
            with st.spinner("Preparing dendrogram..."):
                dendrogram_state = ensure_dendrogram_artifacts(
                    run_dir=selected_run_bundle.run_dir,
                    linkage_matrix_path=selected_run_bundle.linkage_matrix_path,
                    title=title,
                    method=str(selected_run_bundle.manifest.get("method", "")),
                    linkage=str(selected_run_bundle.manifest.get("linkage", "")) or None,
                    selected_k=int(selected_run_bundle.manifest.get("selected_k")) if selected_run_bundle.manifest.get("selected_k") is not None else None,
                    cut_mode=str(selected_run_bundle.manifest.get("cut_mode", "")) or None,
                    cut_value=selected_run_bundle.manifest.get("cut_value"),
                )
            if not dendrogram_state["available"]:
                st.info(str(dendrogram_state.get("message") or "Dendrogram is not available for this run."))
            else:
                st.image(str(dendrogram_state["png_path"]), caption=f"Dendrogram for k={n_clusters}", width="stretch")
                if dendrogram_state.get("cut_png_path") is not None:
                    st.image(
                        str(dendrogram_state["cut_png_path"]),
                        caption=f"Dendrogram with cut overlay for k={n_clusters}",
                        width="stretch",
                    )

    with entropy_tab:
        st.subheader("Shannon Entropy Over Time")
        entropy_col = str(bundle.manifest.get("entropy_default_col") or "global_shannon_entropy")
        entropy_df = build_entropy_timeline_df(bundle, n_clusters)
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
