import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { OverlayView } from "./views/OverlayView";

import "./styles/midfi.css";
import "./styles/animations.css";

// Multi-window routing: Tauri spawns the overlay with
// `index.html?overlay=1` so the same Vite bundle renders either the main
// App or the OverlayView depending on the query string. Cheaper than a
// second Vite entry (avoids two bundles + double bootstrap) and good
// enough for two-window apps.
const isOverlay = new URLSearchParams(window.location.search).get("overlay") === "1";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    {isOverlay ? <OverlayView /> : <App />}
  </React.StrictMode>,
);
