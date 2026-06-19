import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      "/upload": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/solve-grid": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
