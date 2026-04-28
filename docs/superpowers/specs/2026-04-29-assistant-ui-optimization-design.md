# Assistant UI Optimization Design

## Goal

Optimize the assistant management panel and chat selector UI by borrowing key design elements from YubbChat's "Assistant Square" while staying consistent with LambChat's warm stone palette and glass-morphism design system.

## Design Decisions

### 1. Card Gradient Header

Each assistant card gets a 48px gradient bar at the top, generated from the assistant name's hash:

- **Color generation:** HSL with hue derived from name hash (0-360), saturation 25-40%, lightness 65-80%
- **Direction:** 135deg, two-to-three color stops
- **Rationale:** Gives visual variety without requiring per-assistant images. Low saturation keeps it tasteful within the stone palette.

### 2. Category System

Predefined categories with lucide-react icons:

| Category | Icon | Label |
|----------|------|-------|
| Programming | `Code` | Programming |
| Writing | `PenLine` | Writing |
| Translation | `Languages` | Translation |
| Education | `GraduationCap` | Education |
| Business | `Briefcase` | Business |
| Creative | `Palette` | Creative |
| Analysis | `BarChart3` | Analysis |
| General | `Sparkles` | General |

- Each card displays a category badge (small rounded pill with icon + text)
- Create/edit form uses a dropdown for category selection
- Tags remain as free-form labels alongside categories

### 3. Management Panel Layout (`/assistants`)

**Category filter bar:**
- Below search bar, above card grid
- Horizontal `flex-wrap` pill buttons
- Unselected: `bg-stone-100 dark:bg-stone-800`; Selected: `bg-stone-900 dark:bg-stone-100` (inverted)
- First button is "All" (default selected)
- Works in combination with existing scope tabs (All/Marketplace/My Library)

**Search:**
- Fuse.js fuzzy search across name, description, system_prompt, tags
- Existing search input gets a clear (`×`) button
- Search and category filters stack (both active simultaneously)

**Card grid:**
- Responsive: `grid-cols-1 md:grid-cols-2 xl:grid-cols-3`
- Gap: `gap-4` (slightly larger than current `gap-3`)
- Public/private scope shown as small icon in top-right corner instead of badge
- Hover: `translateY(-2px)` + `shadow-md` + border color deepens, `transition-all duration-200`
- Clicking card body navigates to detail page; action buttons (Clone/Edit/Delete) stop propagation

**Empty state:** lucide `Bot` icon + contextual message based on active filters
**Loading state:** Skeleton cards matching final card layout (including gradient bar placeholder)

### 4. Detail Page (`/assistants/:id`)

**Desktop layout (lg:grid-cols-3):**
- Left 2/3: Info card + System prompt preview
- Right 1/3: Related assistants

**Sticky header:**
- Left: Back button (chevron-left)
- Right: "Start Chat" primary button

**Info card (glass-card):**
- Subtle gradient background
- 64×64 rounded avatar + name + category badge + description
- Desktop: horizontal layout; Mobile: vertical centered stack

**System prompt section:**
- `<pre>` block in `bg-stone-100 dark:bg-stone-800`, max-height 400px, scrollable
- "Copy" button with clipboard icon; shows "Copied!" for 2 seconds on click
- Blue-tinted tip bar below: "Use this prompt for best results"

**Related assistants sidebar:**
- Same category, max 6 items
- Each row: 40×40 rounded avatar + name + truncated description + chevron-right
- Hover: `bg-stone-100 dark:bg-stone-800` + arrow translateX animation
- Empty state: `Package` icon + "No similar assistants found"
- Clicking navigates to that assistant's detail page

**"Start Chat" button:**
- Switches to chat tab, auto-selects the assistant
- Mobile: full-width button below the two-column layout (hidden on lg)

### 5. Selector Optimization (Chat Header Dropdown)

**Trigger button:**
- Keep current pill shape and glass style
- Add small gradient dot matching the card gradient color
- Name `truncate` to keep pill width stable

**Dropdown panel:**
- Width: 400px (up from 340px)
- Category quick-filter bar at top (horizontal pills, same style as main panel)
- Grouping: by category first, then Marketplace / My Assistants within each
- Each option: 4px left gradient bar (matching card gradient) + avatar + name + description (2-line clamp) + checkmark if selected
- Hover: `bg-stone-100 dark:bg-stone-800` + `translateX(4px)`
- Search input at top of dropdown, real-time filtering combined with category

**Interactions:**
- Keep scale-in open/close animation
- Close immediately on option click
- Empty state when no results

## Files to Change

### New files:
- `frontend/src/components/assistant/AssistantDetailPage.tsx` — Detail page component
- `frontend/src/components/assistant/AssistantCard.tsx` — Extracted card component with gradient
- `frontend/src/components/assistant/CategoryFilter.tsx` — Category filter bar
- `frontend/src/components/assistant/gradientUtils.ts` — Name-to-gradient color generation
- `frontend/src/components/assistant/categories.ts` — Category definitions with icons

### Modified files:
- `frontend/src/components/panels/AssistantsPanel.tsx` — New card grid, filter bar, search
- `frontend/src/components/assistant/AssistantSelector.tsx` — Wider dropdown, category filter, gradient bars
- `frontend/src/components/layout/AppContent/TabContent.tsx` — Add detail page route
- `frontend/src/components/layout/AppContent/types.ts` — Add detail tab type
- `frontend/src/types/assistant.ts` — Add `category` field to Assistant type
- `frontend/src/hooks/useAssistants.ts` — Add category filter param
- `frontend/src/services/api/assistant.ts` — Add category query param to list
- `frontend/package.json` — Add `fuse.js` dependency

### Backend changes (minimal):
- `src/kernel/schemas/assistant.py` — Add optional `category` field
- `src/infra/assistant/` — Support category in CRUD operations
- `src/api/routes/assistant.py` — Support category query param in list endpoint

## Out of Scope

- Character import (PNG/JSON parsing from YubbChat) — not needed for current use case
- Per-assistant default model/agent options UI — data model exists but UI deferred
- "Recent Updates" two-section layout — simpler single grid is sufficient
- Admin-only creation gating — creation remains open to all users
