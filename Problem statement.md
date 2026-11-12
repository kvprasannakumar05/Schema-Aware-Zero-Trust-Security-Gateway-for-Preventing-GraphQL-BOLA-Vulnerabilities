
GraphQL APIs cannot reliably prevent an authenticated user from accessing data objects belonging to other users, because the required ownership check is scattered across thousands of backend resolvers where it is routinely omitted. Existing perimeter defences cannot compensate, as they are unable to interpret GraphQL's nested query structure or the alias and fragment obfuscation used to disguise such requests.

**Problem Statement**

1. GraphQL APIs cannot reliably prevent an authenticated user from accessing objects owned by other users — the vulnerability ranked #1 in the OWASP API Security Top 10.
2. The ownership check is scattered across thousands of resolvers where it is easily omitted, and perimeter defences cannot detect the attack because they cannot parse GraphQL's nested, obfuscated queries.


GraphQL APIs have no centralised way to verify that an authenticated user owns the specific object they request, leaving object-level authorization dependent on manual checks in thousands of resolvers that perimeter defences cannot see or enforce.

