import { resolve } from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import "vite-react-ssg";
import pkg from "./package.json";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "./src"),
    },
    conditions: ["onnxruntime-web-use-extern-wasm", "import", "module", "browser", "default"],
  },
  worker: {
    format: "es",
  },
  // `pnpm dev` talks to the local backend (`autolyrics serve`); in production the backend serves
  // the built frontend itself, so the API is same-origin.
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8765", changeOrigin: true },
    },
  },
  optimizeDeps: {
    exclude: ["onnxruntime-web"],
  },
  ssgOptions: {
    formatting: "none",
    crittersOptions: false,
  },
});
