# ImageGenerateItem Redesign — aicss.dev Style

**Date:** 2026-08-16
**Status:** Approved
**Scope:** Redesign the entire `ImageGenerateItem` (loading placeholder, detail panel, compact view) with aicss.dev-inspired shimmering canvas aesthetic, using LambChat theme variables.

## Reference

- Source: https://www.aicss.dev/components/image-generation
- Author: @kvnkld (AIcss)
- Style: dot-grid + morphing glow blobs + breathing opacity + resolution badge + shimmer text label

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/components/chat/ChatMessage/items/ImageGenerateItem.tsx` | Restructure loading placeholder JSX, update all color classes to theme variables |
| `frontend/src/styles/components.css` | Replace `.ai-image-generation-frame*` block with new dot-grid/glow animation CSS |
| `frontend/src/i18n/` | Add "Generating image" translation key |

## Design Decisions

1. **Color scheme:** All colors driven by `var(--theme-*)` variables. No hardcoded hex values. Theme-aware via LambChat's existing `dark` class toggle.
2. **CSS approach:** Global CSS classes in `components.css` + Tailwind utilities. No CSS Modules (follows project convention).
3. **Accessibility:** `prefers-reduced-motion` media query disables all animations. ARIA roles and labels preserved.
4. **No functional changes:** Image gallery, reference images, copy buttons, session gallery integration, pill/panel behavior all remain identical. Only visual styling changes.

## Loading Placeholder

The core visual change — replaces the violet skewed light-bar shimmer with aicss.dev's dot-grid + morphing glow canvas.

### Structure

```
.ig-canvas (square, max-width 208px detail / 160px compact)
├── .ig-dots   — dot-grid pattern layer (low opacity)
├── .ig-glow   — morphing glow layer (mask-image animation)
└── .ig-res    — resolution badge (top-right corner, mono font)
.ig-meta
├── .ig-label  — "Generating image" (shimmer text effect)
└── .ig-prompt — prompt text (muted)
```

### Animations

- **`ig-morph`** (4.2s, `cubic-bezier(0.35, 1.55, 0.65, 1)`, infinite): Moves the glow blobs around the canvas using `mask-size` and `mask-position` keyframes across 4 waypoints.
- **`ig-breathe`** (1.9s, `cubic-bezier(0.66, 0, 0.34, 1)`, infinite): Oscillates glow opacity between 0.55 and 1.0.
- **`ig-shine`** (2.25s, `cubic-bezier(0.25, 0.1, 0.25, 1)`, infinite): Sweeps a gradient across the "Generating image" text via `background-position`.

### Theme Colors

| Element | Light | Dark |
|----------|-------|------|
| Canvas bg | `var(--theme-bg-card)` | `var(--theme-bg-card)` |
| Dots | `color-mix(in srgb, var(--theme-text) 22%, transparent)` | same |
| Glow dots | `color-mix(in srgb, var(--theme-text) 90%, transparent)` | same |
| Resolution badge text | `var(--theme-text-tertiary)` | same |
| Resolution badge bg | `color-mix(in srgb, var(--theme-bg) 72%, transparent)` | same |
| Label text | `var(--theme-text)` via gradient clip | same |
| Prompt text | `var(--theme-text-secondary)` | same |

## Detail Panel

- **Header card:** Neutral theme styling (`border-theme-border`, `bg-theme-bg-card`). Icon and text use `theme-text` / `theme-text-tertiary`. Remove all purple overrides.
- **Tags:** Neutral gray pills using theme variables instead of `bg-violet-*` / `text-violet-*`.
- **Prompt block:** Keep structure (header row + content row). Colors from theme variables.
- **Image gallery:** Remove purple hover effects (`hover:border-violet-*`). Use `hover:border-theme-border` or subtle opacity change.
- **Reference images:** Same neutral treatment.
- **Fallback text:** Unchanged.

## Compact View

- **Mini header:** Neutral gray background/text instead of violet.
- **Loading placeholder:** Same aicss.dev dot-grid + glow, but `max-width: 160px`, smaller `ig-res` font size.
- **Tags:** Neutral gray.
- **Image grid / reference thumbnails:** Remove purple hover/border, use neutral theme colors.

## CollapsiblePill

- Remove purple icon color override. Use default status-based coloring (amber for loading, emerald for success).
- Label text stays as-is.

## Result Animation

Keep existing `ai-image-generation-result-in` keyframe for image fade/scale-in when results arrive.

## Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  .ig-glow { animation: none; opacity: 0.7; }
  .ig-label { animation: none; color: var(--theme-text); }
}
```

## i18n

New key: `chat.message.generatingImage` = "Generating image" (with translations for zh-CN, etc.)
