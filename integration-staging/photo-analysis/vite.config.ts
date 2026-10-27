/**
 * Demo only: serves demo/ and mounts the interpretation endpoint on the dev
 * server so you can test end-to-end with `npm run demo`.
 * The main app will mount the handler in its own backend instead.
 */
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { createInterpretHandler } from "./server/handler";
import { toNodeMiddleware } from "./server/node";

export default defineConfig(({ mode }) => {
  const env = { ...process.env, ...loadEnv(mode, process.cwd(), "") };
  const handler = toNodeMiddleware(
    createInterpretHandler({ model: env.COPILOT_MODEL || undefined }),
  );
  return {
    root: "demo",
    plugins: [
      react(),
      {
        name: "interpret-photo-endpoint",
        configureServer(server) {
          server.middlewares.use("/api/interpret-photo", (req, res) => void handler(req, res));
        },
      },
    ],
    build: { outDir: "../dist", emptyOutDir: true },
  };
});
