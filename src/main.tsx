import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@/App";
import "@/styles/global.css";

const container = document.getElementById("root");

if (!container) {
  // This can only happen if index.html was edited; fail loudly rather than blank.
  throw new Error("Mount point #root is missing from index.html.");
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
