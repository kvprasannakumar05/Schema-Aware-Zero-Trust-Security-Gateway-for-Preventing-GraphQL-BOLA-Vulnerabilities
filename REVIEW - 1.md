
# TITLE : Schema-Aware Zero-Trust Security Gateway for Preventing GraphQL BOLA Vulnerabilities


### WHAT IS GRAPHQL ?


### SCHEMA IN GRAPHQL


### BOLA


### JOURNEY OF A GRAPHQL QUERY


### GraphQL Authorization: Current Techniques & Their Flaws


### Problem statement 




![[Pasted image 20260722205029.png]]


![[Pasted image 20260722205230.png]]


![[Pasted image 20260722205240.png]]








# Review Presentation — Slide Content

**Project Phase I | 20CYS495 | TIFAC CORE in Cyber Security**

---

## Slide 1 — Title

**Project Title:** Schema-Aware Zero-Trust Security Gateway for Preventing GraphQL BOLA Vulnerabilities

**Domain:** API Security / Web Application Security (Access Control)

**Team Members:** [Name 1, Name 2, Name 3, Name 4]

**Guide:** [Guide Name]

---

## Slide 2 — Problem Statement

**Statement (say it in exactly these two lines):**

> GraphQL APIs cannot reliably stop a logged-in user from reading or changing another user's data objects, because the ownership check has to be hand-written inside thousands of separate backend functions and is easily forgotten.
> 
> Existing firewalls and API gateways cannot cover this gap, because they cannot read the structure of a GraphQL query or tell whether the user owns the object being asked for.

**Motivation and significance**

- BOLA (Broken Object Level Authorization) has been the **No. 1 risk in the OWASP API Security Top 10 since 2019**.
- 107 confirmed BOLA reports were classified from bug bounty disclosures between 2021 and 2026.
- Real cases: Shopify paid a $5,000 bounty for an IDOR flaw in GraphQL billing queries (HackerOne #2207248); in 2026 an automated agent pulled an airline's full booking database in 15 minutes.
- GraphQL runs in production at Meta, GitHub, Shopify, PayPal, Netflix, Airbnb, LinkedIn and the New York Times — heaviest in mobile, fintech and healthcare, where leaking one person's data to another is most costly.
- Ordinary scanners miss it: the attack uses **valid syntax on legitimate endpoints**, so it looks like normal traffic.

---

## Slide 3 — Literature Survey (part 1: what has been studied)

Keep this slide short — one line each, the table on the next slide does the real work.

- **Foundations** — Hartig & Pérez defined how GraphQL works formally. Their work proves GraphQL has **no built-in access control** at all.
- **How bad it is** — Escape scanned 1,500+ public endpoints and found 46,000+ issues reachable without logging in; ~40% were broken access control. Leaked data included passport details and cloud tokens.
- **Finding flaws** — GraphQLer, PrediQL and taint analysis all detect authorization bugs **before** deployment.
- **Blocking attacks** — Hofer et al. rewrite queries at the syntax-tree level, but only for graph databases.
- **Making rules automatically** — policy mining learns rules from access logs or old policies.
- **Industry** — Apollo, Hasura, Inigo, OPA, GraphQL Shield.

---

## Slide 4 — Literature Survey (part 2: comparison table)

|Work (Year)|What it does|Limitation|How our project differs|
|---|---|---|---|
|**GraphQLer** — Tsai et al. (2025)|First context-aware security testing tool for GraphQL. Builds a dependency graph and chains operations to expose access-control bypasses.|Only a **testing** tool. Never blocks a live request; any flaw it misses stays exploitable.|We **enforce at runtime**, on every live request, instead of only discovering flaws.|
|**PrediQL** — Liu et al. (2025)|First LLM-guided fuzzer for GraphQL. Beats ZAP, BurpSuite, EvoMaster in coverage.|Testing time only, and results are **probabilistic**, not guaranteed.|Our checks are **deterministic** — an ownership check either passes or fails.|
|**Taint Analysis for Graph APIs** — Lambers et al. (ICGT 2024)|First taint-analysis method for broken access control in graph APIs; tested on part of GitHub's API.|Analyses code and schema **offline**; never sees live traffic.|We use the same tainting idea but apply it **live, per request**.|
|**Rewriting Graph-DB Queries for ABAC** — Hofer et al. (DEXA 2023)|Intercepts a query, builds its syntax tree, and inserts filters so only allowed data is returned.|Works on **Cypher / graph databases**, not GraphQL. Assumes it controls query execution.|We move the same idea to the **GraphQL perimeter**, where the gateway does not control execution.|
|**GraphQL Security using LLMs + CNNs** — Perera et al. (2025)|Machine learning inside an API gateway to spot malicious queries in real time.|ML gives false positives/negatives; their own tests showed slowdown. Targets **injection**, not ownership.|We check **object ownership** by rule, not by guessing from a model.|
|**ABAC Policy Extraction from Access Logs** — Karimi et al. (IEEE TDSC)|Learns access rules automatically by mining patterns from access logs.|Needs **historical logs**. A new system has none — and logs record what users _did_, so an existing BOLA flaw is learned as normal behaviour.|We derive rules from the **schema structure**, which always exists on day one.|
|**BOLA in the Wild** — Kaur (2026)|Classifies 107 confirmed BOLA reports (2021–2026). Confirms the root cause and shows global IDs being decoded, changed, re-encoded.|Classifies past incidents only. **Proposes no defence.**|We build the defence, and use this taxonomy as our threat model.|
|**Apollo GraphOS Router** (Industry)|Leading commercial GraphQL gateway with built-in authorization using claims and scopes.|Checks **roles and scopes**, not ownership. Can answer "has permission X?" but not "owns order 124?" Needs schema changes + Enterprise licence.|We answer the ownership question, with **no backend or schema change**.|
|**Hasura** (Industry)|Genuinely enforces row-level ownership rules.|It **is** the backend — it generates the API and only works because it controls the query. Cannot be put in front of an existing server. Every rule is written by hand per table.|We sit **in front of any existing GraphQL server**, and infer the rules instead of hand-writing them.|
|**Open Policy Agent (OPA)** (Industry)|General policy engine; parses GraphQL into a syntax tree and checks written policy per request.|Policies hand-written in Rego. Does **not undo alias/fragment disguises** and does not look up ownership itself.|We **normalise disguises first**, then resolve ownership automatically.|

---

## Slide 5 — Gaps in Existing Solutions

1. **Detection is well studied; runtime protection is not.** GraphQLer, PrediQL and taint analysis all stop at the testing stage. Nothing protects a running system.
2. **Syntax-tree enforcement is proven only for graph databases.** Nothing equivalent exists at the GraphQL perimeter.
3. **Gateways enforce roles, not ownership.** Role-based rules would need an endless number of roles to express "user owns object 124".
4. **True ownership enforcement means replacing your backend** (Hasura).
5. **Automatic rule creation needs data we do not have** — logs, old policies, or written specs. Nobody has used the schema's own structure, even though it is always available.
6. **No tool checks every path to an object.** OWASP asks for checks on both nodes and edges; developers guard one route and forget another.
7. **No enforcement layer removes disguises first** — alias multiplication (Directus CVE-2024-39895), nested fragments, IDs hidden in variables, encoded global IDs.

**Our project addresses gaps 1–6 with one system.**

---

## Slide 6 — Project Objectives

**Main objective:** To design and build a schema-aware security gateway that blocks BOLA attacks on GraphQL APIs at the perimeter, before the request reaches the backend.

**Objectives**

1. To design a gateway that sits in front of an existing GraphQL server and inspects every incoming request without requiring any change to the backend.
2. To automatically work out ownership rules from the structure of the GraphQL schema alone, using type relationships and naming patterns, so no access logs or hand-written policies are needed.
3. To normalise every incoming query — expand fragments, strip aliases, substitute variables, and decode global IDs — so a disguised request is seen in its true form before any check is made.
4. To verify ownership at every object along every path of a nested query, covering both nodes and edges as OWASP requires.
5. To keep the added delay low enough for production use, by caching ownership results.
6. To evaluate the system on a large collection of real GraphQL schemas and measure what percentage of object types have ownership inferred correctly.
7. To compare the gateway against existing tools (Apollo, OPA, GraphQL Shield, and standard scanners) on detection rate, false positives, and latency.

**Sub-objectives**

- Build a deliberately vulnerable test API and an attack suite based on the 107 documented BOLA cases.
- Provide an "audit only" mode that logs violations without blocking, for safe rollout.

---

## Slide 7 — Inputs and Outputs

**Inputs**

- The API's **GraphQL schema** — read from a file or fetched through introspection.
- The **incoming request** — the query text, its variables, and the operation name.
- The **caller's identity** — the user ID taken from the auth token or session.
- **Ownership facts** — who owns which object, looked up from the data source and cached.

**Outputs**

- An **allow or block decision** for each request, made before it reaches the backend.
- A **normalised query tree** with all aliases, fragments, variables and encoded IDs resolved.
- A **decision log** naming the exact object and path that caused a block.
- The **generated ownership policy** produced from the schema, in readable form so it can be reviewed and edited.
- **Evaluation metrics** — inference coverage, detection rate, false positives, added latency.

**Data flow (draw this as a diagram)**

```
Client / Attacker
      │  GraphQL request + token
      ▼
┌─────────────────────────────────────────────┐
│              OUR GATEWAY                    │
│  1. Parse query into a syntax tree          │
│  2. Normalise (fragments, aliases,          │
│     variables, encoded IDs)                 │
│  3. Walk every path, list every object      │
│  4. Check ownership for each object         │
│     (policy inferred from schema + cache)   │
└──────────────┬──────────────────┬───────────┘
        ALLOW  │                  │  BLOCK
               ▼                  ▼
     Existing GraphQL       Error returned
     server (unchanged)     + logged
               │
               ▼
        JSON response ──► Client
```

_(Offline, one time: Schema ──► Ownership Inference Engine ──► Policy)_

---

## Slide 8 — Tools, Methodologies and Technologies

**Languages and core libraries**

- Python with `graphql-core` (or Node.js/TypeScript with `graphql-js`) for parsing and walking the query syntax tree
- FastAPI / Express for the proxy layer
- Redis for caching ownership results

**Test environment**

- Damn Vulnerable GraphQL Application (DVGA) and a custom Apollo Server demo app
- Docker and Docker Compose for reproducible setup

**Evaluation data**

- The Wittern et al. schema corpus — 16 commercial schemas and 8,399 schemas collected from GitHub

**Security and testing tools**

- Attack side: curl, Postman, Burp Suite, InQL, GraphQL-Cop, OWASP ZAP, GraphQLer
- Load testing: k6 or Locust, to measure added latency

**Methodology**

- Agile with two-week sprints, following standard SDLC stages: requirements → design → implementation → testing → deployment → documentation
- Git and GitHub for version control, with issue tracking per sprint

**Techniques**

- Abstract syntax tree (AST) analysis and query normalisation
- Type-graph traversal and relationship scoring for ownership inference
- Ownership taint tracking applied per request
- Zero-trust principle: check every object, on every path, every time

---

## Slide 9 — Deliverables

1. A working **security gateway** (reverse proxy) that blocks BOLA attacks on any existing GraphQL API without backend changes.
2. An **ownership inference engine** that reads a schema and produces an ownership policy automatically.
3. A **query normaliser** that removes alias, fragment, variable and encoded-ID disguises.
4. A **test bed**: a deliberately vulnerable GraphQL application plus an attack suite built from documented BOLA cases.
5. **Evaluation results**: percentage of object types with ownership inferred across thousands of real schemas, detection rate, false-positive rate, and latency overhead.
6. A **comparison study** against Apollo GraphOS Router, OPA, GraphQL Shield and standard scanners.
7. **Documentation** — setup guide, architecture document, and the generated policy format.
8. A **final report** and a draft research paper.

---

## Slide 10 — 8-Month Project Plan

**Start: July 2026 → First demo: October 2026 (Month 4) → Final delivery: February 2027**

|Task|M1 Jul|M2 Aug|M3 Sep|M4 Oct|M5 Nov|M6 Dec|M7 Jan|M8 Feb|
|---|---|---|---|---|---|---|---|---|
|Research & literature survey|██|██|||||||
|Requirement analysis & threat model|██|██|||||||
|Architecture & design||██|██||||||
|Build vulnerable test API + attack suite||██|██||||||
|Proxy + parser + query normaliser|||██|██|||||
|Ownership inference engine (v1)|||██|██|||||
|**DEMO 1 — working prototype**||||★|||||
|Path-wise enforcement (nodes + edges)||||██|██||||
|Caching & performance tuning|||||██|██|||
|Evaluation on schema corpus||||||██|██||
|Comparison with existing tools|||||||██||
|Testing, bug fixing, hardening|||||██|██|██|██|
|Documentation & final report|||||||██|██|
|Review preparation|██||██|★||██||★|

**Milestones**

- **Month 4 (October 2026) — First working demo.** We will show: a live GraphQL API, an attacker sending a query for another user's order, the backend leaking it without the gateway, and the gateway blocking the same request — including an aliased and a global-ID-encoded version of the attack.
- **Month 6 (December 2026)** — Full path-wise enforcement plus caching, with measured latency figures.
- **Month 8 (February 2027) — Final delivery.** Complete gateway, evaluation results across the schema corpus, comparison study, and final report.

---

## Slide 11 — Individual Work Log (last 4 weeks)

_Fill from the shared Excel sheet — one row per member. Suggested split:_

|Member|Work done in last 4 weeks|
|---|---|
|[Name 1]|Literature survey — foundations and detection research (GraphQLer, PrediQL, taint analysis); prepared comparison table|
|[Name 2]|Studied GraphQL internals — query lifecycle, resolvers, aliases, fragments, global IDs; documented BOLA attack flow|
|[Name 3]|Reviewed industry tools — Apollo, Hasura, Inigo, OPA, GraphQL Shield; identified the roles-vs-ownership gap|
|[Name 4]|Reviewed policy-mining literature; confirmed schema-based inference is unexplored; set up test environment and repository|

_(Keep the Excel sheet updated — it is explicitly marked in the rubric.)_

---

## Slide 12 — Technical Challenges and Mitigation

|Challenge|Status / Proposed solution|
|---|---|
|Inferred ownership rules may be wrong and block real users|Give every inferred rule a confidence score. Ship an **audit-only mode** first that logs instead of blocks, plus a manual override file.|
|The gateway adds delay to every request|**Cache ownership results in Redis**; batch lookups for repeated objects in one query. Perera et al. measured slowdown from ML-based gateways — this is why we avoid ML in the hot path.|
|The gateway does not naturally know who owns what|Resolve ownership through a small lookup against the data source, then cache. Design this as a pluggable adapter.|
|Interfaces, unions and abstract types make the type graph harder to walk|Expand every abstract type into its possible concrete types during normalisation.|
|Global ID encoding differs between implementations (Relay, custom base64)|Pluggable decoders, with a fallback that treats an undecodable ID as untrusted.|
|Schemas with unusual naming will not infer cleanly|Report coverage honestly as a result. Wittern et al. found developers follow consistent naming habits, which supports our heuristics; anything left over falls back to manual config.|
|No public benchmark of GraphQL BOLA attacks exists|Build our own attack suite from the 107 documented disclosures in Kaur's taxonomy.|
|Batched queries and very deep nesting could be used to exhaust the gateway|Apply depth and complexity limits at the gateway itself.|

---

## Slide 13 — Plan for the Next 3 Weeks

**Planned Tasks:**

- **Task 1** — Finalise system architecture diagram and component boundaries — [Name 1, Name 2]
- **Task 2** — Set up the vulnerable test GraphQL API in Docker with seeded multi-user data — [Name 3]
- **Task 3** — Build the first working proxy that intercepts, parses and forwards a GraphQL request unchanged — [Name 4]
- **Task 4** — Implement the query normaliser: fragment expansion and alias stripping — [Name 2]
- **Task 5** — Write the first version of the ownership scoring rules and test them by hand on 10 real schemas — [Name 1]
- **Task 6** — Prepare a working demo of one blocked BOLA request for the next review — [All members]

---

## Slide 14 — References

1. O. Hartig and J. Pérez, "Semantics and Complexity of GraphQL," _Proc. World Wide Web Conference (WWW)_, 2018.
2. O. Hartig and J. Pérez, "An Initial Analysis of Facebook's GraphQL Language," _AMW_, 2017.
3. E. Wittern et al., "An Empirical Study of GraphQL Schemas," _International Conference on Service-Oriented Computing (ICSOC)_, 2019.
4. O. Tsai et al., "GraphQLer: Context-Aware Security Testing for GraphQL APIs," 2025.
5. Liu et al., "PrediQL: LLM-Guided Fuzzing for GraphQL APIs," 2025.
6. L. Lambers et al., "Taint Analysis for Graph APIs Focusing on Broken Access Control," _International Conference on Graph Transformation (ICGT)_, 2024.
7. D. Hofer et al., "Rewriting Graph-DB Queries to Enforce Attribute-Based Access Control," _DEXA_, 2023.
8. D. Hofer et al., "An Intermediate Representation for Rewriting Cypher Queries," _DEXA Workshops_, 2023.
9. Perera et al., "Enhancing GraphQL Security Using LLMs and CNNs," 2025.
10. L. Karimi et al., "An Automatic Attribute-Based Access Control Policy Extraction from Access Logs," _IEEE Transactions on Dependable and Secure Computing_.
11. A. Kaur, "BOLA in the Wild: A Taxonomy from 100+ Bug Bounty Disclosures," 2026.
12. A. Carossio and T. Kalos (Escape), "GraphQL Vulnerabilities in the Wild," _GraphQLConf_, 2023.
13. "A Comprehensive Study of GraphQL Security Challenges," 2025.
14. OWASP, _API Security Top 10 — API1:2023 Broken Object Level Authorization_, 2023.
15. Apollo GraphOS Router — Authorization Documentation, Apollo GraphQL.
16. Hasura — Row-Level Permissions Documentation.
17. Open Policy Agent — GraphQL Authorization Documentation.
18. HackerOne Report #2207248 — IDOR in Shopify GraphQL billing queries.
19. CVE-2024-39895 — Directus alias-based denial of service.

_(Check the exact author names, page numbers and DOIs before the final slide — a few of these came from secondary summaries.)_

---

## Quick tips for tomorrow

- The rubric marks **clarity of problem statement**, **quality of literature survey**, **feasibility of plan**, **inputs/outputs**, **tools**, **deliverables**, **individual contribution**, **communication**, and the **Excel sheet**. There is a mark for each — do not skip a section even if it feels thin.
- If asked _"why not just fix the resolvers?"_ — answer: a real API has thousands of them, and asking every developer to never once forget is not a security strategy.
- If asked _"how is this different from Apollo/Hasura?"_ — answer: Apollo checks roles, not ownership. Hasura enforces ownership but only because it **is** the backend. We work in front of any existing server.
- If asked _"what is genuinely new?"_ — say it narrowly: **working out ownership from the schema's type structure**. Do not claim "automatic authorization is new" — the policy-mining literature would contradict that.
