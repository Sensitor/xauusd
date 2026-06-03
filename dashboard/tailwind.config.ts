import type { Config } from "tailwindcss";

/**
 * Dark "trading terminal" palette. Color tokens are intentionally semantic
 * (buy/sell/notrade/severity) so components never hard-code hex values.
 */
const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        terminal: {
          bg: "#0a0e14",          // app background
          surface: "#10151f",     // cards / panels
          "surface-2": "#161c28", // nested surfaces, table headers
          border: "#222b3a",
          "border-strong": "#2f3b4f",
          muted: "#7d8aa0",       // secondary text
          text: "#e6ecf5",        // primary text
          accent: "#3b82f6",      // brand blue
          "accent-soft": "#1d4ed8",
        },
        // Directional / decision tokens.
        buy: {
          DEFAULT: "#16c784",
          soft: "rgba(22, 199, 132, 0.14)",
          border: "rgba(22, 199, 132, 0.40)",
        },
        sell: {
          DEFAULT: "#ea3943",
          soft: "rgba(234, 57, 67, 0.14)",
          border: "rgba(234, 57, 67, 0.40)",
        },
        notrade: {
          DEFAULT: "#f0b90b",
          soft: "rgba(240, 185, 11, 0.14)",
          border: "rgba(240, 185, 11, 0.40)",
        },
        // Risk-flag severities.
        info: "#3b82f6",
        warning: "#f0b90b",
        critical: "#ea3943",
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "monospace",
        ],
      },
      boxShadow: {
        card: "0 1px 0 0 rgba(255,255,255,0.02) inset, 0 8px 24px -16px rgba(0,0,0,0.8)",
      },
      keyframes: {
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.45" },
        },
      },
      animation: {
        "pulse-soft": "pulse-soft 1.8s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
