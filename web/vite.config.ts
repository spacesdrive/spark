import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// The dev server proxies /api to the FastAPI process, so the browser sees one
// origin. That keeps the session cookie same-site in development, exactly as
// it is in production behind the reverse proxy.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  build: {
    rollupOptions: {
      output: {
        // Charts and the auth client are large and only some pages need them,
        // so they get their own chunks instead of sitting in the entry bundle.
        manualChunks: {
          charts: ["recharts"],
          auth: ["@supabase/supabase-js"],
          react: ["react", "react-dom", "react-router-dom"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
