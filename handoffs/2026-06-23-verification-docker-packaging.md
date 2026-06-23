# Verification Docker Packaging

## Context

The local Flyto2 compose stack could not build the dedicated Product
Verification runner image. `Dockerfile.verification` copies `README.md` during
the wheel build because `pyproject.toml` declares it as package metadata, but
`.dockerignore` excluded all `*.md` files.

## Change

- Re-included only the root `README.md` in `.dockerignore`.
- Kept bulk markdown/docs content out of the image context.
- Forced `HEADLESS=true` and `DEPLOYMENT_MODE=worker` in
  `Dockerfile.verification` so the container does not try to launch a headed
  browser or persistent desktop profile.
- Added `tests/test_verification_packaging.py` to assert the verification image
  package metadata remains available while docs stay excluded.

## Verification

Run:

```bash
python -m pytest tests/test_verification_packaging.py tests/test_verification_service.py
docker-compose -f /Users/chester/flytohub/flyto-engine/docker-compose.yml build verification
```

## Follow-Up

If `pyproject.toml` changes to use another readme file, update this guard before
building the verification service image.
