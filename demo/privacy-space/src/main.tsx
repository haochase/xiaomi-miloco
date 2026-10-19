import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { demoState } from "./demoData";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App state={demoState} />
  </StrictMode>,
);
