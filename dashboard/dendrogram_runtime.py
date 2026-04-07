from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from dataclasses import dataclass

from scipy.cluster.hierarchy import dendrogram, fcluster, leaves_list, to_tree

matplotlib.use("Agg")
import matplotlib.pyplot as plt


DENDROGRAM_IMAGE_FILE = "cluster_dendrogram__v1.png"
DENDROGRAM_CUT_IMAGE_FILE = "cluster_dendrogram_at_cut__v1.png"
DENDROGRAM_META_FILE = "cluster_dendrogram_meta__v1.json"
RENDER_STYLE_VERSION = 3
LEVELS_BELOW_CUT = 2
K_MODE_CUT_POSITION_IN_GAP = 0.30


@dataclass(slots=True)
class _DisplayNode:
    left: "_DisplayNode | None"
    right: "_DisplayNode | None"
    dist: float
    count: int
    represented_count: int
    source_id: int
    span_start: int
    span_end: int

    @property
    def is_leaf(self) -> bool:
        return self.left is None and self.right is None


def _resolve_cut_height(
    *,
    linkage_matrix: np.ndarray,
    selected_k: int | None,
    cut_mode: str | None,
    cut_value: float | int | None,
) -> tuple[float | None, str | None]:
    if linkage_matrix.size == 0:
        return None, None
    if cut_mode == "distance" and cut_value is not None:
        return float(cut_value), f"distance={float(cut_value):.4g}"
    if cut_mode != "k" or selected_k is None:
        return None, None
    n_samples = int(linkage_matrix.shape[0]) + 1
    k = int(selected_k)
    if k <= 1:
        return float(linkage_matrix[-1, 2]), f"k={k}"
    if k >= n_samples:
        return None, None
    lower_idx = n_samples - k - 1
    upper_idx = n_samples - k
    lower_dist = float(linkage_matrix[lower_idx, 2]) if lower_idx >= 0 else 0.0
    upper_dist = float(linkage_matrix[upper_idx, 2])
    if upper_dist < lower_dist:
        lower_dist, upper_dist = upper_dist, lower_dist
    return lower_dist + (upper_dist - lower_dist) * float(K_MODE_CUT_POSITION_IN_GAP), f"k={k}"


def _leaf_node(source_id: int, count: int, *, span_start: int, span_end: int) -> _DisplayNode:
    return _DisplayNode(
        left=None,
        right=None,
        dist=0.0,
        count=1,
        represented_count=int(count),
        source_id=int(source_id),
        span_start=int(span_start),
        span_end=int(span_end),
    )


def _build_node_spans(node: object, *, leaf_position: np.ndarray, spans: dict[int, tuple[int, int]]) -> tuple[int, int]:
    node_id = int(getattr(node, "id"))
    left = getattr(node, "left", None)
    right = getattr(node, "right", None)
    if left is None or right is None:
        leaf_pos = int(leaf_position[node_id])
        spans[node_id] = (leaf_pos, leaf_pos)
        return spans[node_id]
    left_span = _build_node_spans(left, leaf_position=leaf_position, spans=spans)
    right_span = _build_node_spans(right, leaf_position=leaf_position, spans=spans)
    spans[node_id] = (int(left_span[0]), int(right_span[1]))
    return spans[node_id]


def _expand_below_cut(node: object, *, levels_remaining: int, node_spans: dict[int, tuple[int, int]]) -> _DisplayNode:
    left = getattr(node, "left", None)
    right = getattr(node, "right", None)
    span_start, span_end = node_spans[int(getattr(node, "id"))]
    if left is None or right is None or levels_remaining <= 0:
        return _leaf_node(int(getattr(node, "id")), int(getattr(node, "count")), span_start=span_start, span_end=span_end)
    return _DisplayNode(
        left=_expand_below_cut(left, levels_remaining=levels_remaining - 1, node_spans=node_spans),
        right=_expand_below_cut(right, levels_remaining=levels_remaining - 1, node_spans=node_spans),
        dist=float(getattr(node, "dist")),
        count=0,
        represented_count=int(getattr(node, "count")),
        source_id=int(getattr(node, "id")),
        span_start=span_start,
        span_end=span_end,
    )


def _contract_tree_around_cut(
    node: object,
    *,
    parent_dist: float,
    cut_height: float,
    levels_below_cut: int,
    node_spans: dict[int, tuple[int, int]],
) -> _DisplayNode:
    left = getattr(node, "left", None)
    right = getattr(node, "right", None)
    span_start, span_end = node_spans[int(getattr(node, "id"))]
    if left is None or right is None:
        return _leaf_node(int(getattr(node, "id")), int(getattr(node, "count")), span_start=span_start, span_end=span_end)
    node_dist = float(getattr(node, "dist"))
    if node_dist <= cut_height < parent_dist:
        return _expand_below_cut(node, levels_remaining=levels_below_cut, node_spans=node_spans)
    return _DisplayNode(
        left=_contract_tree_around_cut(
            left,
            parent_dist=node_dist,
            cut_height=cut_height,
            levels_below_cut=levels_below_cut,
            node_spans=node_spans,
        ),
        right=_contract_tree_around_cut(
            right,
            parent_dist=node_dist,
            cut_height=cut_height,
            levels_below_cut=levels_below_cut,
            node_spans=node_spans,
        ),
        dist=node_dist,
        count=0,
        represented_count=int(getattr(node, "count")),
        source_id=int(getattr(node, "id")),
        span_start=span_start,
        span_end=span_end,
    )


def _assign_leaf_indices(node: _DisplayNode, *, next_leaf_idx: int = 0) -> int:
    if node.is_leaf:
        node.source_id = int(next_leaf_idx)
        return next_leaf_idx + 1
    assert node.left is not None and node.right is not None
    next_idx = _assign_leaf_indices(node.left, next_leaf_idx=next_leaf_idx)
    return _assign_leaf_indices(node.right, next_leaf_idx=next_idx)


def _display_tree_to_linkage(node: _DisplayNode) -> tuple[np.ndarray | None, int, dict[int, tuple[int, int]]]:
    n_leaves = _assign_leaf_indices(node)
    if n_leaves <= 1:
        return None, n_leaves, {int(node.source_id): (int(node.span_start), int(node.span_end))}
    rows: list[list[float]] = []
    leaf_spans: dict[int, tuple[int, int]] = {}

    def _build(current: _DisplayNode) -> tuple[int, int]:
        if current.is_leaf:
            leaf_spans[int(current.source_id)] = (int(current.span_start), int(current.span_end))
            return int(current.source_id), int(current.count)
        assert current.left is not None and current.right is not None
        left_id, left_count = _build(current.left)
        right_id, right_count = _build(current.right)
        node_id = n_leaves + len(rows)
        total_count = int(left_count + right_count)
        rows.append([float(left_id), float(right_id), float(current.dist), float(total_count)])
        return node_id, total_count

    _build(node)
    return np.asarray(rows, dtype="float64"), n_leaves, leaf_spans


def _build_reduced_linkage_matrix(
    *,
    linkage_matrix: np.ndarray,
    resolved_cut_height: float | None,
    levels_below_cut: int,
) -> tuple[np.ndarray, dict[str, object]]:
    if linkage_matrix.size == 0:
        return linkage_matrix, {
            "truncation_strategy": "empty",
            "levels_below_cut": int(levels_below_cut),
            "display_leaf_count": 0,
            "display_internal_count": 0,
        }
    root = to_tree(linkage_matrix, rd=False)
    full_leaf_order = leaves_list(linkage_matrix).astype(int)
    leaf_position = np.empty(len(full_leaf_order), dtype=int)
    leaf_position[full_leaf_order] = np.arange(len(full_leaf_order), dtype=int)
    node_spans: dict[int, tuple[int, int]] = {}
    _build_node_spans(root, leaf_position=leaf_position, spans=node_spans)
    if resolved_cut_height is None:
        display_root = _expand_below_cut(root, levels_remaining=levels_below_cut, node_spans=node_spans)
        strategy = f"top_expand_{int(levels_below_cut)}"
    else:
        display_root = _contract_tree_around_cut(
            root,
            parent_dist=float('inf'),
            cut_height=float(resolved_cut_height),
            levels_below_cut=levels_below_cut,
            node_spans=node_spans,
        )
        strategy = f"cut_expand_{int(levels_below_cut)}"
    reduced_linkage, leaf_count, display_leaf_spans = _display_tree_to_linkage(display_root)
    if reduced_linkage is None or len(reduced_linkage) == 0:
        reduced_linkage = linkage_matrix
        leaf_count = int(linkage_matrix.shape[0]) + 1
        display_leaf_spans = {int(idx): (int(idx), int(idx)) for idx in range(leaf_count)}
        strategy = "fallback_full"
    return reduced_linkage, {
        "truncation_strategy": strategy,
        "levels_below_cut": int(levels_below_cut),
        "display_leaf_count": int(leaf_count),
        "display_internal_count": int(len(reduced_linkage)),
        "display_leaf_spans": {str(key): [int(value[0]), int(value[1])] for key, value in sorted(display_leaf_spans.items())},
    }


def _build_cluster_positions_for_labels(
    *,
    linkage_matrix: np.ndarray,
    selected_k: int | None,
    cut_mode: str | None,
    display_leaf_spans: dict[str, object] | None,
    dendrogram_data: dict[str, object],
) -> dict[int, float]:
    if cut_mode != "k" or selected_k is None or selected_k < 2:
        return {}
    if not display_leaf_spans:
        return {}
    n_samples = int(linkage_matrix.shape[0]) + 1
    full_leaf_order = leaves_list(linkage_matrix).astype(int)
    leaf_position = np.empty(n_samples, dtype=int)
    leaf_position[full_leaf_order] = np.arange(n_samples, dtype=int)
    raw_cluster_labels = fcluster(linkage_matrix, t=int(selected_k), criterion="maxclust").astype(int)
    cluster_first_positions: list[tuple[int, int]] = []
    for original_cluster_id in sorted(np.unique(raw_cluster_labels).tolist()):
        member_indices = np.flatnonzero(raw_cluster_labels == original_cluster_id)
        if len(member_indices) == 0:
            continue
        cluster_first_positions.append((int(leaf_position[member_indices].min()), int(original_cluster_id)))
    cluster_first_positions.sort(key=lambda item: (item[0], item[1]))
    remap = {int(original_cluster_id): int(new_cluster_id) for new_cluster_id, (_, original_cluster_id) in enumerate(cluster_first_positions)}
    cluster_by_leaf_position = np.empty(n_samples, dtype=int)
    for sample_idx, original_cluster_id in enumerate(raw_cluster_labels.tolist()):
        cluster_by_leaf_position[int(leaf_position[sample_idx])] = int(remap[int(original_cluster_id)])

    display_leaf_cluster_ids: dict[int, int] = {}
    for leaf_id_str, span_raw in display_leaf_spans.items():
        leaf_id = int(leaf_id_str)
        if not isinstance(span_raw, (list, tuple)) or len(span_raw) != 2:
            continue
        span_start = int(span_raw[0])
        span_end = int(span_raw[1])
        covered_cluster_ids = np.unique(cluster_by_leaf_position[span_start : span_end + 1])
        if len(covered_cluster_ids) == 1:
            display_leaf_cluster_ids[leaf_id] = int(covered_cluster_ids[0])

    leaf_ids_in_plot = [int(leaf_id) for leaf_id in dendrogram_data.get("leaves", [])]
    if not leaf_ids_in_plot:
        return {}
    leaf_x_positions = {leaf_id: float(5 + 10 * rank) for rank, leaf_id in enumerate(leaf_ids_in_plot)}
    cluster_x_values: dict[int, list[float]] = {}
    for leaf_id, cluster_id in display_leaf_cluster_ids.items():
        x_value = leaf_x_positions.get(int(leaf_id))
        if x_value is None:
            continue
        cluster_x_values.setdefault(int(cluster_id), []).append(float(x_value))
    return {
        int(cluster_id): float((min(x_values) + max(x_values)) / 2.0)
        for cluster_id, x_values in cluster_x_values.items()
        if x_values
    }


def _annotate_cluster_ids(
    ax: plt.Axes,
    *,
    cluster_positions: dict[int, float],
    cut_height: float | None,
    y_max: float,
) -> None:
    if not cluster_positions:
        return
    if cut_height is not None and cut_height > 0:
        y_text = float(cut_height) * 1.015
    else:
        y_text = float(y_max) * 0.035
    for cluster_id, x_pos in sorted(cluster_positions.items()):
        ax.text(
            float(x_pos),
            y_text,
            f"C{int(cluster_id)}",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
            color="black",
            bbox={"boxstyle": "round,pad=0.15", "facecolor": "white", "edgecolor": "none", "alpha": 0.82},
            zorder=30,
            clip_on=False,
        )


def _apply_axis_styling(ax: plt.Axes, *, y_max: float) -> None:
    if y_max <= 0:
        return
    ax.set_yscale(
        "function",
        functions=(
            lambda y: np.power(np.clip(np.asarray(y, dtype="float64"), 0.0, None), 1.8),
            lambda y: np.power(np.clip(np.asarray(y, dtype="float64"), 0.0, None), 1.0 / 1.8),
        ),
    )
    ax.set_ylim(0.0, y_max * 1.02)
    for collection in ax.collections:
        try:
            collection.set_linewidth(1.3)
            collection.set_alpha(0.95)
        except Exception:  # noqa: BLE001
            pass


def _plot_dendrogram(
    *,
    linkage_matrix: np.ndarray,
    out_dir: Path,
    title: str,
    method: str,
    cut_mode: str | None,
    cut_value: float | int | None,
    selected_k: int | None,
) -> tuple[bool, bool, float | None]:
    fig = None
    fig2 = None
    written = False
    written_cut_level = False
    resolved_cut_height = None
    try:
        resolved_cut_height, cut_label = _resolve_cut_height(
            linkage_matrix=linkage_matrix,
            selected_k=selected_k,
            cut_mode=cut_mode,
            cut_value=cut_value,
        )
        display_linkage, truncation_meta = _build_reduced_linkage_matrix(
            linkage_matrix=linkage_matrix,
            resolved_cut_height=resolved_cut_height,
            levels_below_cut=LEVELS_BELOW_CUT,
        )
        fig, ax = plt.subplots(figsize=(16, 6))
        dendrogram_data = dendrogram(
            display_linkage,
            ax=ax,
            no_labels=True,
            color_threshold=None,
            show_contracted=False,
        )
        y_max = max((max(dcoords) for dcoords in dendrogram_data.get("dcoord", []) if dcoords), default=float(linkage_matrix[:, 2].max(initial=0.0)))
        cluster_positions = _build_cluster_positions_for_labels(
            linkage_matrix=linkage_matrix,
            selected_k=selected_k,
            cut_mode=cut_mode,
            display_leaf_spans=truncation_meta.get("display_leaf_spans") if isinstance(truncation_meta, dict) else None,
            dendrogram_data=dendrogram_data,
        )
        _apply_axis_styling(ax, y_max=float(y_max))
        if resolved_cut_height is not None:
            ax.axhline(
                y=resolved_cut_height,
                color="red",
                linestyle="--",
                linewidth=2.0,
                alpha=0.95,
                label=f"cut ({cut_label})",
                zorder=20,
            )
        _annotate_cluster_ids(ax, cluster_positions=cluster_positions, cut_height=resolved_cut_height, y_max=float(y_max))
        ax.set_title(title)
        ax.set_xlabel("samples")
        ax.set_ylabel("distance")
        fig.tight_layout()
        fig.savefig(out_dir / DENDROGRAM_IMAGE_FILE, dpi=180, bbox_inches="tight")
        plt.close(fig)
        written = True

        if method == "agglomerative" and cut_mode == "distance" and cut_value is not None:
            cut_value_f = float(cut_value)
            fig2, ax2 = plt.subplots(figsize=(16, 6))
            dendrogram_data2 = dendrogram(
                display_linkage,
                ax=ax2,
                no_labels=True,
                color_threshold=None,
                show_contracted=False,
            )
            y_max2 = max((max(dcoords) for dcoords in dendrogram_data2.get("dcoord", []) if dcoords), default=float(linkage_matrix[:, 2].max(initial=0.0)))
            _apply_axis_styling(ax2, y_max=float(y_max2))
            ax2.axhline(y=cut_value_f, color="red", linestyle="--", linewidth=1.2, label=f"cut={cut_value_f:.4g}")
            ax2.set_title(f"{title} (with cut)")
            ax2.set_xlabel("samples")
            ax2.set_ylabel("distance")
            ax2.legend(loc="best")
            fig2.tight_layout()
            fig2.savefig(out_dir / DENDROGRAM_CUT_IMAGE_FILE, dpi=180, bbox_inches="tight")
            plt.close(fig2)
            written_cut_level = True
    finally:
        try:
            plt.close(fig)
        except Exception:  # noqa: BLE001
            pass
        try:
            plt.close(fig2)
        except Exception:  # noqa: BLE001
            pass
    return written, written_cut_level, resolved_cut_height


def _meta_matches(existing: dict[str, Any], expected: dict[str, Any]) -> bool:
    for key, expected_value in expected.items():
        if existing.get(key) != expected_value:
            return False
    return True


def _load_meta(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _artifact_stale(path: Path, *, source_mtime: float) -> bool:
    return (not path.exists()) or path.stat().st_mtime < source_mtime


def ensure_dendrogram_artifacts(
    *,
    run_dir: Path,
    linkage_matrix_path: Path | None,
    title: str,
    method: str,
    linkage: str | None,
    selected_k: int | None,
    cut_mode: str | None,
    cut_value: float | int | None,
) -> dict[str, Any]:
    png_path = run_dir / DENDROGRAM_IMAGE_FILE
    cut_png_path = run_dir / DENDROGRAM_CUT_IMAGE_FILE
    meta_path = run_dir / DENDROGRAM_META_FILE
    if method != "agglomerative":
        return {
            "available": False,
            "message": "Dendrograms are available only for agglomerative clustering runs.",
            "png_path": None,
            "cut_png_path": None,
            "meta_path": meta_path,
            "meta": None,
        }
    if linkage_matrix_path is None or not linkage_matrix_path.exists():
        return {
            "available": False,
            "message": "This export does not include dendrogram linkage data yet.",
            "png_path": None,
            "cut_png_path": None,
            "meta_path": meta_path,
            "meta": None,
        }

    expected_meta = {
        "render_style_version": RENDER_STYLE_VERSION,
        "method": method,
        "linkage": linkage,
        "selected_k": int(selected_k) if selected_k is not None else None,
        "cut_mode": cut_mode,
        "cut_value": float(cut_value) if cut_value is not None else None,
        "display_levels": int(LEVELS_BELOW_CUT),
    }
    existing_meta = _load_meta(meta_path)
    source_mtime = linkage_matrix_path.stat().st_mtime
    needs_main = _artifact_stale(png_path, source_mtime=source_mtime)
    needs_cut = method == "agglomerative" and cut_mode == "distance" and cut_value is not None and _artifact_stale(cut_png_path, source_mtime=source_mtime)
    meta_stale = existing_meta is None or not _meta_matches(existing_meta, expected_meta)

    meta: dict[str, Any] = {
        "render_style_version": RENDER_STYLE_VERSION,
        "method": method,
        "linkage": linkage,
        "selected_k": int(selected_k) if selected_k is not None else None,
        "cut_mode": cut_mode,
        "cut_value": float(cut_value) if cut_value is not None else None,
        "display_levels": int(LEVELS_BELOW_CUT),
        "resolved_cut_height": None,
        "written": False,
        "written_cut_level": False,
        "skip_reason": "",
        "linkage_matrix_file": linkage_matrix_path.name,
    }

    if needs_main or needs_cut or meta_stale:
        try:
            linkage_matrix = np.load(linkage_matrix_path)
            written, written_cut_level, resolved_cut_height = _plot_dendrogram(
                linkage_matrix=linkage_matrix,
                out_dir=run_dir,
                title=title,
                method=method,
                cut_mode=cut_mode,
                cut_value=cut_value,
                selected_k=selected_k,
            )
            meta["written"] = written
            meta["written_cut_level"] = written_cut_level
            meta["resolved_cut_height"] = resolved_cut_height
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            meta["skip_reason"] = f"dendrogram_error: {type(exc).__name__}"
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            return {
                "available": False,
                "message": f"Unable to generate dendrogram: {type(exc).__name__}",
                "png_path": None,
                "cut_png_path": None,
                "meta_path": meta_path,
                "meta": meta,
            }
    else:
        meta = existing_meta or meta

    return {
        "available": png_path.exists(),
        "message": None,
        "png_path": png_path if png_path.exists() else None,
        "cut_png_path": cut_png_path if cut_png_path.exists() else None,
        "meta_path": meta_path,
        "meta": meta,
    }
