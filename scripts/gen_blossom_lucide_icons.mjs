/**
 * Regenerate the ICONS block in assets/blossom-icons.js from Lucide (ISC).
 * Run: npm install && node scripts/gen_blossom_lucide_icons.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as lucide from "lucide";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const TARGET = path.resolve(__dirname, "..", "assets", "blossom-icons.js");

const MAP = {
  play: "Play",
  stop: "Square",
  refresh: "RefreshCw",
  search: "Search",
  pin: "Pin",
  gear: "Settings",
  chart: "BarChart3",
  clipboard: "ClipboardList",
  heart: "Heart",
  gem: "Gem",
  link: "Link",
  palette: "Palette",
  key: "KeyRound",
  target: "Target",
  robot: "Bot",
  map: "Map",
  sparkle: "Sparkles",
  pill: "Pill",
  fishing: "Fish",
  storefront: "Store",
  cart: "ShoppingCart",
  coins: "Coins",
  scroll: "ScrollText",
  dice: "Dice5",
  compass: "Compass",
  bolt: "Zap",
  flask: "FlaskConical",
  box: "Package",
  film: "Clapperboard",
  camera: "Camera",
  globe: "Globe",
  lock: "Lock",
  eye: "Eye",
  bell: "Bell",
  bag: "ShoppingBag",
  flower: "Flower2",
  gamepad: "Gamepad2",
  run: "PersonStanding",
  bulb: "Lightbulb",
  trophy: "Trophy",
  warning: "TriangleAlert",
  check: "CircleCheck",
  close: "X",
  monitor: "Monitor",
  megaphone: "Megaphone",
  window: "AppWindow",
  wrench: "Wrench",
  person: "User",
  location: "MapPin",
  keyboard: "Keyboard",
};

const SOLID = new Set(["play", "bolt", "heart"]);

function nodeToMarkup(node) {
  const [tag, attrs = {}] = node;
  const parts = Object.entries(attrs).map(([k, v]) => `${k}="${String(v).replace(/"/g, "&quot;")}"`);
  return `<${tag}${parts.length ? " " + parts.join(" ") : ""}/>`;
}

function innerFromLucide(name) {
  const nodes = lucide[MAP[name]];
  if (!nodes) throw new Error(`Missing Lucide icon for ${name} (${MAP[name]})`);
  return nodes.map(nodeToMarkup).join("");
}

const iconLines = ["  const ICONS = {"];
for (const name of Object.keys(MAP)) {
  const inner = innerFromLucide(name).replace(/\\/g, "\\\\").replace(/'/g, "\\'");
  const solid = SOLID.has(name) ? ", solid: true" : "";
  iconLines.push(`    ${name}: { p: '${inner}'${solid} },`);
}
iconLines.push("  };");

let src = fs.readFileSync(TARGET, "utf8");
const start = src.indexOf("  const ICONS = {");
const end = src.indexOf("\n  };", start) + 5;
if (start < 0 || end < 5) throw new Error("Could not find ICONS block");

src =
  src.slice(0, start) +
  iconLines.join("\n") +
  src.slice(end);

src = src.replace(
  /^\/\*[\s\S]*?\*\/\n\(function \(\) \{\n  "use strict";\n\n/,
  `/*
 * Blossom vector icons (Lucide, ISC).
 * Bundled locally — no CDN. Regenerate: node scripts/gen_blossom_lucide_icons.mjs
 */
(function () {
  "use strict";

`
);

fs.writeFileSync(TARGET, src);
console.log(`[gen] Wrote ${Object.keys(MAP).length} Lucide icons`);
