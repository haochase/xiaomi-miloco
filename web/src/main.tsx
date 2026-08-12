import React from "react";
import ReactDOM from "react-dom/client";
import { registerBuiltInAgentPanels } from "./agents/builtin";
import { agentPanelRegistry } from "./agents/registry";
import "./i18n";
import { App } from "./App";
import { registerPwa } from "./pwa/register";
import "./styles/theme.css";

registerBuiltInAgentPanels(agentPanelRegistry);

// 主题决议优先级：URL ?theme= > localStorage > 跟随系统（不设 data-theme）。
// URL ?theme=dark / ?theme=light 是**临时覆盖**（截图 / 工程调试 / 临时看一眼），
// **不写** localStorage——避免"用 URL 看一眼就被永久保存"。
// 只有用户在设置抽屉里主动选的才进 localStorage 持久化。
const themeParam = new URLSearchParams(window.location.search).get("theme");
const savedTheme = localStorage.getItem("web:theme");
if (themeParam === "dark" || themeParam === "light") {
  document.documentElement.setAttribute("data-theme", themeParam);
  const url = new URL(window.location.href);
  url.searchParams.delete("theme");
  window.history.replaceState({}, "", url.toString());
} else if (savedTheme === "dark" || savedTheme === "light") {
  document.documentElement.setAttribute("data-theme", savedTheme);
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

registerPwa();
