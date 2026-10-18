import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { VitePWA } from "vite-plugin-pwa";

// Served from GitHub Pages at https://<user>.github.io/home-seeker-hub/
export default defineConfig({
  base: process.env.VITE_BASE ?? "/home-seeker-hub/",
  server: { fs: { allow: [".."] } }, // default preferences live in ../config
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon.svg", "apple-touch-icon.png"],
      manifest: {
        name: "Home Seeker – mieszkania w Poznaniu",
        short_name: "Mieszkania",
        description: "Oferty mieszkań dopasowane do preferencji",
        lang: "pl",
        theme_color: "#1f6f5c",
        background_color: "#f6f5f1",
        display: "standalone",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // App shell only; listing data always comes fresh from Supabase.
        navigateFallback: "index.html",
        globPatterns: ["**/*.{js,css,html,svg,png}"],
      },
    }),
  ],
  test: { environment: "node" },
});
