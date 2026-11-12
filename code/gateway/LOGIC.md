# How the gateway works

This explains the logic inside the three files that do the real work:
`normalizer.py`, `inference.py` and `enforcer.py`, plus how `app.py` puts them
in order.

---

## The problem being solved

VulnShop authenticates correctly — it always knows *who* is calling — but it
never checks whether the caller **owns** the object they asked for. So
`order(id:103)` returns Martin's order no matter who asks. That is BOLA
(Broken Object Level Authorization).

The gateway fixes this from the outside, without editing the backend. To do
that it has to answer one question on every request:

> For each object this query names by id, does the caller own that object?

Answering it needs two different kinds of knowledge, and that split is the whole
design:

| Question | Kind of knowledge | Where it comes from | How often |
|---|---|---|---|
| "How is an `Order` owned?" | a **rule** about a type | `inference.py` reads the schema | once, at startup |
| "Who owns order 103?" | a **fact** about one object | `enforcer.py` probes the backend | per request, cached |

The rule layer is the **control plane**. The fact layer is the **data plane**.

---

## The shape of a request

```
POST /graphql
     |
     |  app.py
     v
 [1] parse the JSON body
 [2] normalizer.normalize()        query text  ->  clean tree
 [3] cheap structural checks       introspection? too deep? too large? token?
 [4] enforcer.enforce()            walk the tree, check every id
     |                                  |
     |                                  +-- consults the ownership map (inference.py)
     |                                  +-- probes the backend for owners
     v
 [5] forward the ORIGINAL body to the backend, unchanged
```

Nothing is forwarded until every check has passed, so a refused request is
never half-applied. Structural failures name their cause (`introspection is
disabled`, `query too deep`, `authentication required`). Every **authorization**
outcome instead returns the same `not found`, for the reason in section 4.

---

# 1. `normalizer.py` — see what was really asked

### Why this exists

You cannot check a query you cannot clearly read. GraphQL gives an attacker
several ways to write the *same* request so it does not look like itself:

```graphql
query($v: ID!) {
  harmless: order(id: $v) { ...bits }
}
fragment bits on Order { shippingAddress }
```

That asks for an order, but the field is renamed `harmless`, the id is not in
the query text at all (it is in the variables), and the selected fields are
hidden behind a fragment. A naive string check sees nothing suspicious.

So before any security decision, the query is rebuilt into one plain shape.

### The output format

Everything becomes a tree of [`Node`](normalizer.py#L6) objects — three fields
only:

```python
class Node:
    name      # the REAL field name, alias discarded
    args      # arguments, variables already substituted
    children  # nested fields, fragments already inlined
```

[`normalize()`](normalizer.py#L14) returns a list of operations, one per
operation in the document:

```python
[{"operation": "query", "roots": [Node, Node, ...]}]
```

### What gets stripped, and where

| Disguise | What the attacker writes | How it is removed | Code |
|---|---|---|---|
| **Alias** | `harmless: order(id:103)` | only `sel.name.value` is read; the alias is never stored | [L34](normalizer.py#L34) |
| **Variable** | `order(id: $v)` + `{"v":"103"}` | the variable is looked up in `variables` and replaced by its value | [L67-L69](normalizer.py#L67) |
| **Fragment** | `...bits` | the fragment's selections are spliced in where the spread was | [L37-L43](normalizer.py#L37) |
| **Inline fragment** | `... on Order { ... }` | selections are lifted out of the wrapper | [L44-L45](normalizer.py#L44) |
| **Encoded global id** | `id: "T3JkZXI6MTAz"` | base64-decoded; if it looks like `Type:id`, the real id is taken | [L79-L86](normalizer.py#L79) |
| **Fragment cycle** | `fragment a` spreads `a` | tracked in `seen_fragments`; raises instead of looping forever | [L39-L40](normalizer.py#L39) |

Note the id decoding only triggers when the value really is base64 of
`something:id` — [`_decode_global_id`](normalizer.py#L79) returns the value
untouched on any failure, so a plain `"103"` stays `"103"`. (VulnShop uses plain
ids, so this matters for Relay-style APIs rather than for VulnShop itself, but
the gateway does not know that in advance.)

### Worked example

Request:

```json
{
  "query": "query($a: ID!, $b: ID!){ x:order(id:$a){ ...f } y:order(id:$b){ ...f } } fragment f on Order { shippingAddress }",
  "variables": { "a": "101", "b": "T3JkZXI6MTAz" }
}
```

Normalised to:

```
operation: query
  Node(name="order", args={"id": "101"})
      Node(name="shippingAddress")
  Node(name="order", args={"id": "103"})      <- decoded from base64
      Node(name="shippingAddress")
```

Both aliases are gone, both ids are plain numbers, the fragment is inlined
twice. Now the enforcer sees two ordinary `order` lookups and can judge each.

### Three extra checks it provides

The same tree is cheap to measure, so three helpers live here:

- [`contains_introspection()`](normalizer.py#L102) — true if any field name
  starts with `__`. Catches `__schema` and `__type` wherever they are hiding,
  including inside a fragment, because the tree is already flattened.
- [`count_fields()`](normalizer.py#L106) — total node count, compared with
  `MAX_FIELDS`.
- [`max_depth()`](normalizer.py#L110) — deepest nesting, compared with
  `MAX_DEPTH`.

---

# 2. `inference.py` — work out the rules from the schema

### Why this exists

The lazy way to configure a gateway is to hand-write a rule per type:
"an Order is owned via `owner.id`, a Review via `authorId`, ...". That does not
scale and it rots as the schema changes.

Instead this file **reads the backend's schema and derives the rules**. It runs
**once**, at startup, from [`lifespan`](app.py#L39).

### Step 1 — fetch the schema

[`_fetch_schema()`](inference.py#L32) sends the trimmed introspection query at
[the top of the file](inference.py#L6). It asks for only what is needed to
reason about ownership: every type, its fields, each field's argument *names*,
and what each field returns.

Note this is the gateway talking to the backend at startup, not a client
request: the gateway introspects once so that your callers never have to.

Return types are wrapped in GraphQL (`Order!`, `[Order!]!`), so
[`_named_type()`](inference.py#L26) peels off the `NON_NULL` / `LIST` wrappers
until it reaches the real name.

### Step 2 — build a field index

[L52-L61](inference.py#L52) flattens the schema into:

```python
fields["Order"]["owner"] = {"return_type": "User", "has_id_arg": False}
fields["Query"]["order"] = {"return_type": "Order", "has_id_arg": True}
```

`has_id_arg` is the important flag: a field taking an `id` argument is a field
that can be pointed at someone else's object.

### Step 3 — find the identity type

Which type represents "the logged-in user"? [L68-L77](inference.py#L68) looks
for a root field called `me`, `viewer` or `currentUser` and takes whatever it
returns. For VulnShop, `me: User` means **identity = `User`**.

If none of those exist it falls back to guessing by name (`User`, `Account`,
`Customer`, `Member`).

### Step 4 — find how to fetch each type by id

[L79-L82](inference.py#L79) records, for each type, a root query field that
fetches it by id:

```python
fetch_field = {"Order": "order", "User": "user"}
```

The enforcer needs this later: to learn who owns order 103 it must know that
`order(id:)` is the way to ask for an Order.

### Step 5 — classify every type into a tier

[L84-L101](inference.py#L84) walks every non-root object type and assigns one of
four tiers:

| Tier | Meaning | How it is decided |
|---|---|---|
| `IDENTITY` | this *is* the user type | the type equals the identity type |
| `OWNED` | belongs to one user, reachable by a path | [`_ownership_path()`](inference.py#L113) found a path |
| `PUBLIC` | shared data, nobody owns it | no path **and** the type never mentions the user type |
| `UNRESOLVED` | cannot tell | no path **but** the type does mention the user type |

`UNRESOLVED` is the **fail-closed** tier. If a type looks user-related but the
gateway could not work out the rule, it is blocked rather than guessed at.

### How `_ownership_path` decides

[`_ownership_path()`](inference.py#L113) tries two signals, strongest first:

1. **A link to the user type with an owner-ish name** —
   `Order.owner: User`, and `"owner"` is in
   [`OWNERSHIP_WORDS`](config.py#L12). Path: `["owner", "id"]`.
2. **A scalar foreign key** — a field named `ownerId`, `userId`, `authorId`:
   ends in `id` and the prefix is an ownership word. Path: `["ownerId"]`.

The path is a list of steps to follow from the object to its owner's id. It is
used two ways by the enforcer: to *build* a probe query, and to *read* the
answer out of the response.

### What this produces for VulnShop

The map printed at startup:

```
identity type: User
 - User    -> IDENTITY
 - Order   -> OWNED ['owner', 'id']
 - Product -> PUBLIC
```

Read it as: a User is owned by being that user; an Order is owned by whoever
`order.owner.id` says; a Product is not owned by anyone, so anyone may read it.
Nothing about this was hand-written — it was all read off the schema.

---

# 3. `enforcer.py` — check this caller against these objects

### The entry point

[`enforce()`](enforcer.py#L18) does three things:

```python
caller = _caller_id(token)          # who is asking?
if caller is None: refuse           # unknown token -> stop
for every node in every operation:  # check each object
    if not allowed: return the failure immediately
```

[`_walk()`](enforcer.py#L31) is a recursive generator yielding every node in the
tree, parents and children alike, so a field buried deep in a query is checked
the same as one at the top.

**First failure wins.** One unowned object refuses the entire request — the
query is never partially executed.

### Who is the caller?

[`_caller_id()`](enforcer.py#L89) asks the backend `{ me { id } }` with the
caller's own token. This is the one thing the backend is trusted for:
authentication works, so whatever `me` returns really is the caller.

### The decision ladder

For each node, [`_check()`](enforcer.py#L37) walks down these rules in order:

| # | Condition | Decision | Why |
|---|---|---|---|
| 1 | node has no `id` argument | **allow** | it does not name a specific object, so it cannot be a BOLA attempt. `myOrders` and `me` pass here |
| 2 | field name unknown in the schema | **allow** | the backend will reject it anyway; not the gateway's job |
| 3 | return type not in the map | **refuse** `unknown type` | fail closed |
| 4 | tier is `PUBLIC` | **allow** | shared data, e.g. a Product |
| 5 | tier is `UNRESOLVED` | **refuse** `ownership unresolved` | fail closed |
| 6 | tier is `IDENTITY` | **allow only if** `id == caller` | you own a user record by being that user |
| 7 | tier is `OWNED` | **probe the real owner, allow only if it equals the caller** | the actual BOLA check |

Rule 1 is why the gateway does not get in the way of normal use: safe fields
like `myOrders` carry no id, so they are waved through and the backend's own
resolver does the filtering.

### The probe

For `OWNED` types, [`_probe_owner()`](enforcer.py#L100) turns the ownership path
into a question for the backend. With path `["owner", "id"]` and object `103` it
builds the selection inside-out — [L106-L109](enforcer.py#L106):

```
"id"                    (start at the last step)
"owner { id }"          (wrap in the step before it)
```

giving:

```graphql
{ order(id: "103") { owner { id } } }
```

The answer comes back as `{"order": {"owner": {"id": "3"}}}`, and
[`_dig()`](enforcer.py#L118) follows the same path to pull out `"3"`.

Then [L65](enforcer.py#L65): `"3" == "1"`? No → `not your object` → refused.

The same path string both *writes* the question and *reads* the answer, which is
why a path is a list and not a hand-written query.

### The caches

Two module-level dicts, each entry stored as `(value, expires_at)`:

| Cache | Key | Value | Set at |
|---|---|---|---|
| `_caller_cache` | token | caller's user id | [L96](enforcer.py#L96) |
| `_owner_cache` | (fetch field, object id) | owner's user id | [L114](enforcer.py#L114) |

[`_cache_get()`](enforcer.py#L74) deletes and reports a miss once
`CACHE_TTL_SECONDS` has passed, so the gateway re-probes periodically instead of
trusting a snapshot forever. Without the TTL, reassigning an object's owner in
the database would leave the gateway refusing the new owner access to their own
data until it was restarted.

Only non-`None` values are cached ([L95](enforcer.py#L95),
[L113](enforcer.py#L113)) so a failed lookup is never remembered as "nobody owns
this".

These are in-memory. With several gateway instances they belong in Redis so all
copies share them; for one instance the behaviour is identical.

---

# 4. `app.py` — the order of the checks

[The pipeline](app.py#L54) is deliberately ordered cheapest-first:

| Order | Check | Cost | Why here |
|---|---|---|---|
| 1 | `MODEL is None` | free | never serve traffic without rules |
| 2 | body is JSON and a dict | free | avoid crashing on junk input |
| 3 | `normalize()` | parse only | everything below needs the tree |
| 4 | introspection | tree scan | reject before spending any network call |
| 5 | depth, field count | tree scan | cap the work an attacker can cause |
| 6 | token present | header read | no point probing without one |
| 7 | `enforce()` | **network calls** | the expensive check runs last |
| 8 | forward | network call | only reached by a fully approved request |

Step 7 is wrapped in `try/except` at [L84-L87](app.py#L84): if anything throws
mid-check — backend down, malformed answer — the request is refused, not
allowed. Fail closed.

The forwarded request at [L91-L100](app.py#L91) is the caller's **original
body**, untouched, with their own token. The gateway decides *whether* a request
runs; it does not rewrite *what* runs.

### Why every refusal says "not found"

[`_refuse()`](app.py#L149) returns the same message for "does not exist", "not
yours" and "could not decide". If they differed, an attacker could tell real ids
from fake ones by the error text and map out the database without reading a
single record.

---

# 5. Two end-to-end traces

### Blocked: Goutham reaches for Martin's order

```graphql
{ order(id:103){ shippingAddress owner { email } } }
```

```
normalize   -> Node(order, {id:"103"}) with children shippingAddress, owner>email
introspect  -> no __ fields            ok
depth       -> 3                        <= 10, ok
fields      -> 4                        <= 100, ok
token       -> "token-goutham"          present
enforce
  _caller_id            -> backend { me { id } }          -> "1"   (cached 30s)
  node order, id=103
    _return_type        -> Query.order returns "Order"
    tier                -> OWNED, path ["owner","id"]
    _probe_owner        -> backend { order(id:"103"){ owner { id } } } -> "3"
    "3" == "1"?         -> NO
  Decision(False, "not your object")
refuse      -> {"errors":[{"message":"not found"}]}
```

The `owner { email }` part is never even examined — the walk returned on the
first failure, and nothing was forwarded. That is also why the "lateral" attack
(reaching a stranger's email *through* an order) fails: the path starts at an
object the caller does not own, and refusing that root refuses everything hanging
off it.

### Allowed: Martin lists his own orders

```graphql
{ myOrders { id total shippingAddress } }
```

```
normalize   -> Node(myOrders) with three children
checks      -> no introspection, depth 2, 4 fields, token present
enforce
  _caller_id -> "3"
  node myOrders -> args has no "id"  -> allow (rule 1)
  children      -> no "id" either    -> allow
  Decision(True)
forward     -> original body + Authorization: Bearer token-martin
backend     -> SELECT * FROM orders WHERE owner_id = 3
```

The gateway adds no filtering of its own here. It confirmed the request names no
specific object, then let the backend's own `myOrders` resolver scope the rows.

---

# 6. Honest limits

Worth knowing, and worth saying out loud rather than being caught by:

1. **Nested id-bearing fields are resolved against the root type.**
   [`_return_type()`](enforcer.py#L68) always looks the field name up on `Query`
   or `Mutation`. In VulnShop only root fields take an `id`, so this is exact;
   on a schema where a *nested* field takes an `id`, a type-aware walk would be
   needed to get its true parent type.
2. **The probe uses the caller's own token.** It works because the backend is
   vulnerable and will answer questions about anyone's order. Against a
   partly-fixed backend the probe would return `null`, the comparison would fail
   and the gateway would refuse — safe, but it would block legitimate access.
   A production version would use a service credential for probes.
3. **Inference is a heuristic.** It depends on conventional naming
   (`owner`, `ownerId`, `me`). An unconventional schema lands types in
   `UNRESOLVED`, which blocks them until a human adds the word to
   [`OWNERSHIP_WORDS`](config.py#L12). Blocking is the correct failure
   direction, but it is a failure that needs attention.
4. **Caches are per-instance and time-based.** Ownership changes are picked up
   within `CACHE_TTL_SECONDS`, not instantly. An event-driven invalidation would
   be sharper.
5. **`ALLOW_INTROSPECTION` is a real switch.** Turning it on for GraphiQL
   autocomplete gives up the introspection defence. Ownership is still enforced,
   but the schema becomes readable by any authenticated caller.
