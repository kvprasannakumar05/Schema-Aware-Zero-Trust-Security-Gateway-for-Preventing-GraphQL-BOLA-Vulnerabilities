import time

import httpx

import config


class Decision:
    def __init__(self, allowed, reason=""):
        self.allowed = allowed
        self.reason = reason


_caller_cache = {}
_owner_cache = {}


def enforce(operations, token, model):
    caller = _caller_id(token)
    if caller is None:
        return Decision(False, "no valid identity")

    for op in operations:
        for node in _walk(op["roots"]):
            decision = _check(node, token, caller, model, op["operation"])
            if not decision.allowed:
                return decision
    return Decision(True)


def _walk(nodes):
    for n in nodes:
        yield n
        yield from _walk(n.children)


def _check(node, token, caller, model, operation):
    object_id = node.args.get("id")
    if object_id is None:
        return Decision(True)

    return_type = _return_type(node.name, model, operation)
    if return_type is None:
        return Decision(True)

    info = model["ownership"].get(return_type)
    if info is None:
        return Decision(False, "unknown type")

    tier = info["tier"]

    if tier == "PUBLIC":
        return Decision(True)

    if tier == "UNRESOLVED":
        return Decision(False, "ownership unresolved")

    if tier == "IDENTITY":
        return Decision(str(object_id) == str(caller), "not your account")

    fetch_field = info.get("fetch_field") or model["fetch_field"].get(return_type)
    if fetch_field is None:
        return Decision(False, "cannot resolve owner")
    owner = _probe_owner(fetch_field, object_id, info["path"], token)
    return Decision(str(owner) == str(caller), "not your object")


def _return_type(field_name, model, operation):
    type_name = model["query_type"] if operation == "query" else model["mutation_type"]
    field = model["fields"].get(type_name, {}).get(field_name)
    return field["return_type"] if field else None


def _cache_get(store, key):
    entry = store.get(key)
    if entry is None:
        return False, None
    value, expires_at = entry
    if time.time() >= expires_at:
        del store[key]
        return False, None
    return True, value


def _cache_put(store, key, value):
    store[key] = (value, time.time() + config.CACHE_TTL_SECONDS)


def _caller_id(token):
    hit, value = _cache_get(_caller_cache, token)
    if hit:
        return value
    data = _backend_query("{ me { id } }", token).get("me")
    caller = data["id"] if data else None
    if caller is not None:
        _cache_put(_caller_cache, token, caller)
    return caller


def _probe_owner(fetch_field, object_id, path, token):
    key = (fetch_field, str(object_id))
    hit, value = _cache_get(_owner_cache, key)
    if hit:
        return value

    selection = "id"
    for step in reversed(path[:-1]):
        selection = step + " { " + selection + " }"
    query = "{ %s(id: \"%s\") { %s } }" % (fetch_field, object_id, selection)

    data = _backend_query(query, token).get(fetch_field)
    owner = _dig(data, path)
    if owner is not None:
        _cache_put(_owner_cache, key, owner)
    return owner


def _dig(data, path):
    cur = data
    for step in path:
        if cur is None:
            return None
        cur = cur.get(step)
    return cur


def _backend_query(query, token):
    resp = httpx.post(
        config.BACKEND_URL + "/graphql",
        json={"query": query},
        headers={"Authorization": "Bearer " + token},
        timeout=10,
    )
    return resp.json().get("data") or {}
