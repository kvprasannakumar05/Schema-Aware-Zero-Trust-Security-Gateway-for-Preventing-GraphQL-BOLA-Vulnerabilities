
**Project:** Schema-Aware Zero-Trust Security Gateway for Preventing GraphQL BOLA Vulnerabilities

---
## 1. What This Survey Covers

We reviewed research across six areas that together define the problem space:

- **Foundations** — how GraphQL works, formally described.
- **Real-world security** — studies measuring how insecure GraphQL APIs actually are.
- **Finding flaws** — tools that detect authorization bugs before deployment.
- **Enforcing rules** — techniques that block unauthorized queries at runtime.
- **Creating rules automatically** — research on generating access-control policies without hand-writing them.
- **Industry tools** — what companies use in production today.

Sources were taken from arXiv, ACM and Springer conference proceedings (WWW, ICSOC, DEXA, ICGT), OWASP references, and published vendor security research.

---

## 2. Foundations: How GraphQL Works

|Paper|What it does|Limitation|Why it matters to us|
|---|---|---|---|
|[Hartig & Pérez, _An Initial Analysis of Facebook's GraphQL Language_](https://www.olafhartig.de/files/HartigPerez_WWW2018_Preprint.pdf) (AMW 2017)|Gives the first academic description of GraphQL as a query language.|It only describes the language. It contains no security model at all.|It establishes GraphQL as a serious subject for academic study.|
|[Hartig & Pérez, _Semantics and Complexity of GraphQL_](https://www.olafhartig.de/files/HartigPerez_WWW2018_Preprint.pdf) (WWW 2018)|The main formal paper on GraphQL. It defines exactly how queries are executed and proves how expensive that execution can be.|It studies what GraphQL can express and how costly queries are. It does not cover authorization at all.|It proves that GraphQL's own theory has no built-in way to control who may access what. That missing piece is what our gateway supplies.|
|[Wittern et al., _An Empirical Study of GraphQL Schemas_](https://arxiv.org/pdf/1907.13012) (ICSOC 2019)|Studies 16 commercial schemas and 8,399 schemas collected from GitHub. Finds that most APIs can be crashed by complex queries. Also finds that developers follow consistent "organic" naming habits.|It looks at schema design and denial-of-service risk. It does not examine ownership or authorization.|**Very important for us.** Their schema collection is the natural benchmark for testing our ownership inference. Their finding on naming habits supports the heuristics our inference depends on.|

---

## 3. How Bad Is It in Practice

|Source|What it found|Limitation|Why it matters to us|
|---|---|---|---|
|[_GitHub Data Exposure Using the GraphQL Security Design Flaw_](https://arxiv.org/pdf/2005.13448)|Shows a flaw in GraphQL's design that allowed access to data that should have been blocked, demonstrated on GitHub.|Focuses on one case rather than a broad study.|It proves that unauthorized access can come from GraphQL's design, not only from coding mistakes.|
|Escape (Carossio & Kalos), _GraphQL Vulnerabilities in the Wild_ (GraphQLConf 2023)|Scanned more than 1,500 public GraphQL endpoints. Found over 46,000 security issues reachable without logging in, of which 10% were critical. About 40% were classic API problems such as broken access control. Leaked data included emails, phone numbers, passport details, and cloud access tokens.|This is industry research, not peer-reviewed, and the full method was not published.|It is the strongest available evidence of how widespread the problem is.|
|[Kaur, _BOLA in the Wild: A Taxonomy from 100+ Bug Bounty Disclosures_](https://arxiv.org/abs/2605.25865) (2026)|Classifies 107 confirmed BOLA reports from 2021 to 2026. Confirms the root cause is that servers never check whether the user owns the specific object requested. Shows that GraphQL global IDs are attacked by decoding them, changing the number, and re-encoding them.|It classifies past incidents. It proposes no defence.|**Very important for us.** It grounds our threat model in verified attacks and directly justifies decoding global IDs inside our gateway.|
|_A Comprehensive Study of GraphQL Security Challenges_ (2025)|Surveys the full GraphQL attack surface, including injection, denial of service, broken authentication and authorization, and schema exposure.|It is a survey only. It builds and tests nothing.|Useful background for scoping which threats we cover.|

---

## 4. Finding Flaws (Detection Research)

All work in this group shares one limitation: **it finds problems before deployment, but protects nothing once the system is live.**

|Paper|What it does|Limitation|Why it matters to us|
|---|---|---|---|
|[Tsai et al., _GraphQLer_](https://arxiv.org/abs/2504.13358) (2025)|Described as the first context-aware security testing tool for GraphQL. It builds a dependency graph linking queries, mutations, and objects, then chains operations together to expose authorization flaws and access-control bypasses. It found a known CVE and new issues in production APIs.|It is a testing tool. It discovers flaws but never blocks a live request. A flaw it misses stays fully exploitable.|**Closest academic work to ours.** Its dependency graph supports our type-graph approach. Our clear difference is that we _enforce_, while they _discover_.|
|[Liu et al., _PrediQL_](https://arxiv.org/html/2510.10407v2) (2025)|The first LLM-guided fuzzer for GraphQL. Detects a wider range of flaws than GraphQLer, including logic and context-dependent bugs, and beats ZAP, BurpSuite, EvoMaster, and GraphQLer in coverage.|Works only at testing time. Being LLM-driven, its results are probabilistic rather than guaranteed.|It shows the research field is focused almost entirely on detection, which leaves runtime enforcement open.|
|[Lambers et al., _Taint Analysis for Graph APIs_](https://arxiv.org/abs/2501.08947) (ICGT 2024)|The first systematic taint-analysis method for broken access control in graph APIs, tested on part of the GitHub GraphQL API.|It analyses code and schemas offline. It does not inspect live traffic.|**Closely related to our design.** Our ownership-taint tracking uses a similar idea, but we apply it live on each request instead of offline.|
|[Perera et al., _Enhancing GraphQL Security Using LLMs and CNNs_](https://arxiv.org/pdf/2508.11711) (2025)|Combines static analysis with machine learning inside an API gateway to detect malicious queries in real time. States plainly that static analysis, rate limiting, and normal WAFs give limited protection.|Machine learning produces false positives and false negatives. Their own load testing showed noticeable slowdown on CPU-only servers. It targets injection payloads, not object ownership.|**Sits in the same place as us but does a different job.** They classify payloads with ML; we enforce ownership deterministically. Their measured slowdown is why we cache ownership results.|
|Industry tools: OWASP ZAP, BurpSuite, EvoMaster, Schemathesis, GraphQL-Cop|Standard scanners with GraphQL support.|The PrediQL paper notes they mostly send generic payloads and introspection attacks, and do not follow multi-step workflows.|They form the baseline our work is measured against.|

---

## 5. Enforcing Rules (Query Rewriting Research)

|Paper|What it does|Limitation|Why it matters to us|
|---|---|---|---|
|[Hofer et al., _Rewriting Graph-DB Queries to Enforce Attribute-Based Access Control_](https://doi.org/10.1007/978-3-031-39847-6_34) (DEXA 2023)|Intercepts an unsafe query before it reaches the database, builds its syntax tree, and adds filters so only permitted data is returned.|It works on Cypher and graph databases, not GraphQL APIs. It assumes the system controls how the query is executed.|**This is the academic basis of our enforcement idea.** The fact that it stops at graph databases is exactly the gap we fill for GraphQL.|
|[Hofer et al., _An Intermediate Representation for Rewriting Cypher Queries_](https://doi.org/10.1007/978-3-031-39689-2_9) (DEXA 2023 Workshops)|Explains the syntax-tree representation used to insert authorization filters while the query runs.|Again limited to graph databases.|It proves that inserting policy at the syntax-tree level is technically workable.|
|[_Comparison of Access Control Approaches for Graph-Structured Data_](https://arxiv.org/abs/2405.20762) (2024)|Compares query rewriting against other fine-grained access-control methods for graph data.|A survey, so it builds nothing new.|It helps us position our technique among the alternatives.|

---

## 6. Creating Rules Automatically — The Key Comparison

This section decides whether our first novel contribution stands. **Automatic policy creation is a well-established field.** We must therefore be precise about how our approach differs.

|Paper|What it does|Limitation|
|---|---|---|
|[Karimi et al., _ABAC Policy Extraction from Access Logs_](https://arxiv.org/pdf/2003.07270) (IEEE TDSC)|Learns access-control rules automatically by finding patterns in access logs, then prunes and refines those rules.|**It needs historical access logs.** A newly deployed system has none. Worse, logs record what users _did_ do, so any existing BOLA flaw is learned as normal, permitted behaviour.|
|PAMMELA, DLBAC, and related work|Generate or learn policies using machine learning, in one case by copying rules from a similar organisation.|All still depend on existing authorization data being available.|
|[_LLMs for ABAC Policy Mining_](https://www.arxiv.org/pdf/2511.18098) (2025)|Tests whether large language models can mine policies. Confirms that bottom-up mining works from access logs or legacy access-control lists.|The authors report that scalability remains limited.|

**Where each approach gets its information, and whether we can use it:**

|Information source|Used by|Can we use it?|
|---|---|---|
|Access logs|Karimi et al. and most policy mining|**No.** Not available at deployment, and it treats existing flaws as correct behaviour.|
|Existing access-control lists|Bottom-up policy mining|**No.** This assumes we already have the policy we are trying to create.|
|Written specifications|LLM-based policy generation|**No.** Such documents rarely exist in practice.|
|**The schema's type structure**|**No prior work found**|**Yes.** The schema is always available, either as a file or through introspection.|

**Conclusion.** Working out ownership from the _structure of the schema_ — finding the user type, scoring which relationships mean ownership, and tracing indirect paths — appears to be unexplored. This is our defensible claim. We must state it in these exact terms, because a broader claim such as "automatic authorization is new" would be contradicted by the policy-mining literature above.

---

## 7. What Industry Uses Today

|Tool|What it does|Limitation|
|---|---|---|
|[Apollo GraphOS Router](https://www.apollographql.com/docs/graphos/routing/security/authorization)|The leading commercial GraphQL gateway with built-in authorization. It reads the user's claims and permission scopes, such as `read:profiles`, to decide which fields and types are allowed.|**It checks roles and scopes, not ownership.** It can answer "does this user hold permission X?" but not "does this user own order 124?" It also requires adding directives to the schema, which means changing the backend, and it needs an Enterprise licence.|
|Hasura|The closest competitor in capability. It genuinely enforces row-level ownership using rules such as `{ "id": { "_eq": "X-Hasura-User-Id" } }`.|**Hasura is the backend, not a gateway.** It generates the API from the database and can only enforce rules because it controls the query. It cannot be placed in front of an existing GraphQL server, and every rule is configured by hand per table.|
|Inigo|A commercial GraphQL gateway. Argues that ordinary API gateways cannot see GraphQL-specific threats, and offers denial-of-service protection and sensitive-data controls.|Focused on denial of service and data protection. Per-object ownership is not a documented feature.|
|Open Policy Agent (OPA)|A general policy engine. It parses the GraphQL query into a syntax tree and checks it against written policy on every request.|Policies must be hand-written in the Rego language. It normally runs inside the server. It does not undo alias or fragment disguises, and it does not look up ownership by itself.|
|GraphQL Shield and schema directives|Apply role-based rules declaratively across the schema.|Community reports note that once per-object logic is added, directive code becomes hard to read and eventually unmaintainable.|
|Official guidance (GraphQL.js, OWASP)|Advises putting authorization in the business-logic layer, and requires checking permissions on both nodes and edges.|This is precisely the scattered, manual approach whose failure our project addresses.|

---

## 8. Research Gaps We Identified

- **Detection is well studied, but runtime enforcement is not.** GraphQLer, PrediQL, and taint analysis all find flaws before deployment. None of them protects a running system, so any flaw they miss stays fully exploitable.
- **Syntax-tree enforcement has only been proven for graph databases.** Hofer et al. showed it works for Cypher, where the engine controls query execution. Nothing equivalent exists at the GraphQL perimeter, where the gateway has no such control.
- **Gateways enforce roles, not ownership.** Apollo's scope model and directive-based rules cannot express per-object ownership without creating an unmanageable number of roles. Real ownership enforcement exists only inside backend engines such as Hasura, which means replacing your backend to get it.
- **Automatic rule creation depends on data we do not have.** Every established method needs access logs, legacy access-control lists, or written specifications. Nobody has tried using the schema's own structure, even though it is always available.
- **No system checks every path to an object.** OWASP requires checking both nodes and edges, and documented cases show developers protecting one route while forgetting another. No existing tool verifies authorization along every possible path through a nested query.
- **No enforcement layer removes query disguises first.** Alias multiplication (as in Directus CVE-2024-39895), nested fragments, IDs hidden in variables, and encoded global IDs are all documented attack methods, yet no surveyed enforcement tool normalises against all of them before checking policy.

---

## 9. Why This Work Matters

**The threat is real and highly ranked.**

- BOLA has been the number one risk in the OWASP API Security Top 10 since 2019.
- Researchers have classified 107 confirmed BOLA disclosures between 2021 and 2026.
- Shopify paid a $5,000 bounty for an IDOR flaw on its GraphQL billing queries (HackerOne #2207248).
- In 2026, an automated agent extracted an airline's entire booking database, including passenger records and the ability to modify live itineraries, in 15 minutes with no human guidance.

**Existing tools cannot see these attacks.**

- Analysis of the airline case notes that ordinary scanners are blind to this flaw class, because the attack uses valid syntax against legitimate endpoints.
- A 2025 industry report found no GraphQL-specific breaches in one quarter, but explained this as a gap in detection rather than genuine safety, since a single dynamic endpoint hides activity from traditional security tools. In other words, the apparent silence is itself evidence of the problem.

**The affected systems are widespread and sensitive.**

- GraphQL runs in production at Meta, GitHub, Shopify, PayPal, Netflix, Airbnb, LinkedIn, Coursera, and The New York Times.
- Adoption is heaviest in mobile, fintech, and healthcare, which are the sectors where leaking one person's data to another carries the greatest legal and human cost.

**Our scientific contribution.**

- The project addresses five of the six gaps listed above with a single system.
- It also produces a measurable result that is interesting in its own right: the percentage of object types whose ownership can be inferred automatically across a large collection of real GraphQL schemas. The Wittern et al. corpus makes this evaluation directly possible.

---

## 10. How We Position This Project

> Earlier research establishes that BOLA is real, widespread, and the top-ranked API security risk, and that GraphQL's design makes it worse. Detection research such as GraphQLer, PrediQL, and taint analysis can find these flaws before deployment, but cannot stop them being exploited afterwards. Enforcement research by Hofer and colleagues proves that adding access-control filters at the syntax-tree level works, but only for graph databases where the engine controls execution. Commercial gateways such as Apollo GraphOS Router and Inigo enforce roles and scopes rather than object ownership, while true ownership enforcement exists only inside backend engines like Hasura, which must replace the backend entirely. Policy-mining research can generate rules automatically, but always requires access logs or existing policies that are unavailable at deployment and that would treat current flaws as acceptable behaviour.
> 
> This project fills the remaining gap. It is a **language-independent gateway** that **works out ownership rules from the structure of the schema**, which is the one piece of information always available, and then **enforces those rules at every step of every path through a query**, even when aliases, fragments, variables, or encoded IDs are used to disguise it, and **without requiring any change to the backend**.

---
