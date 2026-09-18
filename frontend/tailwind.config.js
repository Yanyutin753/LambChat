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
        8: "0.5rem",
        8.5: "0.53125rem",
        9: "0.5625rem",
        10: "0.625rem",
        10.5: "0.65625rem",
        11: "0.6875rem",
        12: "0.75rem",
        12.5: "0.78125rem",
        13: "0.8125rem",
        13.5: "0.84375rem",
        14: "0.875rem",
        15: "0.9375rem",
        16: "1rem",
        17: "1.0625rem",
        18: "1.125rem",
        20: "1.25rem",
        24: "1.5rem",
        30: "1.875rem",
        36: "2.25rem",
      },
      fontFamily: {
        // CJK 界面黑体走系统字体（苹方/雅黑等）：网页字体 Noto Sans SC
        // 的 600/700 比系统黑体重一截，接管后粗体观感发黑，已回退。
        sans: ["'Source Sans 3'", "system-ui", "sans-serif"],
        // 排除 Georgia/ui-serif：默认老式数字（old-style figures）会低于基线，
        // 导致数字与文本不在同一水平线；Source Serif 4 默认 lining figures。
        serif: [
          "'Source Serif 4'",
          "'Noto Serif SC'",
          "Cambria",
          "'Times New Roman'",
          "Times",
          "'Source Han Serif SC'",
          "'Songti SC'",
          "SimSun",
          "serif",
        ],
      },
      colors: {
        // 裸 var() 字符串无法承载透明度修饰符（border-theme-border/60 会
        // 静默不生成，边框回落 preflight 默认 #e5e7eb，深色模式呈现白边），
        // 因此统一走 color-mix + <alpha-value>：无修饰符时 100% 混合等于
        // 原色，/N 时注入对应透明度（守卫测试 themeColorAlphaSource 盯这条）
        theme: {
          text: "color-mix(in srgb, var(--theme-text) calc(<alpha-value> * 100%), transparent)",
          "text-secondary":
            "color-mix(in srgb, var(--theme-text-secondary) calc(<alpha-value> * 100%), transparent)",
          "text-tertiary":
            "color-mix(in srgb, var(--theme-text-tertiary) calc(<alpha-value> * 100%), transparent)",
          bg: "color-mix(in srgb, var(--theme-bg) calc(<alpha-value> * 100%), transparent)",
          "bg-card":
            "color-mix(in srgb, var(--theme-bg-card) calc(<alpha-value> * 100%), transparent)",
          "bg-elevated":
            "color-mix(in srgb, var(--theme-bg-elevated) calc(<alpha-value> * 100%), transparent)",
          "bg-subtle":
            "color-mix(in srgb, var(--theme-bg-subtle) calc(<alpha-value> * 100%), transparent)",
          "bg-code":
            "color-mix(in srgb, var(--theme-bg-code) calc(<alpha-value> * 100%), transparent)",
          border: "color-mix(in srgb, var(--theme-border) calc(<alpha-value> * 100%), transparent)",
          "border-hover":
            "color-mix(in srgb, var(--theme-border-hover) calc(<alpha-value> * 100%), transparent)",
          "border-subtle":
            "color-mix(in srgb, var(--theme-border-subtle) calc(<alpha-value> * 100%), transparent)",
          "border-faint":
            "color-mix(in srgb, var(--theme-border-faint) calc(<alpha-value> * 100%), transparent)",
          primary:
            "color-mix(in srgb, var(--theme-primary) calc(<alpha-value> * 100%), transparent)",
          "primary-hover":
            "color-mix(in srgb, var(--theme-primary-hover) calc(<alpha-value> * 100%), transparent)",
          "primary-light":
            "color-mix(in srgb, var(--theme-primary-light) calc(<alpha-value> * 100%), transparent)",
          "toggle-knob":
            "color-mix(in srgb, var(--theme-toggle-knob) calc(<alpha-value> * 100%), transparent)",
          // 语义状态色：CSS 变量在 tokens.css 按三主题各自定义（sepia 降饱和），
          // 漏映射时 text-theme-error 之类会静默不生成（守卫测试盯这条）
          success:
            "color-mix(in srgb, var(--theme-success) calc(<alpha-value> * 100%), transparent)",
          error: "color-mix(in srgb, var(--theme-error) calc(<alpha-value> * 100%), transparent)",
          warning:
            "color-mix(in srgb, var(--theme-warning) calc(<alpha-value> * 100%), transparent)",
          info: "color-mix(in srgb, var(--theme-info) calc(<alpha-value> * 100%), transparent)",
        },
      },
    },
  },
  plugins: [],
};
