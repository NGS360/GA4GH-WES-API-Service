# wes-service

The GA4GH Workflow Execution Service server: FastAPI application, SQLAlchemy
models, and the Alembic migration chain.

See the [repository README](../../README.md) for setup, configuration, and
deployment.

## Layout

```
src/wes_service/     the application
alembic/             migrations (run from this directory)
tests/               unit and API tests, plus tests/contract/
```

## Its place in the workspace

Depends on `wes-schemas` for its response models — the same classes `wes-client`
parses into, so the two cannot drift into lookalike copies of each other.

It dev-depends on `wes-client`, and only dev-depends: `tests/contract/` drives the
real client against this app over `httpx.ASGITransport`, which is what catches a
route rename or a changed response model before a consumer does. Nothing in
`src/` may import `wes_client`.
