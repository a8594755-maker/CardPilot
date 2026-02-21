import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const DEV_SERVER_TARGET = process.env.VITE_DEV_SERVER_TARGET || process.env.VITE_SERVER_URL || "http://127.0.0.1:4000";

export default defineConfig({
  plugins: [tailwindcss(), react()],
  envDir: "../../",
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: false,
    proxy: {
      "/socket.io": {
        target: DEV_SERVER_TARGET,
        changeOrigin: true,
        ws: true,
      },
      "/api": {
        target: DEV_SERVER_TARGET,
        changeOrigin: true,
      },
    },
  },
});
