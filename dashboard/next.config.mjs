/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Required for the Docker standalone build (copies only the minimal runtime).
  output: "standalone",
  // The dashboard is a pure front-end skeleton; all data comes from the
  // FastAPI backend at NEXT_PUBLIC_API_BASE (with a mock-data fallback).
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000",
  },
};

export default nextConfig;
