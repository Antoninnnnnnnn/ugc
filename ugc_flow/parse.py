from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

SKIP_FORM_IDS = {
    "previewSearchForm",
    "enterSearchForm",
    "j_spring_security_check_form",
    "forgotForm",
    "resendForm",
}


@dataclass
class FormField:
    name: str
    tag: str
    type: str
    value: str
    required: bool
    checked: bool
    options: list[str] = field(default_factory=list)


@dataclass
class HtmlForm:
    action: str
    method: str
    form_id: str
    fields: list[FormField]

    def as_dict(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for f in self.fields:
            if not f.name:
                continue
            if f.tag == "input" and f.type == "checkbox" and not f.checked:
                continue
            out[f.name] = f.value
        return out


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _field_from_tag(el: Tag) -> FormField | None:
    name = el.get("name")
    if not name:
        return None
    tag = el.name.lower()
    typ = (el.get("type") or "").lower()
    if tag == "textarea":
        value = el.get_text() or ""
    elif tag == "select":
        selected = el.find("option", selected=True) or el.find("option")
        value = selected.get("value", "") if selected else ""
    else:
        value = el.get("value") or ""
    options: list[str] = []
    if tag == "select":
        options = [o.get("value") or "" for o in el.find_all("option") if o.get("value") is not None]
    raw_req = el.get("required")
    required = el.has_attr("required") and str(raw_req).lower() not in ("false", "0", "no")
    required = required or el.get("aria-required") == "true"
    checked = el.has_attr("checked")
    return FormField(
        name=str(name),
        tag=tag,
        type=typ,
        value=str(value),
        required=required,
        checked=checked,
        options=options,
    )


def parse_forms(html: str, base: str) -> list[HtmlForm]:
    doc = soup(html)
    forms: list[HtmlForm] = []
    for form in doc.find_all("form"):
        fid = form.get("id") or ""
        action = form.get("action") or ""
        method = (form.get("method") or "get").lower()
        fields: list[FormField] = []
        for el in form.find_all(["input", "select", "textarea"]):
            f = _field_from_tag(el)
            if f:
                fields.append(f)
        forms.append(
            HtmlForm(
                action=urljoin(base + "/", action),
                method=method,
                form_id=str(fid),
                fields=fields,
            )
        )
    return forms


def inscription_forms(html: str, base: str) -> list[HtmlForm]:
    out = []
    for form in parse_forms(html, base):
        if form.form_id in SKIP_FORM_IDS:
            continue
        names = {f.name for f in form.fields}
        if form.form_id == "redirect_form" or form.form_id == "inscription_form":
            out.append(form)
            continue
        if any(n.startswith("inscriptionBean.") for n in names):
            out.append(form)
            continue
        if "monCompteInscription" in form.action:
            out.append(form)
    return out


def hidden_csrf(html: str) -> str | None:
    doc = soup(html)
    el = doc.find("input", {"name": "_csrf"})
    if el and el.get("value"):
        return str(el.get("value"))
    return None


def text_error_field(html: str) -> str:
    doc = soup(html)
    node = doc.find(id="errorField")
    if node:
        return re.sub(r"\s+", " ", node.get_text(" ", strip=True))
    return re.sub(r"\s+", " ", doc.get_text(" ", strip=True))[:800]


_ERROR_HINTS = (
    "déjà",
    "invalide",
    "incorrect",
    "erreur",
    "obligatoire",
    "jetable",
    "utilisé",
    "existe",
    "format",
    "refus",
)


def email_validation_ok(html: str) -> tuple[bool, str]:
    text = text_error_field(html).lower()
    if not text.strip():
        return True, ""
    if any(h in text for h in _ERROR_HINTS):
        return False, text
    # Ajax fragment can be a script that submits redirect_form
    if "redirect_form" in html.lower() or "hidden_email" in html.lower():
        return True, text
    if "error" in html.lower() and "color--pink" in html.lower():
        return False, text
    # Non-empty but no error keywords: treat as warning, allow continue
    return True, text


def looks_like_login(html: str, url: str) -> bool:
    if "login.html" in url:
        return "j_spring_security_check" in html
    return False


def struts_errors(html: str) -> list[str]:
    doc = soup(html)
    found: list[str] = []
    for node in doc.select(".errorMessage, .alert-danger, span.error, .fieldError, .invalid-feedback, p.color--pink"):
        t = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
        if t:
            found.append(t)
    for m in re.findall(r"Invalid field value for field [^\.<]+", html):
        found.append(m.replace("&quot;", '"'))
    return list(dict.fromkeys(found))
