import json
import sys
from pathlib import Path

res = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
for x in res.get("traffic", []):
    print(f"{x['req']:<45} sent {x['sent']:>6}  recv {x['recv']:>7}")
print("TOTAL KB", res.get("proxy_kb"))
