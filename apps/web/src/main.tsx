import { companyName } from "./brand";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles.css";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Missing root element");
}

if (companyName !== "EAG") document.title = companyName;

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
