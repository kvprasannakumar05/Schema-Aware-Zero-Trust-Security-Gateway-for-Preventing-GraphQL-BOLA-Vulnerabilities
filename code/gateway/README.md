# BOLA Gateway

A security gateway that sits in front of a GraphQL backend and stops
**BOLA** (Broken Object Level Authorization) — a logged-in user reading or
changing objects that belong to someone else.

It is the "after" half of the project. It protects the VulnShop backend
without changing a single line of it.

## The idea in one paragraph

When it starts, the gateway reads the backend's schema **once** and works out,
on its own, which user owns each kind of object (the *control plane*). Then on
**every request** it normalises the query to strip disguises, walks every
object the query touches, and for anything fetched by id it checks the caller
really owns it — refusing the whole request if not (the *data plane*). The
backend never sees a request the caller isn't entitled to make.

---

## Files

| File | What it does |
|---|---|
| `inference.py` | **Control plane.** Reads the schema and builds the ownership map. |
| `normalizer.py` | Parses the query to a tree and strips disguises (fragments, aliases, variables, encoded IDs). Also counts depth/size and spots introspection. |
| `enforcer.py` | **Data plane.** Walks the query and checks ownership of each object. |
| `app.py` | The reverse proxy that wires it together and forwards allowed requests. |
| `config.py` | Settings — backend URL, port, limits, ownership words. |
| `LOGIC.md` | **How the logic works**, file by file, with worked traces. |

**Stack:** Python 3, FastAPI + Uvicorn (proxy), graphql-core (parsing),
httpx (talking to the backend). An in-memory cache stands in for Redis
(see the note at the end).

---

## How to run

The gateway protects the VulnShop backend, so start that first.

```bash
# terminal 1 — the backend
cd vulnshop
pip install -r requirements.txt
python app.py                 # runs on http://localhost:8000

# terminal 2 — the gateway
cd gateway
pip install -r requirements.txt
python app.py                 # runs on http://localhost:9000
```

Now **http://localhost:9000** is the protected entrance. Browse it as Goutham,
Kumar or Martin and the app works normally — you only ever see your own data.

When the gateway starts it prints the ownership map it worked out:

```
Ownership map (built from the schema):
  identity type: User
   - User  -> IDENTITY
   - Order -> OWNED ['owner', 'id']
   - Product -> PUBLIC
```

---

## Seeing it work

Goutham (`token-goutham`) owns order 101. Kumar owns 102, Martin owns 103.

**The attack is blocked through the gateway (port 9000):**

```bash
curl -s http://localhost:9000/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer token-goutham" \
  -d '{"query":"{ order(id:103){ shippingAddress } }"}'
# -> {"errors":[{"message":"not found"}]}
```

**The same attack still leaks if you go straight to the backend (port 8000):**

```bash
curl -s http://localhost:8000/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer token-goutham" \
  -d '{"query":"{ order(id:103){ shippingAddress } }"}'
# -> {"data":{"order":{"shippingAddress":"8 Bandra West, Mumbai 400050"}}}
```

That contrast is the whole demo: the gateway is what's doing the protecting.
(In a real deployment the backend only accepts traffic from the gateway, so
port 8000 wouldn't be reachable at all.)

**Legitimate access is untouched** — Goutham reading his own order is allowed:

```bash
curl -s http://localhost:9000/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer token-goutham" \
  -d '{"query":"{ order(id:101){ shippingAddress } }"}'
# -> {"data":{"order":{"shippingAddress":"14 Anna Nagar, Chennai 600040"}}}
```

His own order list passes through too, because `myOrders` names no id:

```bash
curl -s http://localhost:9000/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer token-goutham" \
  -d '{"query":"{ myOrders { id total shippingAddress } }"}'
# -> {"data":{"myOrders":[{"id":"101","total":1499.0, ... }]}}
```

---

## What it blocks (all of VulnShop's holes)

| VulnShop vulnerability | How the gateway stops it |
|---|---|
| BOLA — read another user's order/profile by id | Looks up the real owner and compares to the caller |
| Lateral BOLA — reach a stranger's email via a path | The id-bearing object the path starts at is checked, and one failure refuses the whole request |
| Mutation BOLA — edit another user's order | Ownership is checked *before* the write is forwarded |
| Alias enumeration — many objects in one request | Each object is checked on its own after normalising |
| ID hidden in a variable | Variables are substituted before checking |
| Encoded global ID (`base64("Order:103")`) | Decoded to the real id before checking |
| Introspection | Blocked at the gateway |
| Deep / oversized queries | Depth and field-count limits during the walk |

---

## How a request flows (what `app.py` does)

For the full walkthrough of each file's logic, see [LOGIC.md](LOGIC.md).

1. **Normalise** — parse to a tree, inline fragments, substitute variables,
   decode global IDs. Now we see the true query.
2. **Cheap checks** — block introspection, reject queries that are too deep or
   too large, require a valid token.
3. **Ownership** — for every object fetched by id, verify the caller owns it.
   The *rule* comes from the ownership map; the *fact* (who owns object 103)
   comes from a small probe to the backend, cached after the first time.
4. **Verdict** — one failure refuses the whole request with a uniform
   `"not found"`. Otherwise the original request is forwarded unchanged.

---

## Honest notes (worth saying in the review)

- **The cache is in-memory, not Redis.** For a single gateway instance this
  behaves identically. Redis matters when you run several gateway copies and
  they need to share the cache — a deployment detail, not a logic change.
- **Inference is a heuristic.** Here it resolves every type cleanly, but on an
  unusual schema some types would land in an `UNRESOLVED` tier and be
  **blocked by default** until a human confirms them. That fail-closed
  behaviour is deliberate.
- **The "anchored" fast-path** (trusting `me { ... }` without a probe) is a
  deliberate speed trade: it trusts the schema's structure, not live data.
