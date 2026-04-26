import fs from "node:fs";
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import type { Plugin } from "vite";

function serveAudioData(): Plugin {
  const dataDir = path.resolve(__dirname, "../backend/data");
  return {
    name: "serve-audio-data",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url?.startsWith("/audio-data/")) return next();
        const relPath = req.url.replace("/audio-data/", "");
        const filePath = path.join(dataDir, relPath);
        if (!filePath.startsWith(dataDir)) return next();
        if (!fs.existsSync(filePath)) return next();

        const stat = fs.statSync(filePath);
        const total = stat.size;
        const range = req.headers.range;

        if (range) {
          const [startStr, endStr] = range.replace("bytes=", "").split("-");
          const start = parseInt(startStr!, 10);
          const end = endStr ? parseInt(endStr, 10) : total - 1;
          res.writeHead(206, {
            "Content-Range": `bytes ${start}-${end}/${total}`,
            "Accept-Ranges": "bytes",
            "Content-Length": end - start + 1,
            "Content-Type": "audio/wav",
          });
          fs.createReadStream(filePath, { start, end }).pipe(res);
        } else {
          res.writeHead(200, {
            "Content-Length": total,
            "Content-Type": "audio/wav",
            "Accept-Ranges": "bytes",
          });
          fs.createReadStream(filePath).pipe(res);
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), serveAudioData()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8888",
        changeOrigin: true,
      },
    },
  },
});
