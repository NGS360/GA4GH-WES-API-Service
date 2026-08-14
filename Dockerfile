# Use python image with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install project into `/app`
WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Avoid .venv collisions in container
ENV UV_PROJECT_ENVIRONMENT=.venv

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Install third-party dependencies first, as a layer that caches independently of
# the source.
#
# Every workspace member's manifest is mounted, because uv resolves the workspace
# as a whole and the lockfile refers to all three. Manifests only, not their
# source, so editing application code does not invalidate this layer.
#
# --no-install-workspace skips building the members themselves; --no-install-project
# would skip only the root, and uv would then try to build the members here,
# before their source exists.
RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  --mount=type=bind,source=packages/wes-schemas/pyproject.toml,target=packages/wes-schemas/pyproject.toml \
  --mount=type=bind,source=packages/wes-client/pyproject.toml,target=packages/wes-client/pyproject.toml \
  --mount=type=bind,source=packages/wes-service/pyproject.toml,target=packages/wes-service/pyproject.toml \
  uv sync --locked --no-install-workspace --no-dev

# Add the source and install the server.
#
# --package wes-service installs the server and wes-schemas, and deliberately not
# wes-client: the client is a dev dependency used by the contract tests, and has
# no business in a runtime image.
COPY ./ /app
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --locked --no-dev --package wes-service

# Expose FastAPI port
EXPOSE 8000

# Run the app with live reload (dev). Host/port match compose env defaults.
#
# --reload-dir is not optional here. Without it the watcher walks everything under
# the working directory, which includes the virtualenv -- thousands of
# site-packages files. Any write there (a `uv sync`, a rebuilt venv on the host
# side of the bind mount) then triggers a reload storm the server never recovers
# from, and it stops answering /healthcheck. Scoping it to the two source trees
# that can actually change keeps reloads to real edits.
CMD ["uv", "run", "uvicorn", "wes_service.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--reload", \
     "--reload-dir", "packages/wes-service/src", \
     "--reload-dir", "packages/wes-schemas/src"]
