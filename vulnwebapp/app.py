import typing

import strawberry
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from strawberry.fastapi import GraphQLRouter

import database


@strawberry.type
class Product:
    id: strawberry.ID
    name: str
    price: float


@strawberry.type
class User:
    id: strawberry.ID
    name: str
    email: str


@strawberry.type
class Order:
    id: strawberry.ID
    total: float
    shipping_address: str

    @strawberry.field
    def owner(self) -> User:
        conn = database.get_connection()
        row = conn.execute(
            "SELECT u.* FROM users u "
            "JOIN orders o ON o.owner_id = u.id WHERE o.id = ?",
            (self.id,),
        ).fetchone()
        conn.close()
        return User(id=row["id"], name=row["name"], email=row["email"])

    @strawberry.field
    def product(self) -> Product:
        conn = database.get_connection()
        row = conn.execute(
            "SELECT p.* FROM products p "
            "JOIN orders o ON o.product_id = p.id WHERE o.id = ?",
            (self.id,),
        ).fetchone()
        conn.close()
        return Product(id=row["id"], name=row["name"], price=row["price"])


def current_user(info: strawberry.Info) -> typing.Optional[dict]:
    request: Request = info.context["request"]
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[len("Bearer "):]
    conn = database.get_connection()
    row = conn.execute("SELECT * FROM users WHERE token = ?", (token,)).fetchone()
    conn.close()
    return dict(row) if row else None


def order_from_row(row) -> Order:
    return Order(
        id=row["id"],
        total=row["total"],
        shipping_address=row["shipping_address"],
    )


@strawberry.type
class Query:

    @strawberry.field
    def me(self, info: strawberry.Info) -> typing.Optional[User]:
        user = current_user(info)
        if not user:
            return None
        return User(id=user["id"], name=user["name"], email=user["email"])

    @strawberry.field
    def my_orders(self, info: strawberry.Info) -> typing.List[Order]:
        user = current_user(info)
        if not user:
            return []
        conn = database.get_connection()
        rows = conn.execute(
            "SELECT * FROM orders WHERE owner_id = ? ORDER BY id", (user["id"],)
        ).fetchall()
        conn.close()
        return [order_from_row(row) for row in rows]

    @strawberry.field
    def order(self, info: strawberry.Info, id: strawberry.ID) -> typing.Optional[Order]:
        user = current_user(info)
        if not user:
            return None

        conn = database.get_connection()
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (id,)).fetchone()
        conn.close()
        if not row:
            return None
        return order_from_row(row)

    @strawberry.field
    def user(self, info: strawberry.Info, id: strawberry.ID) -> typing.Optional[User]:
        caller = current_user(info)
        if not caller:
            return None

        conn = database.get_connection()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (id,)).fetchone()
        conn.close()
        if not row:
            return None
        return User(id=row["id"], name=row["name"], email=row["email"])


@strawberry.type
class Mutation:

    @strawberry.mutation
    def update_order_address(
        self, info: strawberry.Info, id: strawberry.ID, address: str
    ) -> typing.Optional[Order]:
        user = current_user(info)
        if not user:
            return None

        conn = database.get_connection()
        conn.execute(
            "UPDATE orders SET shipping_address = ? WHERE id = ?", (address, id)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (id,)).fetchone()
        conn.close()
        if not row:
            return None
        return order_from_row(row)


schema = strawberry.Schema(query=Query, mutation=Mutation)

graphql_app = GraphQLRouter(schema)

app = FastAPI(title="VulnShop")
app.include_router(graphql_app, prefix="/graphql")


@app.get("/")
def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    database.setup()
    print("VulnShop running on http://localhost:8000")
    print("GraphQL endpoint: http://localhost:8000/graphql")
    uvicorn.run(app, host="0.0.0.0", port=8000)
