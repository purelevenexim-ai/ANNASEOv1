import re


def parse_error_py(detail):
    if not detail:
        return {"title": "Strategy Failed", "items": ["Unknown error"]}
    raw = str(detail)
    parts = [p.strip() for p in raw.split(";") if p.strip()]

    items = []
    for p in parts:
        if re.search(r"persona", p, re.I):
            items.append("Add at least 1 Customer Persona")
        elif re.search(r"product", p, re.I):
            items.append("Add at least 1 Product")
        else:
            items.append(p)

    return {"title": "Strategy Failed", "items": items}


def test_parse_error_mapping():
    s = "At least one persona is required; At least one product is required."
    out = parse_error_py(s)
    assert out["title"] == "Strategy Failed"
    assert "Add at least 1 Customer Persona" in out["items"]
    assert "Add at least 1 Product" in out["items"]
