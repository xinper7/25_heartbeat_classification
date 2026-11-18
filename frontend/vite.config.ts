import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { execFileSync } from "node:child_process";
let revision = "local";
try { revision = execFileSync("git", ["rev-parse", "--short", "HEAD"], { encoding: "utf8" }).trim(); } catch { /* Source archives may omit Git metadata. */ }

export default defineConfig({
  plugins: [vue()],
  define: { __BUILD_REVISION__: JSON.stringify(revision) },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/docs": "http://127.0.0.1:8000",
      "/openapi.json": "http://127.0.0.1:8000",
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "ui-kit": ["element-plus", "@element-plus/icons-vue"],
          charts: [
            "echarts/core",
            "echarts/charts",
            "echarts/components",
            "echarts/renderers",
          ],
        },
      },
    },
    chunkSizeWarningLimit: 1200,
  },
});
