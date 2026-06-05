import subprocess
from pathlib import Path

p = Path(__file__).resolve().parents[1]
text = subprocess.check_output(
    ["git", "show", "HEAD:assets/index.html"], cwd=p, text=True, errors="replace"
)
start = text.index('id="material-titlebar-enhancement"')
start = text.rfind("<script", 0, start)
end = text.index('id="local-ui-feature-enhancements"')
end = text.rfind("<script", 0, end)
snippet = text[start:end]
(p / "assets" / "_titlebar_snippet.html").write_text(snippet, encoding="utf-8")
print(len(snippet))
