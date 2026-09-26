from __future__ import annotations

import json

from ugc_flow.config import load_settings
from ugc_flow.mailer import check_pasted_link
from ugc_flow.runner import run_one


def _ask_link(email: str) -> str | None:
    while True:
        raw = input(f"Lien d'activation reçu pour {email} (vide = abandon) : ").strip()
        if not raw:
            return None
        url, why = check_pasted_link(raw, email)
        if url:
            return url
        print(f"Lien refusé : {why}")


def main() -> int:
    result = run_one(load_settings(), on_step=lambda s: print(f"... {s}", flush=True), ask_link=_ask_link)
    result.pop("password", None)
    result.pop("traffic", None)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
