import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#090D14",
        panel: "#101722",
        elevated: "#151F2D",
        line: "#202C3B",
        muted: "#8492A6",
        ink: "#E8EEF7",
        accent: "#64D6A1",
        "accent-strong": "#39B980",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "Arial", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 32px rgba(100, 214, 161, 0.10)",
      },
    },
  },
  plugins: [],
};

export default config;