import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: "#0b0d10",
          50: "#f6f7f9",
          100: "#e7eaf0",
          200: "#c9cfdb",
          300: "#9aa3b5",
          400: "#6b7588",
          500: "#4a5265",
          600: "#363c4a",
          700: "#252a35",
          800: "#161a22",
          900: "#0b0d10",
        },
        brand: {
          DEFAULT: "#6366f1",
          soft: "#818cf8",
        },
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
