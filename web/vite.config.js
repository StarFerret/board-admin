import path from "path";
import { fileURLToPath } from "url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const root = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(root, "src") },
  },
  server: {
    port: 5173,
    proxy: {
      // Control API is proxied by the Board server to the supervisor (7411).
      "/api": "http://127.0.0.1:7410",
      "/socket.io": {
        target: "http://127.0.0.1:7410",
        ws: true,
      },
    },
  },
});
