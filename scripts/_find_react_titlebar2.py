from pathlib import Path

text = (Path(__file__).resolve().parents[1] / "assets" / "index.html").read_text(
    encoding="utf-8", errors="replace"
)
idx = text.find("window-frame ${")
if idx < 0:
    idx = text.find("window-frame")
print("idx", idx)
print(text[idx : idx + 3000])
