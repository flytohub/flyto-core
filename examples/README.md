# Examples

Examples are public, runnable starting points for community users and sales or
support demos. They should stay safe to publish and should not require private
Flyto infrastructure.

## Rules

- Use placeholder credentials only.
- Prefer public, low-risk targets or local fixtures.
- Keep outputs deterministic enough for documentation and smoke tests.
- When an example needs browser automation, document the Playwright setup path.

## Enterprise Notes

Enterprise/private deployments can reuse these examples as acceptance tests by
overriding target URLs and credentials at runtime. Do not add enterprise-only
logic here; put deployment-specific policy in config or workflow inputs.
