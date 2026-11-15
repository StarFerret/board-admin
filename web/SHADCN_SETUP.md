# Shadcn/UI & Mobile Responsive Setup

This application now uses **shadcn/ui** components and is fully responsive for computers, tablets, and phones.

## What Changed

### 1. UI Framework: Tailwind CSS + shadcn/ui
- Added `tailwindcss`, `autoprefixer`, and `postcss`
- Installed all shadcn/ui dependencies (`@radix-ui/*`, `clsx`, `class-variance-authority`, `lucide-react`)
- Created `tailwind.config.js` with dark mode support and CSS variables
- Created `index.css` with Tailwind directives and custom styles

### 2. UI Components Created in `/web/src/components/ui/`
- **Button** - Shadcn/ui Button with variants (default, ghost, outline, etc.)
- **Input** - Shadcn/ui Input component
- All components use shadcn/ui's `cn()` utility for class composition

### 3. Mobile Responsive Design
The app is now fully responsive:

**Phones (< 640px):**
- Single column layout
- Side panel folds into mobile view
- Smaller text and touch-friendly buttons (min-height 44px)
- Reduced header height and font sizes
- Full-width cards on single column grid

**Tablets (640px - 1024px):**
- Two-column card grids (responsive: `grid-cols-1 sm:grid-cols-2`)
- Side panel in chat view remains visible
- Optimized spacing and padding

**Desktops (≥ 1024px):**
- Four-column card grids
- Full side panel with agent context
- Multi-column workspaces

### 4. Touch-Friendly Mobile UX
On touch devices (`@media (hover: none) and (pointer: coarse)`):
- All interactive elements have minimum 44px height (Apple's accessibility guideline)
- Buttons, inputs, and links are sized for easy tapping
- No hover-only interactions on mobile

### 5. Accessibility Features
- Focus-visible outlines for keyboard navigation
- Semantic HTML structure
- Proper ARIA labels where needed
- Responsive font scaling

## Development Setup

After `npm install`, the development server runs at:
```bash
cd web
npm run dev
```

The Vite dev server proxies API calls to the Python backend.

## Build Production

To build for production (compresses and bundles assets):
```bash
npm run build
```

Production files are in `/web/dist/` and need to be copied to `web/dist/` before deploying the web app.

## Key Responsive Breakpoints Used

- **Mobile**: `< 640px` (single column, folded side panel)
- **Tablet**: `≥ 640px` (two-column grids, visible side panel)  
- **Desktop**: `≥ 1024px` (four-column grids, full layout)

All Tailwind classes use responsive prefixes like `sm:`, `md:`, and `lg:` for breakpoint-specific styling.

## Color Scheme

The app uses a dark theme with shadcn/ui CSS variables:
- Background: `#0c0e12` (very dark slate)
- Primary: `#6ea8ff` (sky blue accent)
- Success: `#3dd68c` (green)
- Warning: `#f5c15c` (amber)
- Error: `#ff6b7a` (pink/red)

Colors are defined in `/web/src/index.css` and can be customized by modifying the CSS variables.

## Notes

The shadcn/ui components integrate seamlessly with your existing custom CSS styles. The design system follows shadcn/ui's minimalist, accessible principles while maintaining the app's original aesthetic.