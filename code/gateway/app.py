import time
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

import config
import inference
import normalizer
import enforcer

MODEL = None


def _load_model():
    deadline = time.time() + config.BACKEND_WAIT_SECONDS
    waited = False
    while True:
        try:
            return inference.build_ownership_map()
        except Exception:
            if time.time() >= deadline:
                print("")
                print("Cannot reach the backend at " + config.BACKEND_URL)
                print("Start it first, in another terminal:")
                print("    cd vulnshop")
                print("    python app.py")
                print("")
                raise SystemExit(1)
            if not waited:
                print("Waiting for the backend at " + config.BACKEND_URL + " ...")
                waited = True
            time.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global MODEL
    if MODEL is None:
        MODEL = _load_model()
    print("Ownership map (built from the schema):")
    print("  identity type:", MODEL["identity"])
    for type_name, info in MODEL["ownership"].items():
        extra = info.get("path", "")
        print("   -", type_name, "->", info["tier"], extra)
    yield


app = FastAPI(title="BOLA Gateway", lifespan=lifespan)


@app.post("/graphql")
async def graphql(request: Request):
    if MODEL is None:
        return _refuse("gateway not ready")

    try:
        body = await request.json()
    except Exception:
        return _refuse("could not read the request body")
    if not isinstance(body, dict):
        return _refuse("could not read the request body")

    query = body.get("query") or ""
    variables = body.get("variables") or {}
    token = _token(request)

    try:
        operations = normalizer.normalize(query, variables)
    except Exception:
        return _refuse("could not parse the query")

    if not config.ALLOW_INTROSPECTION and normalizer.contains_introspection(operations):
        return _refuse("introspection is disabled")
    if normalizer.max_depth(operations) > config.MAX_DEPTH:
        return _refuse("query too deep")
    if normalizer.count_fields(operations) > config.MAX_FIELDS:
        return _refuse("query too large")
    if token is None:
        return _refuse("authentication required")

    try:
        decision = enforcer.enforce(operations, token, MODEL)
    except Exception:
        return _refuse("not found")
    if not decision.allowed:
        return _refuse("not found")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                config.BACKEND_URL + "/graphql",
                json=body,
                headers={
                    "Authorization": "Bearer " + token,
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
        return JSONResponse(resp.json())
    except Exception:
        return _refuse("backend unavailable")


@app.get("/graphql")
async def graphql_get(request: Request):
    accept = request.headers.get("Accept", "")
    if "text/html" not in accept:
        return JSONResponse(
            {"errors": [{"message": "this endpoint accepts POST only"}]},
            status_code=405,
        )
    return await _proxy_get("/graphql")


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@app.get("/")
@app.get("/static/{path:path}")
async def passthrough(request: Request, path: str = ""):
    return await _proxy_get(request.url.path)


async def _proxy_get(path):
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(config.BACKEND_URL + path)
    except Exception:
        return Response(content="backend unavailable", status_code=502)
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type"),
    )


def _token(request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):]
    return None


def _refuse(message):
    return JSONResponse({"errors": [{"message": message}]})


if __name__ == "__main__":
    print("BOLA gateway on http://localhost:%d" % config.GATEWAY_PORT)
    print("Protecting backend at", config.BACKEND_URL)
    MODEL = _load_model()
    uvicorn.run(app, host="0.0.0.0", port=config.GATEWAY_PORT)
