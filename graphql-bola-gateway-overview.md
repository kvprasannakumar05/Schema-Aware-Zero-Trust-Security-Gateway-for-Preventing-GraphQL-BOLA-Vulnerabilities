# Schema-Aware Zero-Trust Security Gateway for GraphQL BOLA

**Project overview, status, and scope analysis**
As of 10 October 2026 · Group 7, 20CYS495, Phase I

---

## Contents

1. [First principles: how the hole gets made](#1-first-principles-how-the-hole-gets-made)
2. [The vulnerability in detail](#2-the-vulnerability-in-detail)
3. [Why it is still unsolved](#3-why-it-is-still-unsolved)
4. [What the system does](#4-what-the-system-does)
5. [What is genuinely new](#5-what-is-genuinely-new)
6. [Proposed additional features — honest triage](#6-proposed-additional-features--honest-triage)
7. [Where the project stands](#7-where-the-project-stands)
8. [Fix before the next review](#8-fix-before-the-next-review)

---

## 1. First principles: how the hole gets made

### 1.1 One endpoint instead of many

An API is the set of doors through which outside code asks a backend for data.

REST gives you many doors. `/users/5`, `/orders/124`, `/products/9`. Each door serves one fixed thing, the server decides what comes back, and the address itself announces what is being asked for.

GraphQL replaces all of them with one. You POST to a single `/graphql` endpoint with a query describing exactly which fields you want — from which object, and from which connected objects — and get back exactly that shape.

That single design choice is the origin of everything that follows, including the vulnerability.

### 1.2 The "graph" is a map, not a storage format

This is the single most misunderstood point, and it matters because the vulnerability lives in it.

Using GraphQL does **not** mean your data is stored as a graph. It still sits in ordinary relational tables, exactly as before. What the schema does is turn the silent number-links between those tables into **named paths you can walk**.

In the database:

```
users.id = 1
orders.owner_id = 1     ← a real link, but invisible: just a number in a column
```

In the schema:

```graphql
type User {
  name: String
  orders: [Order]       ← the same link, now a named, walkable edge
}

type Order {
  total: Float
  product: Product
  owner: User
}
```

The schema **is** the graph, written as text. Each field whose type is another object type is an edge.

### 1.3 A query is a traversal

Because the schema is a graph, a query is a path through it:

```graphql
{
  user(id: 1) {         # start at a User node
    name
    orders {            # walk the "orders" edge
      total
      product {         # walk the "product" edge
        name
      }
    }
  }
}
```

You start somewhere, follow connections, and pick up fields at each stop. One request, walking wherever the connections lead. Behind the scenes each "walk" is an ordinary database lookup, but the client never thinks about tables.

**This is the whole idea of GraphQL, and it is also the whole problem.**

### 1.4 Why REST moved here at all

Worth knowing, because a reviewer may ask why the industry adopted something with this flaw. REST had four real problems, and on mobile they hurt:

| Problem | What it means |
|---|---|
| Over-fetching | You ask for a name, you get thirty fields. You paid to download twenty-nine you did not want. |
| Under-fetching | User, then orders, then products = three sequential round trips, each waiting on the last. |
| Endpoint sprawl | Every new screen needs a slightly different mix, so the backend writes another endpoint. They pile up. |
| Versioning | Change something, break old clients, ship v2. v1 lives forever. |

Facebook hit all four building their mobile app in 2012. GraphQL genuinely fixes all four. That is why GitHub, Shopify, PayPal, Netflix, Airbnb and others adopted it. The flaw is a side effect of the fix, not a reason the fix was wrong.

---

## 2. The vulnerability in detail

### 2.1 The structural consequence

In REST, one call touches one object. The question "does this caller own it?" has one obvious place to live, and the URL tells any intermediary what is being requested.

In GraphQL, one request touches many objects along many paths. **Every single one of them needs the same question asked.**

GraphQL does not ask it. Not as a bug — by design. The specification is deliberately unopinionated about authorization and the official guidance pushes it into the business-logic layer. There is no default safety net.

So the check must be hand-written inside every resolver that loads an object. A real API has thousands of resolvers.

### 2.2 BOLA

**Broken Object-Level Authorization.** Ranked **#1 in the OWASP API Security Top 10 (API1:2023)**, a position it has held since 2019. Known as **IDOR** in the older web-application context — same root cause, different name.

The attack:

1. The attacker is a **real, logged-in user** with a valid account and a valid token. Authentication passes correctly.
2. They copy the query the site normally sends for their own data:
   `{ order(id: 124) { total shippingAddress } }`
3. They change one number:
   `{ order(id: 125) { total shippingAddress } }`
4. The resolver confirms *who they are*, then fetches order 125. **It never checks ownership.**
5. A stranger's data comes back. They script it — 1, 2, 3, 4 — and scrape every customer.

The attacker is not breaking in. They are a legitimate user abusing valid access.

**Authentication works. Authorization is what breaks.**

### 2.3 Why GraphQL amplifies it specifically

- One query traverses many nodes and edges, so one request touches many resolvers.
- **Each resolver that loads an object by ID is its own separate authorization checkpoint.** Missing the check on any single one creates a hole.
- The graph's interconnection creates **multiple traversal paths to the same node**. A developer guards the obvious route and forgets the sideways one.
- The frontend is not a boundary. The query is visible in DevTools, and anyone can skip the browser entirely with curl or Postman. The server cannot distinguish a request from the official frontend from one typed by hand.

### 2.4 Evidence it is real

- **107 confirmed BOLA reports** classified from bug bounty disclosures, 2021–2026 (Kaur taxonomy). GraphQL global IDs systematically exploited via decode → increment → re-encode.
- **Shopify** paid a **US$5,000** bounty for an IDOR on GraphQL billing queries (HackerOne #2207248).
- **Airline booking API, 2026.** An autonomous red-team agent started with nothing but a URL. It read client-side JavaScript, minted an anonymous session, mapped the schema, found unprotected resolvers, and confirmed mass extraction of a major airline's booking database — with read *and write* access over active itineraries. **Fifteen minutes, zero human guidance.**
- **Escape, 2023.** Scanned 1,500+ public endpoints, found 46,000+ issues reachable without logging in, ~10% critical, ~40% broken access control. Leaked data included passport details and cloud tokens.

**An important nuance for the viva.** A 2025 industry report found no GraphQL-specific breaches in one quarter — but attributed this to **detection gaps rather than safety**, because a single dynamic endpoint obscures visibility for traditional controls. The apparent silence is itself evidence for the problem.

**Accuracy note:** describe these as documented *vulnerabilities and disclosures* — responsible-disclosure findings, bounties, CVEs — not confirmed criminal breaches with public victim counts.

---

## 3. Why it is still unsolved

There are only three places this could be fixed, and each fails for a specific reason.

| Where | The approach | Why it fails |
|---|---|---|
| **Inside the backend** | Write the ownership check in every resolver. The official advice, and what everyone does. | Fails for a human reason, not a technical one. It requires a thousand developers to write a flawless check in a thousand places and never once forget. That is not a security strategy — it is a guarantee of eventual failure. |
| **At the perimeter** | A WAF or API gateway is the natural chokepoint. | A WAF reads flat text and URLs. GraphQL sends one nested POST to one address. The firewall cannot parse the structure, cannot see which objects are requested, and even if it could, has no idea who owns what. |
| **Before deployment** | GraphQLer, PrediQL, taint analysis, scanners. | They find real flaws — in a test lab. Nothing protects a running system, and any flaw the tester misses stays fully exploitable. |

### 3.1 The near misses

**Apollo GraphOS Router** does parse the query — it is the leading commercial GraphQL gateway with built-in authorization. But it enforces **roles and scopes**. It can answer *"does this user hold `read:profiles`?"* It cannot answer *"does this user own order 124?"* Expressing ownership as roles means one role per object — role explosion. It also requires schema directives, which means modifying the backend, and an Enterprise licence.

**Hasura** genuinely enforces row-level ownership (`{ "id": { "_eq": "X-Hasura-User-Id" } }`). But **Hasura is the backend**, not a gateway. It generates the API from the database, so it controls the query — that is the only reason it can enforce anything. You cannot put Hasura in front of an existing Node or Java GraphQL server. You would have to replace the server. And every rule is hand-configured per table.

**OPA** parses GraphQL to an AST and evaluates policy per request — but policies are hand-written in Rego, it normally runs inside the server, it does not undo alias or fragment disguises, and it does not look up ownership by itself.

### 3.2 The gap, in one line

> **Nobody enforces per-object ownership at the perimeter, in front of a backend they do not control.**

---

## 4. What the system does

A reverse proxy that sits in front of any existing GraphQL server, inspects every request, and blocks it if the caller does not own an object somewhere in the query. The backend does not know it exists.

It is a **gateway**, not a framework. A framework is something you build *with* — you import it and write code against it. A gateway runs *in front of* an app as a separate process. That distinction is what gives you **zero backend modification**.

It is **language-independent**, and this is part of the novelty. The gateway speaks HTTP and GraphQL, not Python function calls. The backend may be Node, Java, Go, Ruby or .NET. By contrast, resolver checks, directives and middleware libraries are language-locked — a GraphQL Shield rule only works in JavaScript. In an organisation running several services in several languages, one gateway protects all of them.

### 4.1 Architecture

```
┌──────────────── PHASE A — SETUP, runs once at startup ─────────────────┐
│                                                                        │
│   Backend schema  ──►  Ownership inference  ──►  Ownership map         │
│   SDL / registry /      identify user type,       high / medium /      │
│   introspection         score edges, trace        UNRESOLVED tiers     │
│                         indirect paths                      │          │
└─────────────────────────────────────────────────────────────┼──────────┘
                                                              │
                  ┌─────────────────┐                         │
                  │ Client request  │                         │
                  └────────┬────────┘                         │
                           ▼                                  │
┌──────────── PHASE B — GATEWAY, runs on every request ───────┼──────────┐
│                                                             │          │
│   1. NORMALISE                                              │          │
│      inline fragments, strip aliases, resolve variables,    │          │
│      decode global IDs, expand batches                      │          │
│                           ▼                                 │          │
│   2. WALK                                                   │          │
│      type-aware AST traversal, path stack, taint flag       │          │
│                           ▼                                 │          │
│   3. VERIFY  ◄──────────────────────────────────────────────┘          │
│      classify each node, check ownership (cache → probe)               │
│                           ▼                                            │
│   4. VERDICT                                                           │
│      one failure rejects everything                                    │
└──────────────┬──────────────────────────────┬──────────────────────────┘
               ▼                              ▼
   ┌────────────────────────┐    ┌────────────────────────┐
   │   Backend server       │    │      Rejected          │
   │ receives clean request │    │  returns "not found"   │
   └────────────────────────┘    └────────────────────────┘
```

The arrow from the ownership map into step 3 is the join between the two phases. **That single connection is essentially the whole contribution:** automatic rule generation feeding automatic per-object enforcement.

### 4.2 Phase A — inferring the rules

**Step 1 — Identify the identity type.** Three heuristics in priority order:

1. **The `me` / `viewer` / `currentUser` root field.** Its return type is the identity type. Strongest signal, because the semantics are unambiguous — GitHub literally uses `viewer`.
2. **JWT claim mapping.** If the token carries `sub` or `user_id`, find a type with a matching `id` format.
3. **Naming fallback.** A type named `User`, `Account`, `Member`, `Customer`.

**Step 2 — Build the type graph.** Nodes are object types. Edges are fields whose type is another object type, labelled with the field name and recording cardinality and nullability. `Order.owner: User!` becomes `Order --owner--> User`.

**Step 3 — Score ownership edges.**

| Signal | Description | Confidence |
|---|---|---|
| **Reverse containment** | The identity type has a field returning `T` (e.g. `User.orders`). Anything reachable by walking outward from the user is that user's by construction. | ~0.95 — strongest |
| **Direct identity reference** | A field returning the identity type with an ownership-lexicon name: `owner`, `author`, `creator`, `customer`, `assignee`, `createdBy`. | ~0.90 |
| **Scalar foreign key** | A field named `ownerId`, `userId`, `authorId`. Naming convention only, but directly comparable to the caller's ID. | ~0.60 |
| **Transitive path** | BFS toward the identity type following only edges above threshold. Confidence = product of edge confidences. | Decays with length |

**Step 4 — Emit the map in three tiers.**

```yaml
Order:
  ownership_path: [owner, id]
  confidence: 0.92
  source: direct_identity_reference

Comment:
  ownership_path: [post, author, id]
  confidence: 0.71
  source: transitive_path

Product:
  ownership_path: null
  confidence: 0.0
  status: UNRESOLVED
```

- **High (≥ 0.85)** → enforce automatically
- **Medium (0.5–0.85)** → enforce, but log and surface for confirmation
- **Unresolved / low** → **fail closed**, or report-only during onboarding

**The `UNRESOLVED` bucket is the most important design decision in the system.** Inference is heuristic, not sound — it will miss things. The claim is not "we infer everything perfectly." It is *"we infer the mechanical majority and formally surface the rest as a reviewable checklist."* That turns an invisible problem into a visible one. Lead with this honesty; claiming perfect inference is the fastest way to lose credibility.

**Step 5 — Resolving actual ownership at runtime.** Inference gives you the *rule*. You still need the *fact*.

| Option | How it works | Trade-off |
|---|---|---|
| **(a) Pre-flight probe** *(use this)* | The gateway issues its own minimal query along the ownership path — `{ order(id:125) { owner { id } } }` — with a privileged service token, and compares to the caller's JWT. | Uses the backend's own graph. No DB credentials, works with any language. Costs a round trip; needs a privileged credential. |
| **(b) Ownership cache** *(use this)* | Cache probe results in Redis as `owner:Order:125 → user_8` with a TTL. | High hit rate, since objects are queried repeatedly. Must invalidate on ownership-changing mutations. |
| **(c) Query rewriting** | Inject a filter so the backend returns only owned rows (the Hofer technique). | Only works if the schema exposes filter arguments. Cite as related work. |
| **(d) Response-time verification** | Let it run, then inspect and strip the response. | **Unacceptable for mutations** — the side effect already happened. Defence-in-depth for queries only. |

**Decision: (a) + (b). For mutations, always probe before forwarding.**

### 4.3 Phase B — enforcing them

**Step 1 — Normalise.** Non-negotiable. You cannot analyse a query you cannot see clearly.

- **Fragment inlining** — replace every fragment spread with its selection set, recursively, including inline fragments. Add cycle detection.
- **Alias canonicalisation** — analyse under real field names. Detect alias multiplication (`a: order(id:1) b: order(id:2) c: order(id:3)`) — one request enumerating three objects, each needing its own check. This is the Directus CVE-2024-39895 class.
- **Variable resolution** — resolve `$x` against the `variables` JSON. **Skipping this bypasses the entire defence**, because real clients send IDs as variables by default.
- **Batch expansion** — the body may be a JSON array of operations, and a document may hold several.
- **Identifier normalisation** — handle `id:`, `ids: [..]`, `where: {id:}`, `filter: {}`, and decode Relay global IDs (base64 `Type:id`).

**Step 2 — Schema-aware traversal.** Walking the AST alone is insufficient; you must know what type each field returns. A field named `owner` is meaningless without knowing whether you are inside `Order` or `Comment`. In `graphql-core`, `TypeInfo` combined with `visit()` maintains type context as the visitor descends.

Maintain two structures during the walk: a **path stack** (`[viewer, orders, product, reviews]`) and an **ownership taint flag**.

**Step 3 — Classify every node.**

| Classification | Meaning | Action |
|---|---|---|
| **Anchored** | Path starts at `me`/`viewer` and every edge traversed was an ownership edge. Owned by construction. | No check. **This is the performance optimisation** — most legitimate traffic is anchored. |
| **Unanchored ID fetch** | A client-supplied ID names an object directly (`order(id: 125)`). | Must verify. Classic BOLA lives here. |
| **Lateral / back-reference** | Walking back up to a user or across into another user's data (`order.owner.email`). | Must verify. This is the "guarded one path, forgot another" failure. |
| **Collection** | Returns a set (`orders(first: 100)`). | Fine if anchored. A global root collection needs an enforced filter or denial. |

**Step 4 — Taint propagation.** The subtlest part, and the easiest to get wrong.

- Start: `tainted = true` at `me`/`viewer`, `false` at any other root field.
- Traversing an **ownership edge** → taint **preserved**.
- Traversing into a **shared/global type** (e.g. `Product`) → taint **dropped**.
- Traversing a **back-reference to an identity type** → taint **dropped**, node flagged lateral.
- Any node with `tainted == false` requesting a non-public field → **verify explicitly**.

Why this matters — consider `viewer → orders → product → reviews → author → email`. Your order is yours, but the *product* is shared. Without taint-dropping, an attacker anchors at `viewer`, hops through a shared object, and walks into a stranger's data while still appearing anchored. Structurally the same idea as taint analysis in program security (connecting to Lambers et al., ICGT 2024) — except applied **at runtime on the live request path**.

**Step 5 — Compose the verdict.**

- **Any single node fails → reject the entire request.** No partial execution, no field stripping — partial responses leak which objects exist.
- **Return a uniform error** — "not found", never "forbidden". Revealing that an object exists but is not yours is itself a disclosure. Same response for nonexistent objects, unowned objects, and unresolved types.
- **Emit a structured audit record** — node, path, object ID, rule fired, decision.
- **Forward the original request**, not the normalised one. The client expects its aliases honoured; normalisation was for analysis only.

### 4.4 The security-critical ordering

**Normalisation must fully complete before the walk.** If it misses anything — one fragment form, unresolved variables, undecoded global IDs — every later phase analyses the wrong query and the gateway is bypassable.

**Concentrate your testing effort there.** It is the single point where the whole system fails silently.

### 4.5 Handling disabled introspection

Disabling introspection in production is standard advice, so the gateway must work without it.

| Option | Description |
|---|---|
| **SDL at deploy time** *(primary)* | The schema exists as a file in the backend repo. A CI/CD hook pushes it to the gateway on deploy. Better than introspection: works regardless of settings, available before traffic flows, and solves schema drift properly. |
| **Private introspection** | Introspection is disabled for *untrusted external clients*. The backend can permit it specifically from the gateway by IP allowlist or service token. |
| **Gateway as introspection boundary** | The elegant inversion: the backend keeps introspection on internally, and the **gateway blocks all introspection from outside**. A limitation becomes a feature, and it demos well. |
| **Schema registry** | In federated setups the schema already lives centrally. Pull from there. |

Implement this as a pluggable **schema source** interface. Small abstraction, deployable anywhere, and a credible answer when a reviewer asks.

---

## 5. What is genuinely new

State it narrowly, or a reviewer will take it apart:

> **Deriving ownership rules from the structure of the schema itself.**

Policy mining is a mature field — but every established approach derives rules from data that does not exist at deployment:

| Information source | Used by | Available to us? |
|---|---|---|
| Access logs | Karimi et al., most policy mining | **No.** A new system has none. Worse, logs record what users *did* do, so an existing BOLA flaw is learned as normal, permitted behaviour. |
| Existing ACLs | Bottom-up policy mining | **No.** Circular — assumes the policy we are trying to create. |
| Written specifications | LLM-based policy generation | **No.** Such documents rarely exist in practice. |
| **The schema's type structure** | **No prior work found** | **Yes.** Always available, via SDL or introspection. |

The four stated contributions:

1. **Automatic ownership inference from schema structure** — genuinely unexplored. **Lead with this one.**
2. **Multi-path ownership verification** — checking every node along every traversal path, with taint propagation. Existing tools check the object fetched, not the routes taken to reach it.
3. **Obfuscation-resistant normalisation** — aliases, fragments, variable-carried IDs and encoded global IDs resolved before policy evaluation.
4. **Zero backend modification** — deterministic, at the perimeter, language-independent.

Contributions 2–4 are strong engineering, but they are combinations of known techniques. Contribution 1 is the one that is actually new.

### What not to claim

- Do **not** say the problem is unknown or undiscovered.
- Do **not** say no gateway does GraphQL authorization — Apollo disproves it instantly.
- Do **not** claim perfect inference.
- Do **not** claim broad coverage of injection, business logic, or rate limiting. *(See section 6.)*

The defensible sentence: *"Gateways today enforce roles and scopes. Ownership enforcement exists only inside backend engines such as Hasura, which must replace the backend. No standalone gateway infers and enforces per-object ownership across an existing backend."*

---

## 6. Proposed additional features — honest triage

You raised four: DoS prevention, DDoS prevention, rate limiting, and injection protection. They are not equivalent. One is free, one is worth building, one is a credibility risk, and one mostly cannot work at the perimeter.

### 6.1 Application-layer DoS — **free, take it**

These all fall out of the AST pass you are already paying for. Once you are walking the tree, counting things costs almost nothing.

| Defence | How | Where it fits |
|---|---|---|
| **Depth limit** | Count nesting during the walk; abort past a cap. | Normalisation pass |
| **Complexity / cost cap** | Assign a cost per field, sum, cap the total. | Normalisation pass |
| **Alias amplification cap** | `a: x b: x c: x` × 1000 — the Directus CVE-2024-39895 class. | Already counted for BOLA |
| **Fragment cycle detection** | Self-referencing fragments crash the parser. | Must do anyway |
| **Batch operation cap** | Hundreds of operations in one JSON array. | Pre-parse, on the body |
| **Pagination abuse** | `first: 999999999`. | Capped during the walk |
| **Directive abuse** | Duplicate `@skip`/`@include` to confuse parsing. | Validate counts |
| **Introspection blocking** | Attacker downloads the whole schema. | Cheap rejection, before parsing |

**Claim these.** They are real, they are defensible, and your context document already scopes them correctly as "free wins already in the pipeline." They also make the gateway robust against being crashed itself, which is a question a reviewer will ask.

### 6.2 DDoS — **do not claim this**

This is the one that will cost you marks if you put it on a slide.

**Distinguish two different things:**

- **Application-layer DoS** — one expensive query exhausts the server. Covered above. Yours.
- **Volumetric DDoS** — a botnet floods you with traffic at the network and transport layer. **Not yours, and cannot be.**

Volumetric DDoS is handled at layers 3 and 4 by CDNs, scrubbing providers and load balancers — Cloudflare, AWS Shield, Akamai. A Python/FastAPI gateway operates at layer 7, after the connection is already established and the body already received.

**Worse: your gateway makes volumetric DDoS slightly harder, not easier.** It is an additional hop that does more work per request than the backend's router does. Under a flood, *the gateway falls over first*. Adding an inspection layer in front of a backend increases the attack surface for resource exhaustion unless it sits behind a CDN.

**If asked in the viva, say this:** *"We defend application-layer denial of service through query cost analysis, which is the GraphQL-specific form. Volumetric DDoS is a network-layer concern handled upstream by CDN and scrubbing infrastructure, and we explicitly do not claim it. In deployment our gateway would sit behind such a layer."*

That answer is strictly better than claiming DDoS protection, because it demonstrates you understand the layer boundaries.

### 6.3 Rate limiting — **build it, but only the GraphQL-specific form**

The naive version is worthless here, and understanding *why* is the valuable part.

**Why per-request rate limiting fails for GraphQL.** Standard rate limiting counts HTTP requests per IP per minute. GraphQL breaks this completely: one HTTP request can contain hundreds of operations, or one operation can contain hundreds of aliased object fetches. An attacker using the CrackQL technique packs a thousand BOLA attempts — iterating account IDs 1000 to 1999 — into a **single HTTP request**. Your rate limiter sees one request and waves it through.

**The correct form: cost-based and object-count-based budgeting.**

You are already computing a complexity score for DoS defence. Reuse it. But add the one that matters for your project specifically:

> **Distinct-object budgeting.** Count how many discrete objects of the same type a single query attempts to access. A legitimate query asks for a handful. A query touching 500 distinct `Order` IDs is enumeration, not use.

This is worth building for a reason that is not about rate limiting at all: **it directly defends your primary contribution.** Batched BOLA is the attack that defeats per-object checking by volume — even if every check works, 1000 checks in one request at scale is a resource attack on your own gateway. Capping object count per request closes that.

**Implementation:** Redis sliding window keyed on the JWT subject. Cost function over depth, breadth, distinct object count and alias count. Budget per user per window, not per IP per request.

### 6.4 Stateful cross-request detection — **the one you are missing, and it is good**

Your `novelty.md` mentions this and your `context.md` does not. It should be in both.

Standard gateways are stateless — they evaluate one request at a time. But horizontal enumeration has an obvious signature across requests:

```
User B requests User A's order   → ownership check fails, blocked
User B requests User C's order   → fails, blocked
User B requests User D's order   → fails, blocked
                                 ↑
                    This is not three mistakes. This is an attack campaign.
```

A Redis counter on authorization failures per JWT, with a threshold and a temporary block, converts your system from *"we blocked a request"* to *"we detected and stopped an attacker."*

**Why this is worth your time specifically:**

- It is cheap — a counter and a threshold.
- It demos brilliantly. A single blocked request is an unexciting slide. A live graph of an attacker's enumeration attempt being detected at request 4 and the token blacklisted at request 10 is memorable.
- It produces evaluation data: time-to-detection, requests-before-block.
- It is a natural extension of the ownership check, not a bolt-on from another domain.

Of everything on your list, **this is the addition I would actually prioritise.**

### 6.5 Injection — **mostly cannot work at the perimeter, and here is exactly why**

The gateway sees:

```graphql
{ search(term: "'; DROP TABLE users--") { id } }
```

It has no idea whether the resolver behind `search`:

- parameterises it (safe — blocking this is a false positive)
- concatenates it into SQL (vulnerable)
- passes it to MongoDB, where the syntax is entirely different
- uses it as a filename, making this path traversal, not SQL injection
- does not use it at all

**The gateway cannot know, because the vulnerability lives in code it cannot see.** This is irreducible, not an engineering gap.

Pattern-matching for SQL keywords at the perimeter is the classic signature-based WAF approach, and it fails in both directions: a documentation site where someone legitimately searches for "drop table" gets blocked, while a real attacker bypasses the filter with encoding, comments or case variation. **This is precisely the failure mode the Perera et al. paper you already cite describes** — it states plainly that static analysis, rate limiting and general WAFs give limited protection. Do not reinvent the thing your own literature survey criticises.

**What you *can* honestly do on input safety:**

| Defence | Why it works at the perimeter |
|---|---|
| **Schema-derived type and format validation** | The schema declares `id: ID!`. If the ID arrives as `"1 OR 1=1"`, that is not a valid ID for this API, regardless of what the resolver does with it. |
| **Custom scalar enforcement** | If the schema declares `EmailAddress` or `UUID`, validate the format against it. |
| **Argument length caps** | A 50 KB string into a `name: String` field is not legitimate input. |
| **Egress error sanitisation** | Catch backend errors, strip stack traces, field hints and `"Did you mean secretField?"` suggestions, return a generic error. |

Note what the first row actually is: **deriving an input-validation rule from the schema.** That is the same idea as your core contribution, applied to a second problem. It is defensible precisely *because* it comes from the schema rather than from a signature list.

**Egress sanitisation deserves separate mention.** It does not stop injection, but it removes the feedback channel that blind injection and schema enumeration depend on. It also makes the gateway bidirectional, which is architecturally tidy — you inspect ingress and egress at one chokepoint. Cheap, honest, and it closes the "server leaks schema even with introspection off" hole.

**The honest claim:** *"schema-derived input shape validation and error sanitisation"* — never *"injection prevention."*

### 6.6 The strategic warning

Each feature you add dilutes the claim. There is a question that kills this project if you are not ready for it:

> *"So is this a BOLA gateway, or a general GraphQL WAF? Because general GraphQL WAFs already exist — Inigo, Escape — and they are better funded than you are."*

**The framing that survives it** is already written in your `context.md` §12, and you should keep it verbatim:

> *"Object-ownership enforcement is the primary contribution. Because the gateway already performs full AST normalisation and traversal, a set of structural defences are enforced in the same pass at negligible additional cost. Injection, business-logic and data-layer concerns remain out of scope by design, as they require backend semantics the perimeter cannot observe."*

That sentence does three things at once: it names one contribution, it justifies the extras as free rather than as separate claims, and it pre-empts the scope question by declaring the boundary yourself.

### 6.7 Summary and priority

| Feature | Verdict | When |
|---|---|---|
| Depth / complexity / alias / batch limits | **Free — take it.** Already in the AST pass. | With the normaliser, Step 4 |
| Introspection blocking | **Free — take it.** Cheap rejection. | With the proxy, Step 3 |
| Distinct-object budgeting | **Build it.** Defends the core contribution against batched BOLA. | After the ownership check works |
| Cross-request enumeration detection | **Build it — highest value of the additions.** Cheap, demos well, produces metrics. | After the ownership check works |
| Egress error sanitisation | **Build it.** Cheap, honest, closes a real hole. | Any time after the proxy |
| Schema-derived input validation | **Optional.** Defensible, but secondary. | Only if time allows |
| Per-user cost-based rate limiting | **Basic version only.** Doing it properly is its own project. | Only if time allows |
| Volumetric DDoS protection | **Do not claim.** Wrong layer. | Never |
| Signature-based injection detection | **Do not build.** Reinvents the thing your survey criticises. | Never |

**One caution on timing.** It is October, the Month 4 demo is due, and no code exists yet *(section 7)*. Every item above is a distraction until the core works. Build the ownership check first. These are Month 5–6 work.

---

## 7. Where the project stands

**The design work is well beyond typical Phase I depth. The build has not started.**

### Done, and done well

- Literature survey across six areas — foundations, real-world security, detection, enforcement, policy automation, industry tools. Every entry carries a **limitation** column, which is the part most student surveys skip.
- Threat model grounded in real, verifiable disclosures.
- Problem statement, stated consistently.
- Novelty claim, correctly narrowed to schema-structure inference.
- Full system architecture, with the framework-vs-gateway and language-independence distinctions worked out.
- Technical design down to confidence scores, taint-propagation rules and the UNRESOLVED tier.
- Scope and limitations declared up front — a strength, not a weakness.
- Review 1 deck and viva preparation.

Section 10 of the context document could be handed to an engineer and built from as it stands.

### Not evidenced anywhere

No code. No vulnerable test API, no proxy, no normaliser, no inference engine, no attack suite, no measurements.

### The timeline problem

The Gantt chart places proxy, parser, normaliser and inference v1 in Months 3–4, with **DEMO 1 at Month 4 — October 2026**. The review materials date from late July.

If nothing has been built since, the build track is roughly **six to eight weeks behind**, and the Month 4 demo is the milestone at risk. This is the single most urgent thing in this document.

### Still undecided

All three boxes unticked on your own verification checklist:

- [ ] OPA as policy engine, or pure Python — this changes the software requirements list
- [ ] Test backend: Strawberry/Ariadne (Python) or Apollo Server (Node)
- [ ] Every arXiv ID and DOI verified; the BOLA taxonomy reference (arXiv:2605.25865) flagged as unverified

### What to build first

In this order, because each unblocks the next:

1. **Vulnerable test API** — a small GraphQL backend, a few users, a deliberate BOLA hole
2. **Prove the attack** — log in as A, swap the ID, read B's data. This is your "before" state and your demo opening.
3. **Bare proxy** — intercept and forward unchanged, nothing clever. Proves requests flow through.
4. **Query normaliser** — fragments, aliases, variables, global IDs
5. **Ownership inference engine** — schema in, type graph, scored edges, map out
6. **The ownership check** — the centrepiece, where the novelty lives
7. Everything in section 6

**Steps 1–3 are a weekend.** They also buy you a demo even if the clever parts are unfinished, because *"here is the leak, here is the block"* is the entire story a reviewer needs to see. Do not let the design document keep growing instead.

---

## 8. Fix before the next review

### Three internal inconsistencies

- [ ] **Gap count does not match across documents.** `context.md` lists 6 gaps. Review-1 Slide 5 lists 7 and claims you address 1–6. The Literature Survey says "five of the six." Pick one numbering and use it everywhere — and note that Slide 5's gap 7 (*no layer removes disguises first*) **is** your contribution 3, so you are currently under-claiming your own work.
- [ ] **`script.md` says "two hundred reports, eighty-four confirmed cases."** Every other document says 107 reports. Fix the script before you present it.
- [ ] **Duplicate citation link.** In the Literature Survey, the AMW 2017 and WWW 2018 Hartig & Pérez entries both point to the same WWW 2018 preprint URL.

### The hardest question, and it is not in your viva prep

> *"Your 'anchored' optimisation skips the ownership check when a query starts at `viewer` and follows only ownership edges. But that trusts the backend's `viewer.orders` resolver to be correct. If that resolver is itself buggy and returns everyone's orders, your gateway waves it straight through. How is that zero-trust?"*

It is a fair hit, and your project title contains the words "Zero-Trust."

**The honest answer:** anchoring trusts *schema structure*, not *runtime fact*. It is a deliberate performance trade — most legitimate traffic is anchored, and verifying it would mean a probe per object on every normal request.

**Have a position ready before you are asked.** Either:

- defend the trade-off explicitly, and **measure what full enforcement would cost** so the number is in your back pocket; or
- add a **sampling mode** that spot-checks a percentage of anchored paths, giving you detection without the full cost.

The second option is cheap to build and turns a weakness into a design feature. Either way, do not get asked this cold.

### Other questions worth rehearsing

| Question | Answer |
|---|---|
| *"Why not just fix the resolvers?"* | A real API has thousands. Expecting every developer to never once forget is not a security strategy. |
| *"How is this different from Apollo?"* | Apollo checks roles and scopes, not ownership, and requires schema directives — backend modification. |
| *"Hasura does row-level ownership."* | Hasura **is** the backend. It enforces ownership because it generates the SQL. You cannot put it in front of an existing Node or Java server. |
| *"Isn't automatic policy generation solved?"* | Policy mining is mature, but every approach needs logs, ACLs or specs — none available at deployment, and logs encode existing flaws as legitimate. Schema topology is unexplored. |
| *"What if introspection is disabled?"* | SDL supplied at deploy time via CI/CD hook. The gateway can also act as the introspection boundary. |
| *"Isn't REST more secure?"* | No — same flaw, called IDOR. REST's URLs reveal intent, giving a natural chokepoint. GraphQL's single endpoint destroys that; our gateway restores it. |
| *"What about persisted queries?"* | They eliminate arbitrary queries but **do not solve BOLA** — a legitimate persisted query with a swapped ID is still BOLA. |

### The strongest sentence to say out loud

> *"It enforces object-ownership, not just field-level filtering, which is what actually makes it a BOLA defence rather than a generic query firewall."*

This signals real understanding of the problem, and it is the distinction most students building a "GraphQL security" project get wrong.

---

## Appendix — Ethical and legal note

**Never test BOLA or authorization flaws against systems you do not own** or lack written permission to test. Probing a live `/graphql` endpoint with modified IDs constitutes unauthorised access and is illegal in most jurisdictions, including under India's IT Act.

**For attack testing, use:** your own deliberately vulnerable backend, DVGA (Damn Vulnerable GraphQL Application), PortSwigger Web Security Academy labs, or HackTheBox/TryHackMe sandboxes.

**For learning query syntax only,** public playgrounds are fine: Countries API (`countries.trevorblades.com`), Rick & Morty API, GitHub's official explorer (which returns only your own authorised data).

The distinction: use public APIs to **learn how queries look**; use your own vulnerable instance to **test attacks**.
