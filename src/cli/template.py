"""
CLI Template Commands

Manage templates on the flyto-cloud platform via API.
Supports export, import, push, pull, diff, list, search, info, history.
"""

import json
import os
import sys
from pathlib import Path

from .config import Colors

# Default API base URL — override with FLYTO_API_URL env var
DEFAULT_API_URL = "https://api.flyto.cloud/api"


def _get_api_url() -> str:
    return os.environ.get("FLYTO_API_URL", DEFAULT_API_URL).rstrip("/")


def _get_auth_token() -> str:
    """Read auth token from env or ~/.flyto/token file."""
    token = os.environ.get("FLYTO_TOKEN", "")
    if token:
        return token
    token_file = Path.home() / ".flyto" / "token"
    if token_file.exists():
        return token_file.read_text().strip()
    return ""


def _request(method: str, path: str, *, data=None, params=None, token: str = "") -> dict:
    """Make an HTTP request to the flyto-cloud API."""
    import urllib.request
    import urllib.parse
    import urllib.error

    base = _get_api_url()
    url = f"{base}{path}"

    if params:
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        if qs:
            url = f"{url}?{qs}"

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=body, method=method.upper())
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            detail = err_body.get("detail", str(e))
        except Exception:
            detail = str(e)
        return {"ok": False, "error": detail}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _require_auth() -> str:
    token = _get_auth_token()
    if not token:
        print(f"{Colors.FAIL}Error: Not authenticated.{Colors.ENDC}")
        print(f"Set FLYTO_TOKEN env var or save token to ~/.flyto/token")
        sys.exit(1)
    return token


# ============================================================
# Subcommands
# ============================================================

def cmd_export(args) -> int:
    """Export a template as YAML file."""
    token = _require_auth()
    template_id = args.template_id
    output = args.output

    result = _request("GET", f"/templates/{template_id}/export", token=token)
    if not result.get("ok"):
        print(f"{Colors.FAIL}Error: {result.get('error', 'Export failed')}{Colors.ENDC}")
        return 1

    yaml_str = result["yaml"]
    filename = output or result.get("filename", f"{template_id}.yaml")

    if output == "-":
        print(yaml_str)
    else:
        Path(filename).write_text(yaml_str, encoding="utf-8")
        print(f"{Colors.OKGREEN}✓ Exported to {filename}{Colors.ENDC}")

    return 0


def cmd_import(args) -> int:
    """Import a YAML file to create a new template."""
    token = _require_auth()
    yaml_path = Path(args.file)

    if not yaml_path.exists():
        print(f"{Colors.FAIL}Error: File not found: {yaml_path}{Colors.ENDC}")
        return 1

    yaml_content = yaml_path.read_text(encoding="utf-8")

    result = _request("POST", "/templates/import/yaml", data={
        "yaml_content": yaml_content,
    }, token=token)

    if not result.get("ok"):
        print(f"{Colors.FAIL}Error: {result.get('error', 'Import failed')}{Colors.ENDC}")
        return 1

    tmpl = result.get("template", {})
    print(f"{Colors.OKGREEN}✓ Template created: {tmpl.get('name', 'Untitled')}{Colors.ENDC}")
    print(f"  ID: {tmpl.get('id', 'N/A')}")
    if result.get("needs_auto_layout"):
        print(f"  {Colors.WARNING}Note: No position data — auto-layout recommended{Colors.ENDC}")

    return 0


def cmd_push(args) -> int:
    """Push a YAML file to update an existing template."""
    token = _require_auth()
    yaml_path = Path(args.file)
    template_id = args.template_id

    if not yaml_path.exists():
        print(f"{Colors.FAIL}Error: File not found: {yaml_path}{Colors.ENDC}")
        return 1

    yaml_content = yaml_path.read_text(encoding="utf-8")

    data = {
        "yaml_content": yaml_content,
        "change_summary": args.message or "",
    }
    if args.pr:
        data["create_pr"] = True
        data["pr_title"] = args.message or "YAML push"

    result = _request("PUT", f"/templates/{template_id}/push", data=data, token=token)

    if not result.get("ok"):
        print(f"{Colors.FAIL}Error: {result.get('error', 'Push failed')}{Colors.ENDC}")
        return 1

    action = result.get("action", "updated")
    if action == "pr_created":
        pr = result.get("pull_request", {})
        print(f"{Colors.OKGREEN}✓ Pull request created: {pr.get('title', '')}{Colors.ENDC}")
        print(f"  PR ID: {pr.get('id', 'N/A')}")
    else:
        tmpl = result.get("template", {})
        print(f"{Colors.OKGREEN}✓ Template updated: {tmpl.get('name', '')}{Colors.ENDC}")
        print(f"  Version: {tmpl.get('version_number', 'N/A')}")

    return 0


def cmd_pull(args) -> int:
    """Pull latest template version as YAML."""
    token = _require_auth()
    template_id = args.template_id
    output = args.output

    result = _request("GET", f"/templates/{template_id}/pull", token=token)

    if not result.get("ok"):
        print(f"{Colors.FAIL}Error: {result.get('error', 'Pull failed')}{Colors.ENDC}")
        return 1

    yaml_str = result["yaml"]
    filename = output or result.get("filename", f"{template_id}.yaml")

    if output == "-":
        print(yaml_str)
    else:
        Path(filename).write_text(yaml_str, encoding="utf-8")
        print(f"{Colors.OKGREEN}✓ Pulled to {filename} (v{result.get('version_number', '?')}){Colors.ENDC}")

    return 0


def cmd_diff(args) -> int:
    """Compare a local YAML file against the cloud version."""
    token = _require_auth()
    template_id = args.template_id
    yaml_path = Path(args.file)

    if not yaml_path.exists():
        print(f"{Colors.FAIL}Error: File not found: {yaml_path}{Colors.ENDC}")
        return 1

    yaml_content = yaml_path.read_text(encoding="utf-8")

    result = _request("POST", f"/templates/{template_id}/diff", data={
        "yaml_content": yaml_content,
    }, token=token)

    if not result.get("ok"):
        print(f"{Colors.FAIL}Error: {result.get('error', 'Diff failed')}{Colors.ENDC}")
        return 1

    if result.get("is_same"):
        print(f"{Colors.OKGREEN}No changes — local YAML matches cloud version.{Colors.ENDC}")
        return 0

    # Print diff summary
    added = result.get("added_steps", [])
    removed = result.get("removed_steps", [])
    modified = result.get("modified_steps", [])
    layout = result.get("layout_only_steps", [])
    fields = result.get("changed_fields", [])

    if fields:
        print(f"{Colors.OKCYAN}Changed fields:{Colors.ENDC} {', '.join(fields)}")
    if added:
        print(f"{Colors.OKGREEN}+ Added steps ({len(added)}):{Colors.ENDC} {', '.join(added)}")
    if removed:
        print(f"{Colors.FAIL}- Removed steps ({len(removed)}):{Colors.ENDC} {', '.join(removed)}")
    if modified:
        print(f"{Colors.WARNING}~ Modified steps ({len(modified)}):{Colors.ENDC} {', '.join(modified)}")
    if layout:
        print(f"  Layout-only changes: {', '.join(layout)}")

    return 0


def cmd_list(args) -> int:
    """List user's templates."""
    token = _require_auth()
    params = {}
    if args.tag:
        params["search"] = args.tag
    if args.status:
        params["status"] = args.status

    result = _request("GET", "/templates/me/templates", params=params, token=token)

    if not result.get("ok"):
        print(f"{Colors.FAIL}Error: {result.get('error', 'List failed')}{Colors.ENDC}")
        return 1

    templates = result.get("templates", [])
    if not templates:
        print("No templates found.")
        return 0

    print(f"{Colors.BOLD}{'ID':<24} {'Name':<30} {'Status':<12} {'Ver'}{Colors.ENDC}")
    print("-" * 74)
    for t in templates:
        tid = (t.get("id") or "")[:22]
        name = (t.get("name") or "Untitled")[:28]
        status = t.get("status", "draft")
        ver = t.get("version_number", 1)
        color = Colors.OKGREEN if status == "published" else Colors.WARNING
        print(f"{tid:<24} {name:<30} {color}{status:<12}{Colors.ENDC} v{ver}")

    total = result.get("total", len(templates))
    print(f"\n{total} template(s)")
    return 0


def cmd_search(args) -> int:
    """Search marketplace templates."""
    token = _get_auth_token()  # optional auth for search
    params = {"search": args.query, "pageSize": args.limit}

    result = _request("GET", "/templates/search", params=params, token=token)

    if not result.get("ok"):
        print(f"{Colors.FAIL}Error: {result.get('error', 'Search failed')}{Colors.ENDC}")
        return 1

    templates = result.get("templates", [])
    if not templates:
        print(f"No results for \"{args.query}\".")
        return 0

    print(f"{Colors.BOLD}{'ID':<24} {'Name':<30} {'Category':<12} {'Downloads'}{Colors.ENDC}")
    print("-" * 78)
    for t in templates:
        tid = (t.get("id") or "")[:22]
        name = (t.get("name") or "Untitled")[:28]
        cat = (t.get("category") or "")[:10]
        dl = t.get("downloads", 0)
        print(f"{tid:<24} {name:<30} {cat:<12} {dl}")

    return 0


def cmd_info(args) -> int:
    """Show template details."""
    token = _get_auth_token()
    template_id = args.template_id

    result = _request("GET", f"/templates/{template_id}", token=token)

    if not result.get("ok"):
        print(f"{Colors.FAIL}Error: {result.get('error', 'Not found')}{Colors.ENDC}")
        return 1

    t = result.get("template", {})
    print(f"{Colors.BOLD}{t.get('name', 'Untitled')}{Colors.ENDC}")
    print(f"  ID:          {t.get('id', 'N/A')}")
    print(f"  Description: {t.get('description', '-')}")
    print(f"  Category:    {t.get('category', '-')}")
    print(f"  Status:      {t.get('status', 'draft')}")
    print(f"  Version:     v{t.get('version_number', 1)}")
    print(f"  Tags:        {', '.join(t.get('tags', []))}")
    print(f"  Steps:       {len(t.get('steps', []))}")
    print(f"  Downloads:   {t.get('downloads', 0)}")
    print(f"  Visibility:  {t.get('visibility', 'private')}")

    return 0


def cmd_history(args) -> int:
    """Show version history for a template."""
    token = _require_auth()
    template_id = args.template_id

    result = _request("GET", f"/templates/{template_id}/versions", params={
        "limit": args.limit,
    }, token=token)

    if not result.get("ok"):
        print(f"{Colors.FAIL}Error: {result.get('error', 'Failed')}{Colors.ENDC}")
        return 1

    versions = result.get("versions", [])
    if not versions:
        print("No version history.")
        return 0

    print(f"{Colors.BOLD}{'Ver':<6} {'Tag':<12} {'Summary':<36} {'Date'}{Colors.ENDC}")
    print("-" * 74)
    for v in versions:
        ver = f"v{v.get('version_number', '?')}"
        tag = (v.get("version_tag") or "-")[:10]
        summary = (v.get("change_summary") or "-")[:34]
        date = (v.get("created_at") or "")[:19]
        print(f"{ver:<6} {tag:<12} {summary:<36} {date}")

    return 0


# ============================================================
# Parser registration
# ============================================================

def add_template_parser(subparsers) -> None:
    """Register the 'template' subcommand with all sub-actions."""
    tp = subparsers.add_parser(
        "template",
        help="Manage templates (export/import/push/pull/diff/list/search)",
        description="Template management commands for flyto-cloud.",
    )
    sub = tp.add_subparsers(dest="template_action", help="Template actions")

    # export
    p = sub.add_parser("export", help="Export template as YAML")
    p.add_argument("template_id", help="Template ID")
    p.add_argument("-o", "--output", help="Output file path (use - for stdout)")

    # import
    p = sub.add_parser("import", help="Import YAML to create template")
    p.add_argument("file", help="Path to .yaml file")

    # push
    p = sub.add_parser("push", help="Push YAML update to template")
    p.add_argument("template_id", help="Template ID")
    p.add_argument("file", help="Path to .yaml file")
    p.add_argument("-m", "--message", help="Change summary / PR title")
    p.add_argument("--pr", action="store_true", help="Create PR instead of direct push")

    # pull
    p = sub.add_parser("pull", help="Pull latest template as YAML")
    p.add_argument("template_id", help="Template ID")
    p.add_argument("-o", "--output", help="Output file path (use - for stdout)")

    # diff
    p = sub.add_parser("diff", help="Compare local YAML vs cloud version")
    p.add_argument("template_id", help="Template ID")
    p.add_argument("file", help="Path to local .yaml file")

    # list
    p = sub.add_parser("list", help="List your templates")
    p.add_argument("--tag", help="Filter by tag")
    p.add_argument("--status", choices=["draft", "published", "archived"])

    # search
    p = sub.add_parser("search", help="Search marketplace templates")
    p.add_argument("query", help="Search query")
    p.add_argument("--limit", type=int, default=20, help="Max results")

    # info
    p = sub.add_parser("info", help="Show template details")
    p.add_argument("template_id", help="Template ID")

    # history
    p = sub.add_parser("history", help="Show version history")
    p.add_argument("template_id", help="Template ID")
    p.add_argument("--limit", type=int, default=20, help="Max versions")


def run_template_command(args) -> int:
    """Dispatch template sub-action."""
    action = getattr(args, "template_action", None)
    if not action:
        print(f"Usage: flyto template <action>")
        print(f"Actions: export, import, push, pull, diff, list, search, info, history")
        return 1

    handlers = {
        "export": cmd_export,
        "import": cmd_import,
        "push": cmd_push,
        "pull": cmd_pull,
        "diff": cmd_diff,
        "list": cmd_list,
        "search": cmd_search,
        "info": cmd_info,
        "history": cmd_history,
    }

    handler = handlers.get(action)
    if not handler:
        print(f"{Colors.FAIL}Unknown template action: {action}{Colors.ENDC}")
        return 1

    return handler(args)
