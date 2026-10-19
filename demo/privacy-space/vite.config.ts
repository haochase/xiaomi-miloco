import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import path from "node:path";

const webRoot = path.resolve(import.meta.dirname, "../../web");

export default defineConfig({
  root: ".",
  plugins: [react()],
  resolve: {
    alias: {
      react: path.join(webRoot, "node_modules/react"),
      "react-dom": path.join(webRoot, "node_modules/react-dom"),
    },
  },
  server: { host: "127.0.0.1", port: 4178 },
  build: { outDir: "dist", emptyOutDir: true },
});
