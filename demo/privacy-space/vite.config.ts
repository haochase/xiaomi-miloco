import path from "node:path";
import { createRequire } from "node:module";

const webRoot = path.resolve(import.meta.dirname, "../../web");
const require = createRequire(import.meta.url);
const react = require(path.join(webRoot, "node_modules/@vitejs/plugin-react"));
const { defineConfig } = require(path.join(webRoot, "node_modules/vite"));

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
