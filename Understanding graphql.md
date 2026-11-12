
### Journey of a Graphql query :

User clicks button
        │
        ▼
Event handler fires (frontend JS)
        │
        ▼
Pre-written query string put into an HTTP POST  ──► sent to /graphql
                                                          │
                                                    server pipeline
                                                    (parse→validate→execute→resolvers→DB)
                                                          │
        ┌──────────  JSON response  ◄──────────────────┘
        ▼
Frontend renders JSON into visible HTML
        │
        ▼
User sees the result


### can the user or attacker directly access the /graphql endpoint and write queries ?

- Yes
- The `/graphql` endpoint is just a URL on the internet that accepts HTTP POST requests. Anyone who knows the URL can send requests to it directly — **completely bypassing the website's frontend, buttons, and pre-written queries**
- The button-clicking UI is _one_ way to reach the endpoint, but it's not the _only_ way, and the server cannot tell the difference between a request from your nice frontend and a request an attacker typed by hand.

- The server just sits there receiving POST requests. It has no way to verify "this came from my official button." A request is a request.

- The frontend — the website, the buttons, the JavaScript — all runs on the **user's own computer**, in their browser. That means it is fully visible and fully controllable by whoever is using it. An attacker can:

	- Open browser DevTools and read every query the site sends.
	- Copy that query, change it, and resend it.
	- Skip the browser entirely and hit `/graphql` with any tool that sends HTTP

- **An attacker (or any developer) can send queries directly using:**

	- **curl** — a command-line tool. One line sends a raw query:
	
	```bash
	  curl -X POST https://api.example.com/graphql \
	    -H "Content-Type: application/json" \
	    -H "Authorization: Bearer <their-own-token>" \
		-d '{"query":"{ order(id: 125){ total shippingAddress } }"}'
	```
	
	- **Postman / Insomnia** — GUI apps built for exactly this: typing and sending API requests.
	- **Browser DevTools** — read the real query, edit it, replay it.
	- **GraphiQL / Apollo Sandbox** — if the endpoint exposes a query playground (many do in development), an attacker gets a ready-made query editor with autocomplete.
	- **Introspection** — if enabled, they send `{ __schema { types { name fields { name } } } }` and the server _hands them the entire schema_ — every type, field, and object they could ask for. A complete map of the attack surface, free.

- **"anyone can send queries" doesn't mean "anyone can get data." Two gates stand in the way:**
	
	- **Authentication** — most `/graphql` endpoints require a valid token, so a total stranger with no account is usually rejected before anything runs. That part often works fine.
	- **Authorization** — this is the gate that's frequently broken. The attacker passes authentication (they have a real account/token) but the server fails to check whether they own the specific object requested.

### **using GraphQL does not mean your data is stored as a graph** so then what's the "Graph" in GraphQL ??


**GraphQL stores data in ordinary tables, but lets you _see and query_ that data as a graph of connected things — so instead of asking separate endpoints for separate pieces, you start at one thing and walk along its relationships, taking exactly what you need in a single request.**

- The "graph" in GraphQL is not about how data is _stored_. It's about how data is _connected_.
- GraphQL looks at your existing data and sees the _relationships_ between things as a graph — and lets you travel along those relationships when you ask for data.

- eg. `User ——placed——> Order ——contains——> Product`

- GraphQL just noticed that **your application's data naturally forms this shape** — everything is connected to other things — and built a query language around that idea.

- GraphQL's whole idea is: **take those hidden links between tables and treat them as walkable connections in a graph.** The tables stay exactly as they are. GraphQL lays a "map of connections" _on top_ of them. So:
	- Stored form: flat tables with matching ID numbers (unchanged).
	- GraphQL's view: a graph of things connected by those relationships.

- Where the graph is actually written down: **the schema**
	- That "map of connections" isn't imaginary — the developer writes it out explicitly in something called the **schema**
	- The schema lists each type of thing and, importantly, which other things it connects to:

				`type User {
				  name
				  orders     ← a User connects to their Orders
				}
				
				type Order {
				  total
				  product    ← an Order connects to a Product
				  owner      ← an Order connects back to a User
				}
				
				type Product {
				  name
				}`

	- `User` links to `Order` (via `orders`), `Order` links to `Product` (via `product`). **Each of those linking fields is an edge in the graph.** The schema _is_ the graph, written as text. It's the map that says "from here, you can travel to there."

### How querying uses the graph ?

- When you ask for data, you're **tracing a path through the graph**, starting at one point and walking along the connections:

		`{
		  user(id: 1) {        ← start at the User node
		    name
		    orders {           ← walk the "orders" connection
		      total
		      product {        ← walk the "product" connection
		        name
		      }
		    }
		  }
		}`

- You started at a user, walked to their orders, then walked from each order to its product — following the lines in the graph, grabbing what you want at each stop. One request, walking wherever the connections lead.
- **Behind the scenes, each "walk" quietly runs a normal database lookup on the flat tables (fetch the user, then fetch their orders, then each order's product). But _you_ don't think about tables or joins — you just think "start here, follow these connections." The graph is the mental model you get to use; the tables do the actual work underneath.**

![[Pasted image 20260713140737.png]]

### The three operation types in GraphQL 

- **Query**  
	- A _read_. Asking for data without changing anything. 
	- Queries never modify data — they only fetch. 

- **Mutation**  
	- A _write_. Anything that changes data — create, update, or delete.
	- "Place an order," "update my email," "delete this post." 
	- If a query is _reading_ from the database, a mutation is _writing_ to it. 
	- One key rule: mutations run one at a time, in order (unlike queries, which can run in parallel), because writes mustn't collide.

- **Subscription**  
	- A _live feed_.
	- Instead of asking once and getting one answer, you subscribe and the server keeps pushing new data to you as things happen. 
	- "Notify me whenever a new message arrives." 
	- Used for real-time features like chat or live scores. It stays connected, rather than one-and-done.

## Execution Terms (how it actually runs)

| Term                          | What it is                                                                                                                                                                                                                                                                   |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Resolver**                  | The worker function behind each field. When a field is requested, its resolver fetches the value — often by querying the real database. Every field has one (you write the important ones; the rest use a default). Resolvers are where GraphQL connects to the actual data. |
| **Root types / entry points** | Three special starting-point types — `Query`, `Mutation`, `Subscription` — that list the operations a client is allowed to start with. Every request begins at one of these. They are the "front doors" into the graph.                                                      |

## Query-Writing Terms (things seen inside a query)

| Term          | What it is                                                                                                                                                                                 | Example                                                             |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------- |
| **Argument**  | Extra input passed to a field to narrow it down. Tells the field _which_ item to fetch.                                                                                                    | `user(id: 5)` → `id: 5` is the argument                             |
| **Variable**  | A placeholder for a value, passed separately from the query text, so the same query can be reused with different inputs. Written with `$`. (Security note: IDs often arrive as variables.) | `user(id: $id)`, with `id = 5` supplied alongside                   |
| **Alias**     | Renames a field in the response. Also lets the same field be requested twice with different arguments. (Relevant to the project — can disguise what is really being asked.)                | `myName: name` → result labelled `myName`                           |
| **Fragment**  | A reusable, named bundle of fields, so the same set is not rewritten each time. (Relevant to the project — can hide structure.)                                                            | `fragment basicInfo on User { name email }`, used as `...basicInfo` |
| **Directive** | A small instruction attached to a field that changes its behavior, written with `@`. Built-in ones conditionally include/exclude a field; custom ones sometimes add permission checks.     | `@skip`, `@include`, custom `@auth`                                 |
### BOLA Attack flow :

![[Pasted image 20260713115929.png]]

### GraphQL Authorization: Current Techniques & Their Flaws

- **Inline resolver checks** — an `if` statement inside each resolver (e.g. `if (user.id !== post.authorId) throw`). Official guidance flags this as suitable only for prototypes.
- **Field-level checks / returning null** — hide individual fields (salary, email) from unauthorized users, often by returning null instead of an error.
- **Schema directives** — declarative annotations like `@auth(requires: ADMIN)` or `@hasRole` placed directly on types/fields.
- **Middleware layers** — schema-wide rule engines (e.g. GraphQL Shield) that apply permission rules across all resolvers.
- **External policy engines / policy-as-code** — decoupled authorization via OPA, Oso, Cerbos, or Zanzibar-style ReBAC (SpiceDB, OpenFGA); the app asks "can user X access object Y?" and the engine decides.
- **Query-cost / depth limits** — cap nesting depth and query complexity to blunt DoS (protects availability, not object access).

### Flaws & Weaknesses in Current Strategies

- **Only checks login, not ownership** — the system confirms the user is logged in, then assumes they can access anything they ask for.
- **Treats "having the ID" as "allowed to see it"** — if a request asks for `id: 125`, the server returns it without checking who owns object 125.
- **The check must be added at every level of a query** — one request touches many objects, so forgetting the check on even one of them leaks data.
- **Only some routes to an object are protected** — objects can be reached through multiple paths in the graph; developers guard one path and forget another.
- **Assumes the schema itself provides security** — designing the schema is not the same as enforcing access; GraphQL does neither automatically.
- **Rules differ across services** — in microservice setups, the same object is checked differently (or not at all) by different teams.
- **Trusts the frontend to hide data** — hiding fields in the UI does nothing; attackers bypass the frontend and call the API directly.
- **Role-based tools can't express ownership** — RBAC and directives handle "admin vs user" well, but need endless extra roles to answer "does this user own this object?"
- **Policy engines must be constantly fed ownership data** — tools like OPA/ReBAC only know who owns what if every relationship is continuously synced into them.
- **Scanners can't detect it** — BOLA is a logic flaw, not a bad input, so automated security tools miss it; it only shows up at runtime.
- **Relies on humans never making a mistake** — correct protection needs every developer to add the right check in thousands of places and never once forget.




