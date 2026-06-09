"""Patch bundled index.html: Appearance sidebar tab + page."""
from pathlib import Path

path = Path("assets/index.html")
s = path.read_text(encoding="utf-8")

NAV_OLD = (
    '{id:"stats",label:"Stats",icon:"📊"},'
    '{id:"otherfeatures",label:"Settings & extras",icon:"⚙️"}'
)
NAV_NEW = (
    '{id:"stats",label:"Stats",icon:"📊"},'
    '{id:"appearance",label:"Appearance",icon:"🎨"},'
    '{id:"otherfeatures",label:"Settings & extras",icon:"⚙️"}'
)

MAP_OLD = "otherfeatures:og,customization:mg,credits:ug,donations:rg"
MAP_NEW = "otherfeatures:og,appearance:wg,customization:mg,credits:ug,donations:rg"

PAGE_FN = (
    'function wg(){return n.jsxs(n.Fragment,{children:[n.jsxs("div",{className:"page-header",'
    'children:[n.jsx("h2",{children:"Appearance"}),n.jsx("p",{children:"Theme, colors, layout, window, and motion"})]})]})}'
)

SEARCH_OLD = (
    '{title:"Other Features",tab:"otherfeatures",keywords:["anti","afk","idle","reset character","glitch effect"]},'
    '{title:"Remote Access",tab:"remoteaccess"'
)
SEARCH_NEW = (
    '{title:"Appearance",tab:"appearance",keywords:["theme","accent","color","scale","window","motion","ui"]},'
    '{title:"Other Features",tab:"otherfeatures",keywords:["anti","afk","idle","reset character","glitch effect"]},'
    '{title:"Remote Access",tab:"remoteaccess"'
)

INSERT_BEFORE = "function og(){"

replacements = [
    (NAV_OLD, NAV_NEW, "nav item"),
    (MAP_OLD, MAP_NEW, "page map"),
    (SEARCH_OLD, SEARCH_NEW, "search index"),
]

for old, new, label in replacements:
    if old not in s:
        raise SystemExit(f"Missing patch anchor: {label}")
    s = s.replace(old, new, 1)

if INSERT_BEFORE not in s:
    raise SystemExit("Missing function og() anchor")
if "function wg()" in s:
    raise SystemExit("function wg() already exists")
s = s.replace(INSERT_BEFORE, PAGE_FN + INSERT_BEFORE, 1)

path.write_text(s, encoding="utf-8")
print("Patched index.html OK")
