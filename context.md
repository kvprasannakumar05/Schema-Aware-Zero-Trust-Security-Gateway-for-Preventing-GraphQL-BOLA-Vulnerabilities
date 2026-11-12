# Schema-Aware Zero-Trust Security Gateway for Preventing GraphQL BOLA Vulnerabilities

**Course:** 20CYS495 — Project Phase I
**Group:** Group 7, B.Tech Cyber Security, Amrita Vishwa Vidyapeetham (TIFAC-CORE)
**Batch:** 2023–2027
**Members:** CB.SC.U4CYS23013, CB.SC.U4CYS23014, CB.SC.U4CYS23025, CB.SC.U4CYS23054

---

## Table of Contents

1. [Why This Project Was Selected](#1-why-this-project-was-selected)
2. [Background: Understanding GraphQL](#2-background-understanding-graphql)
3. [The Vulnerability: BOLA](#3-the-vulnerability-bola)
4. [Problem Statement](#4-problem-statement)
5. [How Developers Handle Authorization Today](#5-how-developers-handle-authorization-today)
6. [Literature Survey](#6-literature-survey)
7. [Research Gaps](#7-research-gaps)
8. [Novelty — Our Contribution](#8-novelty--our-contribution)
9. [System Architecture](#9-system-architecture)
10. [Detailed Technical Design](#10-detailed-technical-design)
11. [Complete Request Flow](#11-complete-request-flow)
12. [Other Vulnerabilities Covered](#12-other-vulnerabilities-covered)
13. [Implementation Plan](#13-implementation-plan)
14. [Hardware and Software Requirements](#14-hardware-and-software-requirements)
15. [Expected Outcomes](#15-expected-outcomes)
16. [Scope and Limitations](#16-scope-and-limitations)
17. [Real-World Relevance](#17-real-world-relevance)
18. [Viva Preparation](#18-viva-preparation)
19. [Resume Entry](#19-resume-entry)

---

## 1. Why This Project Was Selected

Four projects were shortlisted. They were assessed on novelty, implementation difficulty, real-world relevance, and whether they solve a genuine problem.

| Project | Novel | Difficulty | Real-world | Verdict |
|---|---|---|---|---|
| 1. Linux Persistence Detection | Medium | Medium | High | Strong backup, but provenance-based detection is a crowded area and risks becoming "a log parser that tags events with ATT&CK IDs". |
| 2. Serverless Memory Acquisition | Low | Medium | Very high | AWS already publishes this exact pipeline (EventBridge → Lambda → SSM → LiME → S3). Would need repositioning around forensic integrity or container forensics. |
| **3. GraphQL BOLA Gateway** | **Good** | **Medium** | **Very high** | **Selected.** |
| 4. Runtime SSRF Defense | Medium | Low | High | Too easy; a validating outbound proxy is a well-trodden pattern. |

**Reasons for selecting Project 3:**

- It is genuinely novel once extended with object-ownership enforcement.
- It is correctly sized — one well-defined component that can actually be finished and demonstrated, not a sprawling cloud pipeline.
- It addresses the #1 ranked API security risk, so relevance is unambiguous.
- It demonstrates well in a review: send a malicious query, watch the gateway strip the disguise, catch the violation, and drop the request.

**The critical correction made during selection.** The original proposal described *field-level* filtering — removing unauthorised fields. That is technically a different vulnerability (BFLA, Broken Function Level Authorization). It does **not** stop the classic BOLA case where the field is public but the *object* belongs to someone else. The project was therefore re-centred on **object-ownership enforcement**, which is what actually makes it a BOLA defence.

---

## 2. Background: Understanding GraphQL

### 2.1 What GraphQL Is

- A query language for APIs, created at Facebook in 2012 by Lee Byron, Nick Schrock, and Dan Schafer.
- Open-sourced in 2015; governance moved to the neutral GraphQL Foundation in 2018.
- Unlike REST, which exposes many endpoints, GraphQL exposes **one single endpoint** (usually `/graphql`).
- The **client** specifies exactly which fields it wants; the server returns exactly that shape.

### 2.2 GraphQL vs REST

| Aspect | REST | GraphQL |
|---|---|---|
| Endpoints | Many, one per resource. | One single endpoint. |
| Who picks the data | Server decides. | Client asks for exact fields. |
| Over-/under-fetching | Common. | Avoided. |
| Multiple resources | Several requests. | One nested request. |
| Schema/typing | None built-in. | Strongly typed schema. |
| Caching | Easy (HTTP caching). | Harder (single endpoint). |
| Firewall visibility | High (attacks visible in URLs). | Low (hidden in one POST body). |
| Best for | Simple, predictable APIs. | Complex, client-driven data. |

### 2.3 Clearing Up the "Graph" Confusion

This is the single most misunderstood point, and it matters for the project.

- **Using GraphQL does not mean the data is stored as a graph.** The data still lives in ordinary database tables.
- The "graph" refers to how data is **connected and queried**, not how it is stored.
- The relationships already exist in the tables as matching ID numbers (for example, `orders.owner_id = 1` points to `users.id = 1`).
- The **schema** is the map that turns those silent number-links into walkable connections.
- A query is therefore a **path through that graph**: start at one object, follow the connections, take what you need.

**Two views of the same data:**

- *Stored form* — flat tables linked by matching ID numbers (unchanged by GraphQL).
- *GraphQL's view* — connected nodes you can walk along.

**Important distinction for the viva:** a graph *database* (such as Neo4j, using Cypher) genuinely stores data as nodes and edges. That is about **storage**. GraphQL is about the **API layer** and usually sits on top of ordinary tabular databases. Do not conflate them.

### 2.4 Key GraphQL Terminology

**Structure:**

| Term | Meaning |
|---|---|
| **Schema** | The rulebook defining every type, field, and connection. Nothing exists in the API unless the schema declares it. |
| **Type** | A category of thing with a defined shape (`User`, `Order`, `Product`). |
| **Field** | A single piece of information on a type. Fields pointing to other types are the graph's edges. |
| **Scalar** | The simple leaf values that cannot be broken down: `Int`, `Float`, `String`, `Boolean`, `ID`. |

**The three operations:**

| Operation | Purpose |
|---|---|
| **Query** | A read. Fetches data without changing anything. |
| **Mutation** | A write. Creates, updates, or deletes. Runs strictly in sequence, unlike queries. |
| **Subscription** | A live feed. The server pushes updates over a persistent connection. |

Simple way to remember: **Query reads, Mutation writes, Subscription listens.**

**Execution:**

| Term | Meaning |
|---|---|
| **Resolver** | The function behind each field that fetches its value, usually by querying the database. Every field has one. |
| **Root types** | `Query`, `Mutation`, `Subscription` — the three "front doors". Every request must begin at one of these. They define the complete attack surface: if an operation is not listed as a root field, it cannot be invoked. |

**Inside a query:**

| Term | Meaning | Example |
|---|---|---|
| **Argument** | Extra input narrowing a field down. | `user(id: 5)` |
| **Variable** | A placeholder passed separately from the query text. IDs usually arrive this way. | `user(id: $id)` with `id = 5` |
| **Alias** | Renames a field in the response; also allows requesting the same field twice. | `myName: name` |
| **Fragment** | A reusable named bundle of fields. | `fragment basicInfo on User { name email }` |
| **Directive** | An instruction attached to a field, written with `@`. | `@skip`, `@include`, custom `@auth` |

**Relationships:**

| Term | Meaning |
|---|---|
| **Interface** | Shared fields that several types all promise to have. |
| **Union** | "This result could be one of several types." |
| **Input type** | A type used for sending data into a mutation. |
| **`!` and `[]`** | `!` means never empty; `[]` means a list. |

**Tooling:**

| Term | Meaning |
|---|---|
| **Introspection** | GraphQL's ability to describe itself. Powers autocomplete — and hands attackers a complete map, so it is often disabled in production. |
| **Playground / GraphiQL** | In-browser query editor built on introspection. |
| **Endpoint** | The single URL all requests go to, usually `/graphql`. |

### 2.5 How a Query Is Actually Executed

The pipeline is fixed: **Request → Lexing → Parsing (AST) → Validation → Execution → Response.**

- **Stage 0 — Request arrives.** An HTTP POST to `/graphql` with a JSON body containing `query`, `variables`, and optionally `operationName`. Variables arrive separately from the query text — a crucial security detail.
- **Stage 1 — Lexing.** The query string is broken into tokens (braces, field names, literals).
- **Stage 2 — Parsing.** Tokens are assembled into an **Abstract Syntax Tree (AST)** — a structured tree of `Document`, `OperationDefinition`, `Field`, `Argument`, and `SelectionSet` nodes. **This is the stage our gateway hooks into.**
- **Stage 3 — Validation.** The AST is checked against the schema: do the fields exist, are arguments correctly typed, are fragments valid. **Standard validation does not check authorization** — that gap is where BOLA lives.
- **Stage 4 — Execution.** Resolvers run, walking the tree top-down. Each resolver receives four arguments:
  - `parent` — the value returned by the parent field's resolver.
  - `args` — the field's arguments, **where object IDs appear**.
  - `context` — shared per-request object holding the **authenticated user**.
  - `info` — metadata about the current field and execution path.
- **Stage 5 — Response.** Results are assembled into JSON mirroring the query's shape, with `data` and optionally `errors`. Partial results are normal.

**Additional execution details:**

- Fields at the same level resolve in parallel; **top-level mutation fields run strictly in sequence** because writes must not race.
- The **N+1 problem** occurs because each field resolves independently; **DataLoader** batches and caches to fix it.
- **Null propagation** — if a non-null field errors, the null bubbles up to the nearest nullable parent.

### 2.6 How a Button Click Becomes a Query

Users never type GraphQL. The flow is:

1. The developer writes the query as a string inside the frontend code, ahead of time.
2. The user clicks a button, firing an event handler.
3. The handler sends that pre-written query as an HTTP POST to `/graphql`, with the user's token in the `Authorization` header.
4. The server runs the pipeline and returns JSON.
5. The frontend renders that JSON into visible HTML.

**The security consequence, and the foundation of this project:**

- The query is visible to anyone via browser DevTools.
- Anyone can **skip the frontend entirely** and POST directly to `/graphql` using curl, Postman, or any HTTP tool.
- The server **cannot distinguish** a request from the official frontend from one an attacker typed by hand.
- Therefore **the frontend is never a security boundary**. Hiding a button removes the option from honest users only.
- All authorization must happen server-side or at a perimeter gateway, treating every request as potentially hand-crafted.

---

## 3. The Vulnerability: BOLA

### 3.1 Definition

- **BOLA** — Broken Object-Level Authorization.
- Ranked **#1 in the OWASP API Security Top 10 (API1:2023)**, a position it has held since 2019.
- The system verifies **who you are** (authentication) but not **whether you may access this specific object** (authorization).
- Known as **IDOR** (Insecure Direct Object Reference) in the older web-application context. Same root cause, different name.

### 3.2 The Attack, Step by Step

1. The attacker is a **real, logged-in user** with a valid account and valid token. Authentication passes correctly.
2. They copy the query the site normally sends for their own data: `{ order(id: 124) { total shippingAddress } }`.
3. They change one number: `{ order(id: 125) { total shippingAddress } }` — an order belonging to someone else.
4. The server's resolver confirms who they are, then fetches order 125. **It never checks ownership.**
5. A stranger's data is returned. The attacker scripts it — 1, 2, 3, 4 — and scrapes every customer's private data.

**The key insight:** the attacker is not breaking in. They are a legitimate user abusing valid access.

### 3.3 Where BOLA Lives in the Graph

- **Nodes** = objects (a specific user, a specific order), fetched by resolvers.
- **Edges** = relationships, traversed by resolvers.
- **BOLA** = any resolver that loads an object by ID without verifying the requester is authorised for that specific object.

**Why GraphQL amplifies it:**

- One query traverses many nodes and edges, so one request touches many resolvers.
- **Each resolver that loads an object by ID is its own separate authorization checkpoint.**
- Missing the check on any single one creates a hole.
- The graph's interconnection creates **multiple traversal paths** to the same sensitive node, so an attacker may reach protected data sideways through an unguarded route.

---

## 4. Problem Statement

> GraphQL APIs cannot reliably prevent an authenticated user from accessing data objects belonging to other users, because the required ownership check is scattered across thousands of backend resolvers where it is routinely omitted. Existing perimeter defences cannot compensate, as they are unable to interpret GraphQL's nested query structure or the alias and fragment obfuscation used to disguise such requests.

**Supporting points:**

- **Why the current fix does not work.** The only real defence is that developers manually write an ownership check inside every resolver. A real API has thousands. Expecting every developer to write a flawless check in thousands of places and never forget once is not a security strategy — it is a guarantee of eventual failure.
- **Why existing perimeter defences cannot cover for it.** Traditional WAFs read flat text and URLs. GraphQL sends everything as one nested POST to a single endpoint, and attackers further disguise requests using aliases and fragments. The firewall cannot read the query structure, cannot see which objects are requested, and cannot distinguish an ownership violation from a normal request.
- **The gap.** No perimeter defence currently (a) understands GraphQL query structure, (b) strips alias and fragment disguises, and (c) verifies that a specific user may access a specific object — before the request reaches the backend.

---

## 5. How Developers Handle Authorization Today

### 5.1 Techniques Currently Used

- **Inline resolver checks** — an `if` statement inside each resolver. Official guidance flags this as suitable only for prototypes.
- **Field-level checks / returning null** — hiding individual fields from unauthorised users.
- **Schema directives** — declarative annotations such as `@auth(requires: ADMIN)` or `@hasRole`.
- **Middleware layers** — schema-wide rule engines such as GraphQL Shield.
- **External policy engines** — OPA, Oso, Cerbos, or Zanzibar-style ReBAC systems (SpiceDB, OpenFGA).
- **Query cost and depth limits** — protects availability, not object access.

### 5.2 Flaws in These Strategies

- **Only checks login, not ownership** — the system confirms the user is logged in, then assumes they may access anything they ask for.
- **Treats "having the ID" as "allowed to see it"** — if a request asks for `id: 125`, the server returns it without checking who owns object 125.
- **The check must be added at every level of a query** — one request touches many objects, so forgetting the check on even one leaks data.
- **Only some routes to an object are protected** — objects are reachable through multiple paths; developers guard one and forget another.
- **Assumes the schema itself provides security** — designing the schema is not enforcing access.
- **Rules differ across services** — in microservice setups, the same object is checked differently or not at all by different teams.
- **Trusts the frontend to hide data** — attackers bypass the frontend and call the API directly.
- **Role-based tools cannot express ownership** — RBAC and directives handle "admin vs user" well but need endless extra roles to answer "does this user own this object?"
- **Policy engines must be constantly fed ownership data** — OPA and ReBAC only know who owns what if every relationship is continuously synced into them.
- **Scanners cannot detect it** — BOLA is a logic flaw, not a bad input, so automated tools miss it; it only shows up at runtime.
- **Relies on humans never making a mistake** — correct protection needs every developer to add the right check in thousands of places and never once forget.

### 5.3 Why This Keeps Happening

- **The specification deliberately offloads it.** GraphQL is unopinionated about authorization; official guidance pushes it into the business-logic layer. There is no default safety net.
- **It is a logic flaw, so tools miss it.** BOLA arises from application logic rather than input validation, making it difficult for vulnerability scanners to detect.
- **The mature fix has a hidden cost.** Policy engines only know ownership if relationships are continuously pushed into them, and RBAC alone causes "role explosion" when expressing ownership.

---

## 6. Literature Survey

### 6.1 Foundations

| Paper | What it does | Limitation | Relevance |
|---|---|---|---|
| Hartig & Pérez, *An Initial Analysis of Facebook's GraphQL Language* (AMW 2017) | First academic formalisation of GraphQL. | Descriptive; no security model. | Establishes GraphQL as a subject of formal study. |
| Hartig & Pérez, *Semantics and Complexity of GraphQL* (WWW 2018) | The canonical formal treatment. Defines execution semantics and proves complexity results. | Concerns expressiveness and cost, not access control. Authorization is absent from the model. | Proves GraphQL's own theory offers no authorization primitives — the omission we address. |
| Wittern et al., *An Empirical Study of GraphQL Schemas* (ICSOC 2019) | Studies 16 commercial and 8,399 GitHub-mined schemas. Finds most APIs are susceptible to DoS through complex queries. Documents organic naming conventions. | Focuses on schema design and DoS, not authorization. | **Our evaluation benchmark.** The corpus enables measuring inference coverage; the naming-convention finding supports our heuristics. |

### 6.2 Real-World Security Landscape

| Source | What it found | Limitation | Relevance |
|---|---|---|---|
| *GitHub Data Exposure Using the GraphQL Security Design Flaw* (arXiv:2005.13448) | A design-level flaw permitting access to data that should have been blocked, demonstrated on GitHub. | Single case study. | Precedent that GraphQL's design, not just implementation bugs, enables unauthorised access. |
| Escape, *GraphQL Vulnerabilities in the Wild* (GraphQLConf 2023) | Scanned 1,500+ public endpoints; found 46,000+ issues accessible without authentication, 10% critical. About 40% were broken authentication and access control. Leaked PII and cloud tokens. | Industry research; methodology not fully published. | Strongest quantitative evidence of exposure scale. |
| Kaur, *BOLA in the Wild* (arXiv, 2026) | Classifies 107 confirmed BOLA reports (2021–2026). Confirms the root cause. Documents GraphQL global IDs exploited by decode/increment/re-encode. | Retrospective taxonomy; proposes no defence. | Grounds our threat model; justifies global-ID decoding in our parser. |
| *A Comprehensive Study of GraphQL Security Challenges* (2025) | Surveys the full attack surface. | Survey only; nothing built or tested. | Background for scoping which threats we cover. |

### 6.3 Detection Research

**All work in this group shares one limitation: it finds problems before deployment but protects nothing once the system is live.**

| Paper | What it does | Limitation | Relevance |
|---|---|---|---|
| Tsai et al., *GraphQLer* (arXiv:2504.13358, 2025) | First context-aware security testing framework for GraphQL. Builds a dependency graph over queries, mutations, and objects, then chains operations to expose authorization flaws. Found a known CVE and new issues in production APIs. | A testing tool. Discovers flaws but never blocks a live request. | **Closest academic work.** Its dependency graph validates our type-graph approach. Our distinction: **enforcement vs. discovery.** |
| Liu et al., *PrediQL* (arXiv:2510.10407, 2025) | First LLM-guided fuzzer for GraphQL. Detects a broader flaw spectrum than GraphQLer; benchmarked against ZAP, BurpSuite, EvoMaster, GraphQLer. | Testing-time only; probabilistic. | Shows the field's energy is directed at detection, leaving runtime enforcement open. |
| Lambers et al., *Taint Analysis for Graph APIs* (ICGT 2024) | First systematic taint analysis for broken access control in graph APIs, tested on the GitHub GraphQL API. | Analysis-time; requires implementation access; does not intercept live traffic. | **Closely related.** Our ownership-taint propagation uses a similar idea but applies it at runtime on the live request path. |
| Perera et al., *Enhancing GraphQL Security Using LLMs and CNNs* (arXiv:2508.11711, 2025) | Static analysis plus ML inside an API gateway for real-time detection. States that static analysis, rate limiting, and general WAFs give limited protection. | ML produces false positives and negatives. Load testing showed noticeable overhead on CPU-only servers. Targets injection payloads, not ownership. | **Same architectural position, different task.** Their measured overhead motivates our caching design. |

### 6.4 Enforcement Research

| Paper | What it does | Limitation | Relevance |
|---|---|---|---|
| Hofer et al., *Rewriting Graph-DB Queries to Enforce ABAC* (DEXA 2023) | Intercepts an unsafe query before the database, builds its AST, and injects filters so only authorised data returns. | Targets Cypher and graph databases, not GraphQL. Assumes control of the query plan. | **The academic basis of our enforcement idea.** Its restriction to graph databases is precisely the gap we fill. |
| Hofer et al., *An Intermediate Representation for Rewriting Cypher Queries* (DEXA 2023 Workshops) | Details the AST representation used to add authorization filters at runtime. | Graph databases only. | Proves AST-level policy injection is workable. |
| *Comparison of Access Control Approaches for Graph-Structured Data* (2024) | Survey of fine-grained access-control models for graph data. | Builds nothing new. | Positions our technique among alternatives. |

### 6.5 Automatic Policy Creation — The Key Comparison

**This section determines whether our first novel contribution stands. Policy mining is a mature field, so our claim must be precise.**

| Paper | What it does | Limitation |
|---|---|---|
| Karimi et al., *ABAC Policy Extraction from Access Logs* (IEEE TDSC) | Learns ABAC rules from access logs using unsupervised pattern detection plus rule pruning. | **Requires historical access logs.** A new system has none. Worse, logs record what users *did*, so an existing BOLA flaw is learned as legitimate behaviour. |
| PAMMELA, DLBAC | Generate or learn policies with machine learning, in one case by copying a similar organisation's rules. | Still depend on existing authorization data. |
| *LLMs for ABAC Policy Mining* (arXiv:2511.18098, 2025) | Tests LLMs for policy mining. Confirms bottom-up mining works from access logs or legacy ACLs. | Authors report scalability remains limited. |

**Where each approach gets its information:**

| Information source | Used by | Available to us? |
|---|---|---|
| Access logs | Karimi et al., most policy mining | **No.** Unavailable at deployment; treats existing flaws as correct behaviour. |
| Existing access-control lists | Bottom-up policy mining | **No.** Circular — assumes the policy we are trying to create. |
| Written specifications | LLM-based policy generation | **No.** Such documents rarely exist. |
| **The schema's type structure** | **No prior work found** | **Yes.** Always available via SDL or introspection. |

**Conclusion.** Deriving ownership from the **structure of the schema** appears unexplored. This must be stated in exactly these terms — a broader claim such as "automatic authorization is new" would be contradicted by the literature above.

### 6.6 Industry Tools

| Tool | What it does | Limitation |
|---|---|---|
| **Apollo GraphOS Router** | Leading commercial GraphQL gateway with built-in authorization. Uses request claims and permission scopes such as `read:profiles`. | **Checks roles and scopes, not ownership.** Answers "does this user hold permission X?" not "does this user own order 124?" Requires schema directives (backend modification) and an Enterprise licence. |
| **Hasura** | Closest competitor. Enforces genuine row-level ownership via rules such as `{ "id": { "_eq": "X-Hasura-User-Id" } }`. | **Hasura is the backend, not a gateway.** It generates the API from the database and enforces rules because it controls query generation. It cannot sit in front of an existing GraphQL server. Rules are hand-configured per table. |
| **Inigo** | Commercial GraphQL gateway. Argues standard API gateways are blind to GraphQL-specific threats. | Focuses on DoS and sensitive-data protection. Per-object ownership is not a documented feature. |
| **Open Policy Agent (OPA)** | General policy engine. Parses queries to an AST and evaluates Rego policy per request. | Requires hand-written Rego. Normally runs inside the server. Does not resolve alias/fragment obfuscation or look up ownership automatically. |
| **GraphQL Shield / directives** | Declarative RBAC across the schema. | Community reports note that once per-object logic is added, directive code becomes unreadable and eventually unmaintainable. |
| **Official guidance** | GraphQL.js and OWASP advise placing authorization in the business-logic layer and checking both nodes and edges. | This is precisely the scattered, manual approach whose failure we address. |

---

## 7. Research Gaps

- **Detection is well studied; runtime enforcement is not.** GraphQLer, PrediQL, and taint analysis all find flaws before deployment. None protects a running system, so any flaw they miss stays fully exploitable.
- **AST-based enforcement is proven only for graph databases.** Hofer et al. validated it for Cypher, where the engine controls execution. Nothing equivalent exists at the GraphQL perimeter.
- **Gateways enforce roles, not ownership.** Apollo's scope model cannot express per-object ownership without role explosion. True ownership enforcement exists only inside backend engines such as Hasura, which requires replacing the backend.
- **Automatic rule creation depends on unavailable data.** Every established method needs access logs, legacy ACLs, or written specifications. Nobody has used the schema's own structure, even though it is always present.
- **No system checks every path to an object.** OWASP requires checking both nodes and edges, and documented cases show one route guarded while another is forgotten. No tool verifies authorization along every path through a nested query.
- **No enforcement layer removes query disguises first.** Alias multiplication (Directus CVE-2024-39895), nested fragments, IDs in variables, and encoded global IDs are documented attack methods, yet no surveyed enforcement tool normalises against all of them before checking policy.

---

## 8. Novelty — Our Contribution

> Existing solutions enforce *roles and scopes* at the gateway, or *object ownership* only inside the backend engine. We introduce a language-independent perimeter gateway that derives ownership rules from the schema itself and enforces them on every object in every query path.

**Four specific contributions:**

1. **Automatic ownership inference from schema structure.** The gateway identifies the user type, scores which relationships denote ownership, and traces indirect ownership paths, generating the rules itself. All prior policy automation mines from access logs or existing policies, which are unavailable at deployment; the schema is the one artefact always present.

2. **Multi-path ownership verification.** Ownership is checked at every node along every traversal path in a nested query, using taint propagation that drops trusted status when a query crosses into shared or third-party data. Existing tools check the object fetched, not the routes taken to reach it.

3. **Obfuscation-resistant normalisation.** Aliases, fragments, variable-carried IDs, and encoded global IDs are resolved to their true form *before* policy evaluation, defeating the disguise techniques documented in real BOLA exploits.

4. **Zero backend modification.** Enforcement is deterministic, applied at the perimeter, and independent of the backend's language or framework. No resolver edits, no schema directives, no engine replacement.

**How to defend this claim:**

- Do **not** claim the problem is unknown, or that no gateway does GraphQL authorization — Apollo GraphOS Router disproves that immediately.
- The accurate, defensible claim is: *"Gateways today enforce roles and scopes. Ownership enforcement exists only inside backend engines such as Hasura, which must replace the backend. No standalone gateway infers and enforces per-object ownership across an existing backend."*
- Contribution 1 is genuinely new rather than a new combination — lead with it.
- State its limit honestly: inference is heuristic, so the system reports confidence per type and fails closed on anything unresolved. Claiming perfect inference is the fastest way to lose credibility.

---

## 9. System Architecture

### 9.1 Is It a Framework or a Gateway?

**It is a gateway.** A framework is something developers build *with* — importing it and writing code against it. A gateway runs *in front of* an app as a separate process, intercepting traffic. Our design is the second: a standalone reverse proxy the backend does not even know exists. This means **zero backend modification**.

### 9.2 Is It Language Independent?

**Yes — and this is part of the novelty.**

- The gateway speaks HTTP and GraphQL, not Python function calls, so the backend may be Node, Java, Go, Ruby, or .NET.
- GraphQL is a specification, so query syntax is identical regardless of the server's language.
- By contrast, resolver checks, directives, and middleware libraries are **language- and framework-locked**. A GraphQL Shield rule works only in JavaScript.
- In an organisation running multiple services in different languages, one gateway protects all of them.

### 9.3 Architecture Diagram

```
┌──────────────────────── SETUP — runs once at startup ────────────────────────┐
│                                                                              │
│   ┌──────────────────┐      ┌──────────────────────┐      ┌───────────────┐  │
│   │  Backend schema  │ ───► │ Ownership inference  │ ───► │ Ownership map │  │
│   │  SDL / registry  │      │   who owns what      │      │ rules+unknown │  │
│   │  / introspection │      │                      │      │               │  │
│   └──────────────────┘      └──────────────────────┘      └───────┬───────┘  │
└───────────────────────────────────────────────────────────────────┼──────────┘
                                                                    │
                        ┌─────────────────┐                         │
                        │ Client request  │                         │
                        └────────┬────────┘                         │
                                 │                                  │
┌────────────────────────────────▼──────── GATEWAY — every request ──┼──────────┐
│                                                                    │          │
│   ┌──────────────────────────────────────────────────────┐         │          │
│   │ 1. Un-disguise the request                           │         │          │
│   │    inline fragments, resolve aliases and real IDs    │         │          │
│   └───────────────────────────┬──────────────────────────┘         │          │
│                               ▼                                    │          │
│   ┌──────────────────────────────────────────────────────┐         │          │
│   │ 2. Walk every object requested                       │         │          │
│   │    type-aware at each step, propagate ownership taint│         │          │
│   └───────────────────────────┬──────────────────────────┘         │          │
│                               ▼                                    │          │
│   ┌──────────────────────────────────────────────────────┐         │          │
│   │ 3. Verify ownership of each  ◄───────────────────────┼─────────┘          │
│   │    cache first, else probe the backend               │                    │
│   └───────────────────────────┬──────────────────────────┘                    │
│                               ▼                                               │
│   ┌──────────────────────────────────────────────────────┐                    │
│   │ 4. Verdict — one failure rejects everything          │                    │
│   └──────────┬─────────────────────────────┬─────────────┘                    │
└──────────────┼─────────────────────────────┼──────────────────────────────────┘
               ▼                             ▼
   ┌────────────────────────┐    ┌────────────────────────┐
   │   Backend server       │    │      Rejected          │
   │ receives clean request │    │  returns "not found"   │
   └────────────────────────┘    └────────────────────────┘
```

**Reading the diagram:**

- The **setup row** runs once at startup. It reads the schema, works out ownership relationships automatically, and produces the ownership map — including an explicit list of types it could not resolve.
- The **gateway column** runs on every request, in four stages.
- The **arrow from the ownership map into stage 3** is the join between the two phases. That single connection is essentially the whole contribution: automatic rule generation feeding automatic per-object enforcement.
- The **backend is untouched** — no resolver changes, no directives, works regardless of language.

---

## 10. Detailed Technical Design

### 10.1 Automatic Ownership Inference

**Goal:** the gateway reads the schema and works out which user owns each object type, with no human writing rules per type.

**Step 1 — Identify the identity type.** Three heuristics in priority order:

- **The `me`/`viewer`/`currentUser` root field.** Its return type is the identity type. This is the strongest signal because the semantics are unambiguous — GitHub literally uses `viewer`.
- **JWT claim mapping.** If the token contains `sub` or `user_id`, find a type with a matching `id` format.
- **Naming fallback.** A type named `User`, `Account`, `Member`, or `Customer`.

**Step 2 — Build the type graph.**

- **Nodes** = object types.
- **Edges** = fields whose type is another object type, labelled with the field name, recording cardinality and nullability.
- Example: `Order.owner: User!` becomes edge `Order --owner--> User`.

**Step 3 — Detect ownership edges with confidence scores.**

| Signal | Description | Confidence |
|---|---|---|
| **Direct identity reference** | A field returning the identity type with an ownership-lexicon name: `owner`, `author`, `creator`, `user`, `customer`, `assignee`, `createdBy`. | ~0.9 |
| **Reverse containment** | The identity type has a field returning `T` (e.g. `User.orders`). Anything reachable by walking outward from the user is that user's by construction. | ~0.95 (strongest) |
| **Scalar foreign key** | A field named `ownerId`, `userId`, `authorId`. Weaker (naming convention only) but directly comparable to the caller's ID. | ~0.6 |
| **Transitive path** | BFS over the type graph toward the identity type, following only edges above threshold. Confidence = product of edge confidences, so longer chains score lower. | Decays with length |

**Step 4 — Emit the ownership map in three tiers.**

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

- **High confidence (≥ 0.85)** → enforce automatically.
- **Medium (0.5–0.85)** → enforce, but log and surface for confirmation.
- **Unresolved / low** → **fail closed**, or run report-only during onboarding.

**The `UNRESOLVED` bucket is the most important design decision in the system.** Inference is heuristic, not sound — it will miss things. The claim is not "we infer everything perfectly" but *"we infer the mechanical 80% and formally surface the 20% needing a human"*, turning an invisible problem into a reviewable checklist.

**Step 5 — Resolving actual ownership at runtime.** Inference gives the *rule*; you still need the *fact*.

| Option | How it works | Trade-off |
|---|---|---|
| **(a) Pre-flight probe** *(recommended)* | The gateway issues its own minimal query along the ownership path (`{ order(id:125) { owner { id } } }`) using a privileged service token, comparing the result to the caller's JWT. | Uses the backend's own graph — no DB credentials, works with any language. Costs a round trip; requires a privileged credential. |
| **(b) Ownership cache** | Cache probe results in Redis as `owner:Order:125 → user_8` with a TTL. | High hit rate since objects are queried repeatedly. Must invalidate on ownership-changing mutations. |
| **(c) Query rewriting** | Inject a filter so the backend returns only owned rows (the Hofer/GQRA technique). | Only works if the schema exposes filter arguments. Cite as related work; note as a limitation. |
| **(d) Response-time verification** | Let the query run, then inspect and strip the response. | **Unacceptable for mutations** — side effects already occurred. Use only as defence-in-depth for queries. |

**Design decision: use (a) + (b). For mutations, always probe before forwarding.**

### 10.2 Multi-Path Ownership Verification

**Goal:** enforce ownership at every node along every traversal path, not just the root object.

**Step 1 — Normalise the query first.** This is non-negotiable; you cannot analyse a query you cannot see clearly.

- **Fragment inlining** — replace every fragment spread with its selection set, recursively, including inline fragments. Add cycle detection.
- **Alias canonicalisation** — analyse under real field names, retaining aliases only for the response. Detect **alias multiplication** (`a: order(id:1) b: order(id:2) c: order(id:3)`) — one request enumerating three objects, each checked independently. This is the Directus CVE-2024-39895 class.
- **Variable resolution** — resolve `$x` against the `variables` JSON to get the actual ID. **Skipping this bypasses the entire defence**, since real clients send IDs as variables by default.
- **Batch expansion** — the body may be a JSON array of operations, and a document may hold multiple operations.
- **Identifier normalisation** — handle `id:`, `ids: [..]`, `where: {id:}`, `filter: {}`, and decode Relay global IDs (base64 `Type:id`).

**Step 2 — Schema-aware traversal.** Walking the AST alone is insufficient; you must know what type each field returns. A field named `owner` is meaningless without knowing whether you are inside `Order` or `Comment`. In `graphql-core`, `TypeInfo` combined with `visit()` maintains type context as the visitor descends.

Maintain two structures during the walk:

- A **path stack** — `[viewer, orders, product, reviews]`.
- An **ownership taint flag** — whether the current node is provably within the caller's ownership closure.

**Step 3 — Classify every node.**

| Classification | Description | Action |
|---|---|---|
| **Anchored** | Path originates at `me`/`viewer` and every edge traversed was an ownership edge. Owned by construction. | No check needed. **This is the performance optimisation** — most legitimate traffic is anchored. |
| **Unanchored ID fetch** | A client-supplied ID names an object directly (`order(id: 125)`). | Must verify. This is where classic BOLA lives. |
| **Lateral / back-reference** | Walking back up to a user or across into another user's data (`order.owner.email`). | Must verify. This is the "guarded one path, forgot another" failure. |
| **Collection** | Returns a set (`orders(first: 100)`). | Fine if anchored. A global root collection requires an enforced ownership filter or denial. |

**Step 4 — Ownership taint propagation.** This is the subtlest part and the easiest to get wrong.

- Start: `tainted = true` at `me`/`viewer`; `false` at any other root field.
- Traversing an **ownership edge** → taint **preserved**.
- Traversing into a **shared/global type** (e.g. `Product`) → taint **dropped**.
- Traversing a **back-reference to an identity type** → taint **dropped**, node flagged as lateral.
- Any node with `tainted == false` requesting a non-public field → **verify explicitly**.

**Why this matters:** consider `viewer → orders → product → reviews → author → email`. Your order is yours, but the *product* is shared. Without taint-dropping, an attacker anchors at `viewer`, hops through a shared object, and walks into a stranger's data while still appearing anchored. It is structurally the same idea as taint analysis in program security — which connects to the Lambers ICGT 2024 paper, except applied **at runtime on the live request path**.

**Step 5 — Compose the verdict.**

- **Any single node fails → reject the entire request.** No partial execution, no field stripping.
- **Return a uniform error** — "not found" rather than "forbidden". Revealing that an object exists but is not yours is itself a disclosure.
- **Emit a structured audit log** — node, path, object ID, rule fired, decision.
- **Run depth and complexity limits in the same walk** — you are already traversing the tree.

### 10.3 Handling Disabled Introspection

Disabling introspection in production is standard security advice, so the gateway must work without it.

| Option | Description |
|---|---|
| **SDL at deploy time** *(recommended)* | The schema exists as a file in the backend repository. A CI/CD hook pushes it to the gateway on deploy. Better than introspection: works regardless of settings, available before traffic flows, and solves schema drift properly. |
| **Private introspection** | Introspection is usually disabled for *untrusted external clients*. The backend can permit it specifically from the gateway by IP allowlist, service token, or internal-only port. |
| **Gateway as introspection boundary** | The elegant inversion: the backend keeps introspection enabled internally, and the **gateway blocks all introspection queries from outside**. A limitation becomes a feature, and it demos easily. |
| **Schema registry** | In federated setups the schema already lives in a central registry. The gateway pulls from there. |

**Implementation:** design a pluggable **schema source** interface with several implementations. A small abstraction that makes the gateway deployable anywhere, and a credible answer when a reviewer asks.

---

## 11. Complete Request Flow

### Phase 0 — Startup: build the ownership map

- **Get the schema**, trying sources in order: SDL file → schema registry → introspection with an internal credential.
  - *If all fail:* do not start in enforcing mode. Refuse to start, or run report-only with a loud warning. Never silently start with an empty map.
- **Find the identity type** via `me`/`viewer`, JWT claim shape, then naming.
  - *If none found:* confidence drops everywhere; most types land in `UNRESOLVED`.
- **Build the type graph** — object types as nodes, object-returning fields as edges.
- **Score ownership edges** using the four signals.
- **Emit the map in three tiers** — enforce, flag, or fail closed.
- **Register a schema-change hook** so the map regenerates on backend deploy.
  - *If a request references a field not in the loaded schema:* reject and trigger a refresh rather than guessing.

### Phase 1 — Request arrives: cheap rejections first

- **Block introspection queries** (`__schema`, `__type`).
- **Verify identity** — check JWT signature and expiry, extract caller ID.
  - *If missing, expired, or malformed:* reject immediately. Never default to anonymous.
- **Reject oversized payloads** before parsing — body size cap and batch-operation count cap.

### Phase 2 — Normalise: make the query honest

- **Expand batching** — validate all operations in the document, not just the named one.
- **Parse to AST** — syntax error means reject.
- **Inline all fragments**, named and inline, recursively.
  - *Detect fragment cycles* and reject rather than recursing forever.
- **Canonicalise aliases** — analyse under real field names.
  - *Count alias multiplication* and feed it into complexity limits.
- **Resolve variables to actual values.**
  - *Reject* undeclared, missing, or wrongly-typed variables.
- **Normalise identifier shapes** — including decoding Relay global IDs.
- **Enforce depth and complexity limits** in this same pass, aborting early.

### Phase 3 — Walk and classify

- **Walk the AST with type context**, tracking path stack and taint flag.
- **Start taint as true** only if the operation begins at `me`/`viewer`.
- **Classify each node** — anchored, unanchored ID fetch, lateral, or collection.
- **Propagate taint correctly** — preserved across ownership edges, dropped on shared types or back-references.
- **Check mutations before forwarding** — there is no verify-the-response option once a write has happened.
- **Apply the unresolved policy** for types in the `UNRESOLVED` bucket.

### Phase 4 — Resolve ownership where needed

- **Check the cache first**, comparing to the caller ID.
- **On a miss, probe the backend** along the inferred path, then cache with a TTL.
- **Batch the probes** — a query touching 50 objects must not fire 50 sequential lookups.
- **Fail closed** if the probe errors, times out, or the backend is down. A check you could not perform is not a check that passed.
- **Return the same "not found"** for nonexistent objects as for unowned ones — distinguishing them reveals which IDs are real.
- **Invalidate the cache on ownership-changing mutations.** Stale ownership is a security bug, not a freshness bug.
- **Scope the service credential minimally** (read-only, ownership fields only) and audit it — it is a new attack surface and the sharpest question a reviewer can ask.

### Phase 5 — Verdict

- **Default deny** — a node passes only if explicitly permitted.
- **One failure rejects the whole request** — partial responses leak which objects exist.
- **Return a uniform error** — identical for missing objects, unowned objects, and unresolved types.
- **Emit a structured audit record** every time. This is both evaluation data and the system's operational value.

### Phase 6 — Forward and respond

- **Forward the original request**, not the normalised one — the client expects its aliases honoured. Normalisation was for analysis only.
- **Return the backend response** unchanged.
- *Optional:* a response-side scan as defence-in-depth for queries only — never for mutations, never as the primary control.

**The security-critical ordering:** Phase 2 must fully complete before Phase 3. If normalisation misses anything — one fragment form, unresolved variables, undecoded global IDs — every later phase analyses the wrong query and the gateway is bypassable. **Concentrate testing there.**

---

## 12. Other Vulnerabilities Covered

The architecture is already a general-purpose GraphQL security chokepoint. Once the AST walk is paid for, several defences come almost free.

### 12.1 Free Wins — already in the pipeline

| Vulnerability | Description | Where it fits |
|---|---|---|
| **Depth attacks** | Infinitely nested queries exhaust the server. | Phase 2 — depth counter |
| **Complexity attacks** | Wide, shallow, expensive queries. | Phase 2 — per-field cost cap |
| **Alias amplification** | `a: x b: x c: x` × 1000; basis of Directus CVE-2024-39895. | Phase 2 — already counted |
| **Fragment cycles** | Self-referencing fragments crash the parser. | Phase 2 — already detected |
| **Batch flooding** | Hundreds of operations in one array. | Phase 1 — operation cap |
| **Introspection exposure** | Attacker downloads the entire schema. | Phase 1 — already blocked |
| **Pagination abuse** | `first: 999999999`. | Phase 3 — cap during the walk |
| **Directive abuse** | Duplicate `@skip`/`@include` to confuse parsing. | Phase 2 — validate counts |

### 12.2 Cheap Additions

- **BFLA (Broken Function Level Authorization)** — "can you call this operation at all", e.g. a normal user invoking `deleteUser`. You already have identity and the parsed operation, so an operation-level allowlist is a small addition.
- **Excessive data exposure** — field-level sensitivity, such as reading another user's `email` on an object you do own. Your walk visits every field, so a sensitive-field policy slots in.
- **Batching-based auth bypass** — attackers batch 500 `login(otp:)` mutations in one HTTP request, defeating per-request rate limits. Cap sensitive mutations to one per request; count operations, not HTTP requests.
- **Error and suggestion leakage** — GraphQL servers say *"Did you mean `secretField`?"*, leaking schema even with introspection off. Extend error normalisation to sanitise all backend errors in Phase 6.
- **CSRF** — reject mutations over GET; enforce `Content-Type: application/json`.

### 12.3 Partial Help — mention, do not overbuild

- **Rate limiting** — the gateway is architecturally the right place, and per-user *cost-based* limiting is correct for GraphQL. But doing it properly is its own project. Implement something basic; claim no more.
- **Persisted query allowlisting** — only pre-registered queries accepted. Worth knowing, but note it **does not solve BOLA**: a legitimate persisted query with a swapped ID is still BOLA.

### 12.4 Explicitly Out of Scope

- **SQL/NoSQL/command injection** — the gateway sees `search: "foo"` but has no idea how the resolver uses it. Irreducibly a backend concern.
- **SSRF via arguments** — same reason.
- **Business-logic flaws** beyond authorization — requires domain knowledge the gateway lacks.
- **Mutation race conditions** — requires transactional control at the data layer.
- **Authentication itself** — we consume the JWT; issuing it belongs elsewhere.

**Scoping statement for the report:** *"Object-ownership enforcement is the primary contribution. Because the gateway already performs full AST normalisation and traversal, a set of structural defences are enforced in the same pass at negligible additional cost. Injection, business-logic, and data-layer concerns remain out of scope by design, as they require backend semantics the perimeter cannot observe."*

---

## 13. Implementation Plan

| Step | Task | Purpose |
|---|---|---|
| **1** | Build a victim application — a small GraphQL backend with a few users and objects, containing a deliberate BOLA hole. | You need something real to break and then defend. |
| **2** | Prove the attack works — log in as user A, change an ID, retrieve user B's data. | This is the "before" state, and the opening of your demo. |
| **3** | Build the basic reverse proxy — intercept and forward, doing nothing clever yet. | Prove requests flow through the gateway. |
| **4** | Add AST parsing and normalisation — fragments, aliases, variables, global IDs. | The gateway can now see the true request. |
| **5** | Add ownership inference — read the schema, build the type graph, score edges, emit the map. | Generates the rules automatically. |
| **6** | Add the ownership check — extract IDs, classify nodes, propagate taint, verify, drop violations. | **The centrepiece.** Where most effort and novelty live. |
| **7** | Add self-defence limits — depth, complexity, alias counts. | The gateway cannot be crashed. |
| **8** | Add the ownership cache (Redis). | Answers "does this slow the app down?" |
| **9** | Evaluate and measure — run the attack suite and record results. | Turns a demo into a credible result. |

**Testing focus:** concentrate effort on Phase 2 normalisation. If it is incomplete, everything downstream analyses the wrong query.

---

## 14. Hardware and Software Requirements

### Hardware

- Standard developer laptop or workstation with a multi-core CPU.
- 8 GB RAM minimum; 16 GB comfortable.
- A few GB of free disk space.
- No GPU, cloud account, or specialised hardware — everything runs locally.

*Report phrasing:* "The system is lightweight by design; all components run on a single commodity workstation without specialised or accelerated hardware." This reinforces the lightweight-perimeter claim.

### Software

**Gateway core:**

- **Python 3.x** — implementation language.
- **FastAPI + Uvicorn** — reverse-proxy gateway.
- **graphql-core** — AST parsing, alias and fragment resolution, `TypeInfo` traversal.
- **httpx** — forwards validated requests to the backend.

**Authorization:**

- **PyJWT** — reads user identity from the token.
- **Open Policy Agent (OPA)** — *optional*, only if used as the policy engine instead of Python.

**Performance:**

- **Redis** — ownership cache (not generic query caching).

**Test backend:**

- GraphQL server with a deliberate BOLA flaw — Strawberry or Ariadne (Python), or Apollo Server (Node.js). **Pick one before the final report.**
- **PostgreSQL or SQLite** — sample users and objects.

**Testing and evaluation:**

- **pytest** — attack test scripts.
- **Locust or k6** — load testing for latency measurement.
- **Postman or Insomnia** — manual query testing.

**Tooling:**

- **Docker + Docker Compose** — runs all components together; reproducible demo.
- **Git/GitHub** — version control.
- OS: Linux, macOS, or Windows (Ubuntu recommended).

**Minimum viable stack:** Python + FastAPI + graphql-core + a small GraphQL backend + SQLite. Everything else strengthens the project but is not required for a first prototype.

---

## 15. Expected Outcomes

1. A working reverse-proxy gateway that enforces object-level authorization on GraphQL APIs **without any modification to the backend**.
2. An **ownership map generated automatically** from the schema, reporting a confidence level per object type and an explicit list of types requiring manual review.
3. **Demonstrated blocking of BOLA attacks** across four variants — direct ID substitution, alias-disguised, fragment-hidden, and variable-carried — against a deliberately vulnerable GraphQL application.
4. **Measured performance overhead**, reported as median added latency with and without ownership caching.
5. **Measured inference coverage** — the percentage of object types for which ownership is correctly inferred across a corpus of real-world public GraphQL schemas.

**Outcome 5 is the one to emphasise.** Outcomes 1–4 prove the system works. Outcome 5 produces a *finding* interesting independent of the implementation: nobody has published what fraction of real GraphQL schemas expose ownership structurally. The Wittern et al. corpus (8,399 mined schemas) makes it directly achievable, and it elevates the project from "we built a tool" to "we built a tool and learned something."

**Caution:** do not write target figures you cannot yet justify. State *what will be measured*, not what you expect to find.

---

## 16. Scope and Limitations

**Declare these before a reviewer finds them. Doing so is a strength.**

- **Group and organisation ownership** — "owned by a team I belong to" is a ReBAC-shaped problem, considerably harder than direct ownership. Support single-hop membership at most, or exclude explicitly.
- **Subscriptions** — long-lived connections need ongoing re-authorization, not a single check at connect time.
- **Black-box third-party APIs** — the gateway requires schema access. It is designed for first-party deployment, not as a proxy for APIs you do not control.
- **Inference completeness** — heuristics are unsound by nature. Naming conventions vary, and some schemas encode ownership in ways no heuristic catches. The `UNRESOLVED` tier is the honest answer, not a gap.
- **The privileged service credential** — the probe mechanism requires a credential that is itself a high-value target. Scope it minimally and audit it.
- **Cache invalidation on ownership transfer** — if a mutation reassigns an object's owner, stale entries are a security bug. Invalidate on mutations touching that type; use short TTLs as a backstop.
- **Probe latency** — mitigated by caching and the anchoring optimisation, but a real cost that must be measured.

---

## 17. Real-World Relevance

### 17.1 Adoption

- Roughly **200,000+ verified companies** use GraphQL as of 2026; one 2024 report found **61.5% of respondents using it in production**, with 15.5% exploring it.
- Named production users: **Meta** (creator), **GitHub**, **Shopify**, **PayPal**, **Netflix**, **Airbnb**, **Twitter/X**, **The New York Times**, **LinkedIn**, **Coursera**, **Amazon**, **Walmart**.
- Adoption concentrates in **mobile, fintech, and healthcare** — the sectors where object-level data exposure carries the greatest regulatory and human cost.
- GraphQL is most often deployed as a **Backend-for-Frontend aggregation layer** in front of existing services — a single public door to a great deal of connected, sensitive data. That is exactly the shape this gateway defends.

### 17.2 Documented Incidents

- **Airline booking API (2026).** An autonomous red-team agent read client-side JavaScript, minted an anonymous session, mapped the GraphQL schema, found unprotected resolvers, and confirmed mass extraction of a major airline's booking database — with read *and write* access over active itineraries — in **15 minutes with zero human guidance**. The analysis notes that exposing core resolvers to unauthenticated traffic means a simple logic flaw nullifies all network perimeter security, and that **context-aware authorization at the object level is the only prevention**.
- **Shopify (HackerOne #2207248).** A **US$5,000** bounty paid for an IDOR on the GraphQL `BillingDocumentDownload` and `BillDetails` queries.
- **BOLA taxonomy (2026).** 107 classified reports; GraphQL global IDs systematically exploited via decode/increment/re-encode across HackerOne, GitLab, and Shopify. Critical cases cluster in government and fintech.
- **Fintech (Salt Labs).** A financial platform's GraphQL API failed to cross-check sender identity during funds-transfer requests; researchers altered transfer targets and auto-authorised the transactions.
- **CVEs:** Directus CVE-2024-39895 (alias/batching abuse), Hasura CVE-2022-46792 (row-level authorization mishandling), Apollo Router CVE-2025-32032, GitLab CVE-2025-3922.

### 17.3 An Important Nuance

- A 2025 industry report observed **"no GraphQL-specific breaches"** in one quarter — but explicitly attributed this to **detection gaps rather than safety**, because GraphQL's single dynamic endpoint obscures visibility for traditional controls.
- **The apparent silence is itself evidence for the problem.** If asked "why don't I hear about GraphQL breaches?", this is the answer.

### 17.4 Accuracy Note

- Describe these as **documented vulnerabilities and disclosures** — responsible-disclosure findings, bug bounties, and CVEs — **not** confirmed criminal breaches with public victim counts.
- **BOLA and IDOR are the same underlying flaw.** IDOR is the older web-application term; BOLA is the API-specific name. In OWASP's 2025 web Top 10, IDOR falls under A01 Broken Access Control.

---

## 18. Viva Preparation

### 18.1 The Core Positioning Statement

> "BOLA is the #1 API security risk and is well-documented in GraphQL; it is *known*, but current defences are manual, scattered across thousands of resolvers, and blind to GraphQL's own obfuscation features. Our contribution is a centralised, query-aware perimeter gateway that enforces object-ownership automatically."

### 18.2 Anticipated Questions and Answers

| Question | Answer |
|---|---|
| **"How is this different from OPA?"** | OPA is a general policy *engine*; ours is a purpose-built ownership *gateway*. OPA could even serve as our evaluation backend. On its own it does not de-obfuscate aliases/fragments, does not automatically extract object IDs and verify ownership, and typically runs inside the server. |
| **"Doesn't Apollo Router already do this?"** | Apollo enforces **roles and scopes** — "does this user hold permission X?" — not "does this user own object 124?" It also requires schema directives, which means modifying the backend. |
| **"Hasura does row-level ownership."** | Hasura **is the backend**, not a perimeter gateway. It enforces ownership because it generates the SQL. You cannot put Hasura in front of an existing Node or Java GraphQL server — you would have to replace the backend. |
| **"Isn't automatic policy generation already solved?"** | Policy mining is mature, but every approach derives rules from access logs, legacy ACLs, or written specs — none available at deployment, and logs encode existing flaws as legitimate. Inference from schema topology is unexplored. |
| **"Why hasn't Meta fixed this?"** | GraphQL deliberately leaves authorization to the application, because object ownership is application-specific and cannot live in a generic spec. Meta enforces it internally with bespoke infrastructure that does not generalise. |
| **"What if introspection is disabled?"** | The primary schema source is the SDL file supplied at deploy time via a CI/CD hook, which works regardless. The gateway can also act as the introspection boundary, letting the backend keep it enabled internally while blocking external access. |
| **"Isn't REST more secure?"** | No. The same flaw exists in REST, where it is called IDOR. The difference is structural: REST's endpoint URLs reveal intent, giving a natural chokepoint for enforcement. GraphQL's single endpoint destroys that, which is what our gateway restores. |
| **"What about persisted queries?"** | They eliminate arbitrary queries but **do not solve BOLA** — a legitimate persisted query with a swapped ID is still BOLA. |

### 18.3 The Strongest Sentence to Say Out Loud

> "It enforces object-ownership, not just field-level filtering, which is what actually makes it a BOLA defence rather than a generic query firewall."

This signals deep understanding of the problem, and it is the distinction most students building a "GraphQL security" project would get wrong.

### 18.4 What Not to Claim

- Do **not** say the problem is unknown or undiscovered.
- Do **not** say no gateway performs GraphQL authorization.
- Do **not** claim perfect inference.
- Do **not** claim broad coverage of injection, business logic, or rate limiting.

---

## 19. Resume Entry

**Schema-Aware Zero-Trust Security Gateway for Preventing GraphQL BOLA Vulnerabilities** | *Final Year Project*
*Python, FastAPI, graphql-core, Redis, Docker*

- Developing a perimeter security gateway that protects application APIs by preventing users from accessing data belonging to others — mitigating Broken Object-Level Authorization, the top-ranked API security risk per OWASP.
- Engineering request-inspection logic that detects and neutralises evasion techniques used to disguise malicious requests, rejecting unauthorised access before it reaches the backend.
- Validating the solution against a purpose-built vulnerable application using multiple real-world attack scenarios to confirm consistent, reliable protection.

**Notes:**

- Replace "consistent, reliable protection" with concrete figures (block rate, latency) once evaluation produces them.
- Only list tools actually used and defensible in an interview. Drop Redis or OPA if not built.

---

## 20. Verification Checklist Before Submission

- [ ] Open and confirm every arXiv identifier and DOI cited. Treat the BOLA taxonomy reference (arXiv:2605.25865) as unverified until checked.
- [ ] Run the same searches directly in **IEEE Xplore, ACM Digital Library, and Google Scholar** for "GraphQL access control", "GraphQL authorization enforcement", and "GraphQL security gateway". Web search does not cover subscription-indexed venues.
- [ ] Record the date each database was searched.
- [ ] Check Inigo's and Escape's current feature documentation directly — their marketing is vague about object-level capabilities.
- [ ] Search for 2025–2026 startups in this space to confirm nothing has landed on the exact idea recently.
- [ ] Lock the architectural decision: OPA as policy engine, or pure Python. This changes the software requirements list.
- [ ] Lock the test backend choice: Python (Strawberry/Ariadne) or Node (Apollo Server).
- [ ] Ensure the project title, problem statement, novelty, and objectives all state the same thing — object-ownership enforcement, not field filtering.

---

## Appendix A: Ethical and Legal Note

- **Never test BOLA or authorization flaws against systems you do not own** or lack written permission to test. Probing a live `/graphql` endpoint with modified IDs constitutes unauthorised access and is illegal in most jurisdictions, including under India's IT Act.
- **For attack testing, use:** your own deliberately vulnerable backend, DVGA (Damn Vulnerable GraphQL Application), PortSwigger Web Security Academy labs, or HackTheBox/TryHackMe sandboxes.
- **For learning query syntax only,** public GraphQL playgrounds are acceptable: Countries API (`countries.trevorblades.com`), Rick & Morty API, and GitHub's official explorer (which returns only your own authorised data).
- The distinction: use public APIs to **learn how queries look**; use your own vulnerable instance to **test attacks**.
