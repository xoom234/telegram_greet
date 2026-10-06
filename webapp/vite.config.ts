import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    server: {
      host: true,
      proxy: {
        "/api": {
          target: env.VITE_API_PROXY || "https://telegram-greet-omega.vercel.app",
          changeOrigin: true,
          secure: true,
        },
      },
    },
  };
});
