import sys
from pathlib import Path

d = Path(sys.argv[1])
for p in sorted(d.glob("*.html")) + sorted((d / "join").glob("*.html")):
    t = p.read_text(encoding="utf-8")
    size = len(t.encode())
    csrf = 'name="_csrf"' in t
    print(f"{str(p.relative_to(d)):<35} {size:>7} B  csrf={csrf}")
