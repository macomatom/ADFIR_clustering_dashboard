(function () {
  const COMPONENT_READY = "streamlit:componentReady";
  const SET_COMPONENT_VALUE = "streamlit:setComponentValue";
  const SET_FRAME_HEIGHT = "streamlit:setFrameHeight";
  const RENDER = "streamlit:render";
  const API_VERSION = 1;

  const plotRoot = document.getElementById("plot-root");
  const plotElement = document.getElementById("plot");

  const state = {
    lastPayloadJson: "",
    lastViewport: {
      x_min: null,
      x_max: null,
      reset_requested: false,
      container_width_px: null,
    },
    observer: null,
    relayoutBound: false,
  };

  function postMessage(type, data) {
    window.parent.postMessage({ type, ...data }, "*");
  }

  function setFrameHeight(height) {
    postMessage(SET_FRAME_HEIGHT, { height });
  }

  function setComponentValue(value) {
    const payloadJson = JSON.stringify(value);
    if (payloadJson === state.lastPayloadJson) {
      return;
    }
    state.lastPayloadJson = payloadJson;
    state.lastViewport = value;
    postMessage(SET_COMPONENT_VALUE, { value, dataType: "json" });
  }

  function getContainerWidth() {
    return Math.max(
      0,
      Math.round(
        plotRoot.getBoundingClientRect().width ||
          plotElement.getBoundingClientRect().width ||
          window.innerWidth ||
          0,
      ),
    );
  }

  function maybeReportWidth() {
    const width = getContainerWidth();
    if (!width) {
      return;
    }
    if (state.lastViewport.container_width_px === width) {
      return;
    }
    setComponentValue({
      ...state.lastViewport,
      reset_requested: false,
      container_width_px: width,
    });
  }

  function handleRelayout(eventData) {
    const xMin = eventData["xaxis.range[0]"] ?? (Array.isArray(eventData["xaxis.range"]) ? eventData["xaxis.range"][0] : null);
    const xMax = eventData["xaxis.range[1]"] ?? (Array.isArray(eventData["xaxis.range"]) ? eventData["xaxis.range"][1] : null);
    const resetRequested = Boolean(eventData["xaxis.autorange"] || eventData.autosize);
    setComponentValue({
      x_min: resetRequested ? null : xMin,
      x_max: resetRequested ? null : xMax,
      reset_requested: resetRequested,
      container_width_px: getContainerWidth(),
    });
  }

  function bindPlotEvents() {
    if (state.relayoutBound) {
      return;
    }
    plotElement.on("plotly_relayout", handleRelayout);
    state.relayoutBound = true;
  }

  function ensureResizeObserver() {
    if (state.observer) {
      return;
    }
    state.observer = new ResizeObserver(function () {
      maybeReportWidth();
      setFrameHeight(document.body.scrollHeight);
    });
    state.observer.observe(plotRoot);
  }

  function renderFigure(args) {
    const figure = JSON.parse(args.figure_json || "{}");
    const config = JSON.parse(args.config_json || "{}");
    const height = Number(args.plot_height || 360);
    plotElement.style.height = `${height}px`;

    const layout = { ...(figure.layout || {}), autosize: true, height };
    Plotly.react(plotElement, figure.data || [], layout, config).then(function () {
      bindPlotEvents();
      ensureResizeObserver();
      setFrameHeight(document.body.scrollHeight);
      maybeReportWidth();
    });
  }

  window.addEventListener("message", function (event) {
    const message = event.data || {};
    if (message.type !== RENDER) {
      return;
    }
    renderFigure(message.args || {});
  });

  postMessage(COMPONENT_READY, { apiVersion: API_VERSION });
})();
