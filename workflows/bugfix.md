# Bugfix Workflow

1. Reproduce the workflow or module failure with the smallest recipe.
2. Identify whether the issue is parameter validation, execution, assertion, or
   product target behavior.
3. Add a regression fixture when the bug is in core.
4. Update state if release validation confidence changes.
