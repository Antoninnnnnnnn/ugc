import json
import sys
from datetime import date
from pathlib import Path

from ugc_flow.config import load_settings
from ugc_flow.fidelity import FID_BASE, fid_points
from ugc_flow.profile import Person
from ugc_flow.session import UgcSession
from ugc_flow.signup import _login

run_dir = Path(sys.argv[1])
c = json.loads((run_dir / "credentials.json").read_text(encoding="utf-8"))
p = Person(c["email"], c["password"], c["first_name"], c["last_name"], date.fromisoformat(c["birth"]), "", "", "")
s = load_settings()
with UgcSession(s.ugc_base, s.proxy_source, run_dir / "verify") as sess:
    _login(sess, s, p)
    r = sess.get(f"{FID_BASE}/catalogue-cadeaux.html", "catalogue")
    print(c["email"], "->", r.url, "points:", fid_points(r.text))
