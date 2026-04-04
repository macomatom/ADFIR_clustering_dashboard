from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
import streamlit.components.v1 as components


_COMPONENT_DIR = Path(__file__).resolve().parent / "components" / "live_plotly"
_live_plotly_component = components.declare_component(
    "live_plotly_viewport",
    path=str(_COMPONENT_DIR),
)


def render_live_plotly(
    fig: go.Figure,
    *,
    key: str,
    height: int = 360,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _live_plotly_component(
        figure_json=fig.to_json(),
        plot_height=int(height),
        config_json=json.dumps(
            config
            or {
                "responsive": True,
                "displaylogo": False,
                "scrollZoom": True,
                "doubleClick": "reset+autosize",
            }
        ),
        default={
            "x_min": None,
            "x_max": None,
            "reset_requested": False,
            "container_width_px": None,
        },
        key=key,
    )
    if not isinstance(payload, dict):
        return {
            "x_min": None,
            "x_max": None,
            "reset_requested": False,
            "container_width_px": None,
        }
    return payload
