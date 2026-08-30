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
      // 全站字号刻度：命名 token + rem，禁止 text-[Npx] 写死像素
      // （CI 由 fontSizeScaleSource.test.ts 守护）。token 只声明 font-size、
      // 不带 line-height，与历史 text-[Npx] 行为逐像素一致。
      // 后续“自定义字体大小”能力：调整根字号即可全局等比缩放，
      // 或直接改这里的 token 值。
      fontSize: {
        "8": "0.5rem",
        "8.5": "0.53125rem",
        "9": "0.5625rem",
        "10": "0.625rem",
        "10.5": "0.65625rem",
        "11": "0.6875rem",
        "12": "0.75rem",
        "12.5": "0.78125rem",
        "13": "0.8125rem",
        "13.5": "0.84375rem",
        "14": "0.875rem",
        "15": "0.9375rem",
        "17": "1.0625rem",
        "20": "1.25rem",
      },
      fontFamily: {
        sans: ["'Source Sans 3'", "system-ui", "sans-serif"],
        // 排除 Georgia/ui-serif：默认老式数字（old-style figures）会低于基线，
        // 导致数字与文本不在同一水平线；Source Serif 4 默认 lining figures。
        serif: [
          "'Source Serif 4'",
          "Cambria",
          "'Times New Roman'",
          "Times",
          "'Noto Serif SC'",
          "'Source Han Serif SC'",
          "'Songti SC'",
          "SimSun",
          "serif",
        ],
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
