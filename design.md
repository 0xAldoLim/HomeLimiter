# Design: HomeLimiter

The dashboard's shared design system. New screens inherit this system; change it deliberately.

## System

- Genre: modern-minimal, app-screen scope.
- Theme: Hallmark Console, dealt 2/3 from Ink, Console and Ultraviolet.
- Default colourway: paper. Alternate: graphite through the existing dark-mode control.
- Signature: the device/address ledger and its adjacent enforcement-path readout.
- Navigation: top-level destinations, native disclosure on narrow screens.
- Material: actual API device inventory, policy state, reconciliation state and audit events. Demo data remains explicitly simulated. No stock photographs, fabricated readings or decorative traffic charts.

## Tokens

`src/homelimiter/web/tokens.css` is the source of truth. The default roles are:

```css
:root {
  --color-paper: oklch(98% 0.006 85);
  --color-paper-2: oklch(95.5% 0.007 85);
  --color-paper-3: oklch(92.8% 0.008 85);
  --color-ink: oklch(19% 0.010 60);
  --color-muted: oklch(48% 0.012 60);
  --color-accent: oklch(50% 0.13 70);
  --color-accent-ink: oklch(98% 0.006 85);
  --color-cool: oklch(48% 0.13 245);
  --font-display: "Host Grotesk", ui-sans-serif, system-ui, sans-serif;
  --font-body: var(--font-display);
  --font-outlier: "Atkinson Hyperlegible Mono", ui-monospace, monospace;
  --radius-card: 10px;
  --radius-pill: 6px;
}
```

Spacing and fixed app typography use the scaffold's shared scale. Every colour and font is token-based. The outlier face is reserved for addresses, IDs, timestamps and measured/configured numeric data, never labels or controls. Fonts are bundled locally under SIL OFL licenses.

## Controls and states

- Amber primary actions, neutral secondary actions, 40px controls and 48px on coarse pointers.
- Sentence-case labels, visible instant focus, stable input borders, native disabled states.
- Keep every existing route, form field, API call, safety confirmation and test hook.
- Main regions expose loading, empty, error and full states. Success is the returned visible state.

## Motion

Still. Motion communicates a press or state change only. No load reveals, glow, chart animation or hover lift. Reduced motion disables transitions.

## Exports

Shared `tokens.css`, `base.css` and `style.css` live in `src/homelimiter/web/`. Hallmark provenance and review records live in `.hallmark/` and `docs/UI_REDESIGN.md`.
