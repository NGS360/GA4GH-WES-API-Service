# wes-schemas

Pydantic models for the GA4GH Workflow Execution Service wire format.

This package is the contract. The WES server declares these as its
`response_model`s, `wes-client` parses responses into these same classes, and
consumers type against them — so a `RunLog` is one class object everywhere
rather than three lookalikes that have to be kept in sync by hand.

It depends on pydantic and nothing else. Keep it that way: every dependency
added here lands on the server, the client, and every downstream consumer.

```python
from wes_schemas import RunListResponse, RunLog, State
```

Changing a model here changes the published API. Additive changes (new optional
field) are safe for existing consumers; renaming or removing a field, or
narrowing a type, is a breaking change and needs a major version bump.
