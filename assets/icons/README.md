# Blossom icons

The vector icons used across the UI live in `assets/blossom-icons.js` as inline
SVG (24x24, `currentColor` so they follow the active theme). They are bundled
locally — no CDN and no remote fonts, so the app works fully offline.

These are a small original line/solid set drawn for Blossom in the style of
Fluent UI System Icons (MIT). They are not copied from another set, so there is
nothing extra to attribute. If you ever swap in real Fluent UI System Icons,
keep their MIT license notice here.

`blossom-icons.js` also swaps the emoji the bundled React app still renders
(sidebar nav, card headers, a few toolbar buttons) for these SVGs, and exposes
`window.BlossomIcons.svg(name)` for the other local scripts to reuse.
