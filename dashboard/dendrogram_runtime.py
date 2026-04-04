from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from scipy.cluster.hierarchy import dendrogram

matplotlib.use("Agg")
import matplotlib.pyplot as plt


DENDROGRAM_IMAGE_FILE = "cluster_dendrogram__v1.png"
DENDROGRAM_CUT_IMAGE_FILE = "cluster_dendrogram_at_cut__v1.png"
DENDROGRAM_META_FILE = "cluster_dendrogram_meta__v1.json"
RENDER_STYLE_VERSION = 2


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
    return (lower_dist + upper_dist) / 2.0, f"k={k}"


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
    display_levels: int,
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
        fig, ax = plt.subplots(figsize=(16, 6))
        dendrogram_data = dendrogram(
            linkage_matrix,
            ax=ax,
            no_labels=True,
            color_threshold=None,
            truncate_mode="lastp",
            p=display_levels,
            show_contracted=False,
        )
        y_max = max((max(dcoords) for dcoords in dendrogram_data.get("dcoord", []) if dcoords), default=float(linkage_matrix[:, 2].max(initial=0.0)))
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
                linkage_matrix,
                ax=ax2,
                no_labels=True,
                color_threshold=None,
                truncate_mode="lastp",
                p=display_levels,
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
    display_levels = max(1, int(selected_k) + 2) if selected_k is not None else 10

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
        "display_levels": int(display_levels),
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
        "display_levels": int(display_levels),
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
                display_levels=display_levels,
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
