
First, what GraphQL is.

GraphQL is a query language for APIs. The easiest way to understand it is by comparison.

With a normal API, you call a web address, and the server decides what to send you. You take what you're given.

With GraphQL, you send a query that says exactly what you want — these fields, from this thing, and also these connected things — and the server sends back exactly that. Nothing extra.

And there's one more difference that matters a lot later. There's only one address. Not fifty endpoints for fifty different screens. One. Everything goes to a single URL.

Now, the word "graph" confuses people, so let me clear it up quickly. It does not mean your data is stored as a graph. Your data sits in ordinary tables, exactly like before.

What GraphQL does is draw a map over those tables.

In a database, a user and their order are linked by a number in a column. That link is real, but it's invisible — it's just a number sitting there. GraphQL turns that invisible number into a named path you can walk along. A User connects to their Orders. An Order connects to a Product.

So when you write a query, you're travelling. Start at a user, walk to their orders, walk from each order to its product. Pick up what you want at each stop. One request, walking wherever the connections lead.

That's the whole idea.

---

**[Why people moved from REST]**

So why did the industry move to this? Because the old way had four real problems, and on a phone they hurt.

**One — you get too much.** You ask for a user's name, and the server hands you thirty fields. Address, phone, settings, everything. You needed one field. You paid to download thirty.

**Two — you get too little.** You want a user, then their orders, then the products in those orders. That's three separate calls, one after another, each one waiting for the one before it. On a slow connection, that's the difference between an app that feels fast and an app that feels broken.

**Three — endpoints multiply.** Every new screen needs a slightly different mix of data, so the backend team writes another endpoint. Then another. They pile up and nobody deletes them.

**Four — versions.** You change something, you break the old apps, so you make version two. Version one lives forever, because somebody's still on it.

Facebook ran into all four at once building their mobile app. That's why they built GraphQL. And GraphQL genuinely fixes all four. One request instead of three. Only the fields you asked for. No endpoint sprawl. No version numbers.

It works. That's why GitHub and Shopify and a lot of others adopted it.

---

**[The problem with GraphQL]**

But here's the turn.

GraphQL's whole strength is that the client can walk freely across relationships. That is the point of it. Now think about what that means for security.

In the old way, one call touches one thing. In GraphQL, one request touches many objects, through many different paths. And every single one of those objects needs somebody to ask one question: _does this user actually own this?_

And here's the part that surprises people. **GraphQL does not ask that question.**

Not because of a bug. On purpose. GraphQL is a thin layer that describes how to fetch data. The official documentation says, in plain words, that authorization is your business logic — it belongs in your own code.

So the check has to be written by hand, inside every function that fetches an object. A real API has thousands of those functions.

Now go back to my opening story. That attacker isn't a stranger. They're a real customer with a real account and a real login. The server checks _who they are_ — and that works perfectly. It just never checks whether they _own_ order one two five.

Authentication works. Authorization is what breaks.

And the honest problem is this: expecting a thousand developers to write a perfect check in a thousand places, and never once forget — that isn't a security strategy. That's a guarantee that eventually somebody forgets.

---

**[Why we chose this problem statement]**

So that's the landscape. Now let me explain how we got from that to our actual problem statement, because we didn't start here.

We started much broader. We started with "GraphQL security," and read our way through the whole attack surface.

**First cut.** A lot of it is already solved. Attackers can crash a server with deeply nested queries — there are depth limits for that. They can read your entire schema through introspection — you turn introspection off in production. Injection attacks — well understood. Rate limiting — solved.

Those problems have answers. We didn't want to rebuild something that already exists.

**Second cut.** One problem kept coming back and had no clean answer: this one. Ownership.

And when we checked how serious it was, the numbers were hard to ignore. OWASP ranks it number one — not in the top ten, _number one_, in both their 2019 and their 2023 lists. A study this year went through two hundred publicly disclosed bug bounty reports and confirmed eighty-four real cases. Shopify paid five thousand dollars for exactly this bug in their billing queries.

And in June this year, a security firm pointed an autonomous AI agent at an airline. It began with nothing but a web address. No password, no documentation, no human helping it. It read the site's code, worked out how to get a session, asked the API to describe itself, spotted the missing ownership check, and confirmed it could read the entire passenger database — names, dates of birth, billing addresses, live bookings.

Fifteen minutes.

_(pause)_

**Third cut — and this is the one that actually shaped our statement.**

We found plenty of tools that _find_ this flaw. Testing tools, fuzzers, scanners. Good work, real research.

But every one of them finds the problem _before_ you go live. None of them stops the attack _while it's happening_. And a flaw a tester misses stays fully open.

So we asked the obvious next question: can't a firewall catch it at the edge?

No. And the reason is specific. A firewall reads flat text and web addresses. GraphQL sends one complex nested request to one single address. The firewall can't see the structure. It can't see which objects are being asked for. And even if it could — it has no idea who owns what.

That's the gap. Everything before deployment is well covered. Everything at the perimeter, while the attack is live, is not.
