from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

try:
    from st_aggrid import AgGrid, GridOptionsBuilder
    from st_aggrid.shared import DataReturnMode, GridUpdateMode
except Exception:  # noqa: BLE001
    AgGrid = None
    GridOptionsBuilder = None
    DataReturnMode = None
    GridUpdateMode = None


def aggrid_available() -> bool:
    return AgGrid is not None and GridOptionsBuilder is not None


def render_feature_aggrid(features_df: pd.DataFrame, *, color: str, height: int = 360, key: str) -> None:
    if features_df.empty:
        st.info("No feature rows available.")
        return
    if not aggrid_available():
        st.dataframe(features_df, width="stretch", hide_index=True)
        return

    gb = GridOptionsBuilder.from_dataframe(features_df)
    gb.configure_default_column(sortable=True, filter=False, resizable=True)
    if "rank" in features_df.columns:
        gb.configure_column("rank", width=80, maxWidth=90)
    if "feature_name" in features_df.columns:
        gb.configure_column("feature_name", minWidth=260, flex=1)
    for numeric_col in ["delta_vs_global", "cluster_value", "global_value"]:
        if numeric_col in features_df.columns:
            gb.configure_column(numeric_col, width=180, minWidth=170)
    gb.configure_grid_options(
        domLayout="normal",
        rowHeight=34,
        headerHeight=38,
    )
    grid_options: dict[str, Any] = gb.build()
    grid_options["defaultColDef"] = {
        **grid_options.get("defaultColDef", {}),
        "sortable": True,
        "resizable": True,
    }
    grid_options["columnDefs"] = [
        {
            **col_def,
            "headerStyle": {"backgroundColor": color, "color": "white", "fontWeight": "600"},
        }
        for col_def in grid_options.get("columnDefs", [])
    ]

    custom_css = {
        ".ag-root-wrapper": {"border": f"2px solid {color}", "borderRadius": "8px"},
        ".ag-header": {"borderBottom": f"1px solid {color}"},
    }

    aggrid_kwargs: dict[str, Any] = {
        "key": key,
        "gridOptions": grid_options,
        "height": height,
        "fit_columns_on_grid_load": False,
        "allow_unsafe_jscode": False,
        "custom_css": custom_css,
        "theme": "streamlit",
        "update_on": [],
        "show_search": False,
        "show_download_button": False,
    }
    if GridUpdateMode is not None:
        aggrid_kwargs["update_mode"] = GridUpdateMode.NO_UPDATE
    else:
        aggrid_kwargs["update_mode"] = "NO_UPDATE"
    if DataReturnMode is not None:
        aggrid_kwargs["data_return_mode"] = DataReturnMode.AS_INPUT
    else:
        aggrid_kwargs["data_return_mode"] = "AS_INPUT"

    AgGrid(features_df, **aggrid_kwargs)
