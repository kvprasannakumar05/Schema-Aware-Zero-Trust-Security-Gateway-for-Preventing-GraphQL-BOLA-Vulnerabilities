**Novelty (Our Contribution)**

> Existing solutions enforce _roles and scopes_ at the gateway, or _object ownership_ only inside the backend engine. We introduce a language-independent perimeter gateway that derives ownership rules from the schema itself and enforces them on every object in every query path.

Four specific contributions:

1. **Automatic ownership inference from schema structure** — the gateway identifies the user type, scores which relationships denote ownership, and traces indirect ownership paths, generating the rules itself. All prior policy-automation work mines from access logs or existing policies, which are unavailable at deployment; the schema is the one artefact always present.
2. **Multi-path ownership verification** — ownership is checked at every node along every traversal path in a nested query, using taint propagation that drops "trusted" status when a query crosses into shared or third-party data. Existing tools check the object fetched, not the routes taken to reach it.
3. **Obfuscation-resistant normalisation** — aliases, fragments, variable-carried IDs, and encoded global IDs are resolved to their true form _before_ policy evaluation, defeating the disguise techniques documented in real BOLA exploits.
4. **Zero backend modification** — enforcement is deterministic, applied at the perimeter, and independent of the backend's language or framework. No resolver edits, no schema directives, no engine replacement.


--- 

​1. Defeating Alias Masking & Deep Fragments
​Existing security rules often fail because they evaluate the surface-level alias rather than the actual underlying resolver being invoked.
​Implementation Idea: The "Canonicalization" step must be the core engine of your gateway. Build an aggressive Abstract Syntax Tree (AST) parser that flattens all aliases, inline fragments, and named fragments into a standardized, unified format before the Zero Trust Policy is applied.  
​Engineering approach: Utilizing a systems-level programming language with strict typing, safe memory management, and zero-cost abstractions will be critical here. Parsing and flattening highly nested ASTs is computationally expensive; a high-performance system can recursively unravel the AST without introducing unacceptable latency or memory leaks.
​2. Thwarting Batched BOLA Attempts (Anti-CrackQL)
​Attackers applying web exploitation tactics often use query batching to bypass standard rate limits, packing hundreds of BOLA attempts (e.g., iterating through Account IDs 1000 to 1999) into a single HTTP request.
​Implementation Idea: Expand the "Ownership Verification" phase to include contextual rate-limiting. Instead of just tracking the number of HTTP requests, the gateway should assign a "cost" to the number of discrete objects being accessed within a single query. If a user attempts to access an abnormally high number of distinct objects in one go, the gateway terminates the request before it hits the backend.  
​3. Egress Error Sanitization
​A major drawback of existing GraphQL setups is that even when unauthorized queries are blocked, the server's exception handling leaks sensitive schema information or data types.
​Implementation Idea: Modify the proposed flow to be bidirectional. The gateway should not only inspect the ingress (incoming request) but also intercept the egress (outgoing response). If the backend GraphQL server throws an error (e.g., due to a malformed query that bypassed the initial check), the gateway catches the payload, strips out stack traces or field-level hints, and returns a generic, sanitized HTTP 403 or 400 error.  
​4. Cross-Request Attack Detection (Stateful Analysis)
​Standard gateways are stateless; they evaluate one request at a time.
​Implementation Idea: Introduce a short-term, high-speed memory cache (like Redis) into the gateway to track authorization failures over time. If User B requests User A's account and fails, the gateway flags it. If User B then requests User C, D, and E's accounts, the gateway recognizes the horizontal privilege escalation pattern and temporarily blacklists User B's JWT entirely.


--- 

- automatic ownership inference
- multipath ownership verification
