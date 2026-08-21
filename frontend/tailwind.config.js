/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    "./node_modules/@tremor/react/dist/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["'Source Sans 3'", "system-ui", "sans-serif"],
      },
      colors: {
        theme: {
          text: "var(--theme-text)",
          "text-secondary": "var(--theme-text-secondary)",
          "text-tertiary": "var(--theme-text-tertiary)",
          bg: "var(--theme-bg)",
          "bg-card": "var(--theme-bg-card)",
          "bg-elevated": "var(--theme-bg-elevated)",
          "bg-subtle": "var(--theme-bg-subtle)",
          "bg-code": "var(--theme-bg-code)",
          border: "var(--theme-border)",
          "border-hover": "var(--theme-border-hover)",
          "border-subtle": "var(--theme-border-subtle)",
          "border-faint": "var(--theme-border-faint)",
          primary: "var(--theme-primary)",
          "primary-hover": "var(--theme-primary-hover)",
          "primary-light": "var(--theme-primary-light)",
        },
      },
    },
  },
  plugins: [],
};
