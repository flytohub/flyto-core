# Verification Service Image

## Summary

Added a dedicated `Dockerfile.verification` for the `flyto-verification`
microservice used by Flyto2 deterministic Product Verification.

## Contract

- Builds `flyto-core[browser,api]`.
- Installs Playwright Chromium and browser system dependencies.
- Runs `core.verification_service.main('0.0.0.0', 8344)`.
- Exposes `/health` on port `8344`.

## Notes

- This image is separate from the default `Dockerfile`, which still starts
  `flyto-serve`.
- The service must receive runtime-only callback secrets through environment
  variables. Do not bake credentials into the image or compose fixtures.
- Local/staging browser replay should use narrow SSRF envs instead of disabling
  the guard. For Vite smoke, set `FLYTO_ALLOWED_HOSTS=127.0.0.1,localhost` and
  `FLYTO_HTTP_ALLOWED_PORTS=5180`; production defaults remain `80,443,8080,8443`.
- `browser.screenshot` returns a module output object with `filepath`; the
  verification service now extracts that path and sends it as a screenshot
  callback artifact.
