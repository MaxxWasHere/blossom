import subprocess
from pathlib import Path

p = Path(__file__).resolve().parents[1]
text = subprocess.check_output(
    ["git", "show", "HEAD:assets/index.html"], cwd=p, text=True, errors="replace"
)
start = text.index("    .window-frame {")
end = text.index("    .sidebar-nav {")
snippet = text[start:end]
(p / "assets" / "_window_snippet.css").write_text(snippet, encoding="utf-8")
print(len(snippet))
