import httpx

import config


INTROSPECTION = """
{
  __schema {
    queryType { name }
    mutationType { name }
    subscriptionType { name }
    types {
      kind
      name
      fields {
        name
        args { name }
        type { kind name ofType { kind name ofType { kind name ofType { kind name } } } }
      }
    }
  }
}
"""


def _named_type(type_ref):
    while type_ref and type_ref.get("name") is None and type_ref.get("ofType"):
        type_ref = type_ref["ofType"]
    return type_ref["name"] if type_ref else None


def _fetch_schema():
    resp = httpx.post(
        config.BACKEND_URL + "/graphql",
        json={"query": INTROSPECTION},
        timeout=10,
    )
    return resp.json()["data"]["__schema"]


def build_ownership_map():
    schema = _fetch_schema()
    query_type = schema["queryType"]["name"]
    mutation_type = schema["mutationType"]["name"] if schema.get("mutationType") else None

    object_types = {
        t["name"]: t
        for t in schema["types"]
        if t["kind"] == "OBJECT" and not t["name"].startswith("__")
    }

    fields = {}
    for name, t in object_types.items():
        fmap = {}
        for f in (t.get("fields") or []):
            arg_names = {a["name"] for a in (f.get("args") or [])}
            fmap[f["name"]] = {
                "return_type": _named_type(f["type"]),
                "has_id_arg": "id" in arg_names,
            }
        fields[name] = fmap

    root_types = {query_type, mutation_type}
    if schema.get("subscriptionType"):
        root_types.add(schema["subscriptionType"]["name"])
    data_types = [n for n in object_types if n not in root_types]

    identity = None
    for candidate in ("me", "viewer", "currentUser"):
        if candidate in fields.get(query_type, {}):
            identity = fields[query_type][candidate]["return_type"]
            break
    if identity is None:
        for guess in ("User", "Account", "Customer", "Member"):
            if guess in object_types:
                identity = guess
                break

    fetch_field = {}
    for fname, fdef in fields.get(query_type, {}).items():
        if fdef["has_id_arg"] and fdef["return_type"] in object_types:
            fetch_field.setdefault(fdef["return_type"], fname)

    ownership = {}
    for name in data_types:
        if name == identity:
            ownership[name] = {"tier": "IDENTITY"}
            continue

        path = _ownership_path(name, identity, fields)
        if path:
            ownership[name] = {
                "tier": "OWNED",
                "path": path,
                "fetch_field": fetch_field.get(name),
            }
        else:
            touches_user = any(
                fd["return_type"] == identity for fd in fields[name].values()
            )
            ownership[name] = {"tier": "UNRESOLVED" if touches_user else "PUBLIC"}

    return {
        "identity": identity,
        "query_type": query_type,
        "mutation_type": mutation_type,
        "fields": fields,
        "fetch_field": fetch_field,
        "ownership": ownership,
    }


def _ownership_path(type_name, identity, fields):
    for fname, fdef in fields[type_name].items():
        if fdef["return_type"] == identity and fname.lower() in config.OWNERSHIP_WORDS:
            return [fname, "id"]

    for fname in fields[type_name]:
        low = fname.lower()
        if low.endswith("id") and low[:-2] in config.OWNERSHIP_WORDS:
            return [fname]

    return None
