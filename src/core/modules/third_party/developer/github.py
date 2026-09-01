# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
GitHub API Integration Modules
Work with GitHub repositories, issues, pull requests, etc.

HOW FAR A GITHUB CALL IS FOLLOWED

Every module in this file sends one HTTPS request and reads the reply to that
same request. Not one of them reads anything back afterwards, so the ceiling on
every successful path here is ACCEPTED. `response.status` is GitHub reporting on
GitHub's own work, and reading a peer's report of its own work is the definition
of taking its word for it. `http.request` settled the identical question the
identical way (`atomic/http/request.py`, the `is_ok` branch), and a 201 Created
is the case it names out loud: the number in the body is the server ASSERTING it
created something. To reach OBSERVED one of these modules would have to issue a
second request and compare; none does, and adding one is a change to what these
modules cost and when they rate-limit, not a change to what they report.

ACCEPTED is still worth attaching, because the alternative is not OBSERVED, it
is DISPATCHED -- what the engine stamps on a module that reports nothing, and
what these five said until now. "The instruction left us and nobody confirmed
anything" is untrue of a call that came back 200 with a parsed body.

THE ERROR PATHS ARE THE OTHER HALF, and on this file they matter more than the
happy one. These five modules do not raise on a non-2xx: they return
``{'status': 'error', 'message': ...}`` with no ``ok`` key, which
``_execute_single_mode`` passes straight through, so a 404 on ``get_repo`` is
recorded as a step that SUCCEEDED and flows downstream as one. The envelope is
now the only field on that path that says otherwise. It does not fix the
underlying shape -- see the report accompanying this change; returning
``ok: False`` would make the payload vanish into an ERROR result and take the
envelope with it, which is a decision about step semantics and not about
reporting.
"""
import logging
import os
from typing import Any, Dict

import aiohttp

from ...base import BaseModule
from ...registry import register_module
from ....constants import APIEndpoints, EnvVars
from ....engine.outcome import ClaimBy, Outcome, envelope


logger = logging.getLogger(__name__)


def _peer_answered(status: int) -> Dict[str, Any]:
    """The one thing every path in this file measures: a status line came back.

    This is the whole distance between DISPATCHED and ACCEPTED. A server
    received the request, processed it far enough to choose a reply, and sent
    one. It is not an observation of GitHub's state -- nothing in this file
    looks at anything except the answer to the message it just sent.
    """
    return {
        'kind': 'github_reply_read',
        'status': status,
        'measured_by': 'response.status -- the status line of the reply to this request',
        'detail': (
            'A server received this request and chose a reply. That is what '
            'separates accepted from dispatched, and it is all it separates: '
            'no GitHub state is read back anywhere in this module.'
        ),
    }


def _read_refused(status: int, resource: str) -> Dict[str, Any]:
    """FAILED -- a read that came back non-2xx returned nothing and changed nothing.

    FAILED rather than INDETERMINATE, and the second axis in `engine/outcome.py`
    is what decides it: INDETERMINATE is for when we cannot say. Here we can. A
    GET that GitHub refused altered nothing on either side, so there is no
    effect left in doubt -- only data we do not have. `http.request` uses FAILED
    for the same shape of definite non-happening.
    """
    return envelope(
        Outcome.FAILED,
        claim_by=ClaimBy.NONE,
        effects=[
            _peer_answered(status),
            {
                'kind': 'github_read_refused',
                'resource': resource,
                'measured_by': 'response.status, against the 200 this module can read',
                'detail': (
                    'GitHub answered and returned no {0}. A read changes nothing, '
                    'so nothing is left uncertain: this did not happen. The module '
                    'still returns a payload the engine records as a successful '
                    'step; this rung is the only field on it that disagrees.'
                ).format(resource),
            },
        ],
    )


def _mutation_unconfirmed(status: int, resource: str) -> Dict[str, Any]:
    """The off-ladder answer for a create that did not come back 201.

    The same split `http.request` makes between a refused request and a timed
    out one, moved from the transport to the status line:

        4xx   GitHub read the request, rejected it by name, and created
              nothing. Definite, so FAILED.
        5xx   GitHub broke while handling a POST it had already taken off the
              wire. The resource may exist. INDETERMINATE -- and this is why
              ``retryable=False`` on both creating modules is right: a retry
              after a 500 can create the thing twice.
        2xx   a success code this module does not recognise (it tests for
              exactly 201). The peer took the request and this module parsed
              nothing, so whether the resource exists is not known here.

    Calling the 5xx case FAILED would be the more comfortable answer and the
    wrong one: it would tell a person nothing was created when something may
    have been, which is the failure mode a workflow author cannot recover from.
    """
    definite = 400 <= status < 500
    return envelope(
        Outcome.FAILED if definite else Outcome.INDETERMINATE,
        claim_by=ClaimBy.NONE,
        effects=[
            _peer_answered(status),
            {
                'kind': 'github_create_rejected' if definite else 'github_create_unconfirmed',
                'resource': resource,
                'measured_by': 'response.status, against the 201 this module can read',
                'detail': (
                    'GitHub rejected the request by name and created no {0}.'
                    if definite else
                    'GitHub took this request off the wire and did not confirm '
                    'what it did with it, so the {0} may or may not exist. A '
                    'retry may create a second one.'
                ).format(resource),
            },
        ],
    )


def _github_headers(token=None):
    """Build common GitHub API headers."""
    headers = {'Accept': APIEndpoints.GITHUB_API_ACCEPT_HEADER, 'User-Agent': 'Flyto2-Workflow-Engine'}
    if token:
        headers['Authorization'] = f'token {token}'
    return headers


def _simplify_issues(data):
    """Extract essential fields from GitHub issue list."""
    return [{
        'number': i.get('number'), 'title': i.get('title'), 'state': i.get('state'),
        'url': i.get('html_url'), 'created_at': i.get('created_at'),
        'updated_at': i.get('updated_at'),
        'labels': [l['name'] for l in i.get('labels', [])],
        'user': i.get('user', {}).get('login'),
    } for i in data]


def _simplify_repos(data):
    """Extract essential fields from GitHub repo list."""
    return [{
        'name': r.get('name'), 'full_name': r.get('full_name'),
        'description': r.get('description'), 'url': r.get('html_url'),
        'private': r.get('private'), 'language': r.get('language'),
        'stars': r.get('stargazers_count'), 'forks': r.get('forks_count'),
        'created_at': r.get('created_at'), 'updated_at': r.get('updated_at'),
        'pushed_at': r.get('pushed_at'),
    } for r in data]


@register_module(
    module_id='api.github.get_repo',
    can_connect_to=['*'],
    can_receive_from=['*'],
    version='1.0.0',
    category='api',
    tags=['api', 'github', 'repository', 'integration', 'ssrf_protected'],
    label='Get GitHub Repository',
    label_key='modules.api.github.get_repo.label',
    description='Get information about a GitHub repository',
    description_key='modules.api.github.get_repo.description',
    icon='Github',
    color='#24292e',

    # Connection types
    input_types=['string'],
    output_types=['json', 'object'],

    # Phase 2: Execution settings
    timeout_ms=30000,  # API calls should complete within 30s
    retryable=True,  # Network errors can be retried
    max_retries=3,
    concurrent_safe=True,  # Multiple API calls can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['GITHUB_TOKEN'],
    handles_sensitive_data=False,  # Repository data is typically public
    required_permissions=['network.access'],

    params_schema={
        'owner': {
            'type': 'string',
            'label': 'Owner',
            'description': 'Repository owner (username or organization)',
                'description_key': 'modules.api.github.get_repo.params.owner.description',
            'placeholder': 'octocat',
            'required': True
        },
        'repo': {
            'type': 'string',
            'label': 'Repository',
            'description': 'Repository name',
                'description_key': 'modules.api.github.get_repo.params.repo.description',
            'placeholder': 'Hello-World',
            'required': True
        },
        'token': {
            'type': 'string',
            'label': 'Access Token',
            'description': 'GitHub Personal Access Token (optional but recommended)',
                'description_key': 'modules.api.github.get_repo.params.token.description',
            'placeholder': '${env.GITHUB_TOKEN}',
            'required': False,
            'sensitive': True
        }
    },
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.api.github.get_repo.output.status.description'},
        'repo': {'type': 'object', 'description': 'Repository information',
                'description_key': 'modules.api.github.get_repo.output.repo.description'},
        'name': {'type': 'string', 'description': 'Name of the item',
                'description_key': 'modules.api.github.get_repo.output.name.description'},
        'full_name': {'type': 'string', 'description': 'Full repository name',
                'description_key': 'modules.api.github.get_repo.output.full_name.description'},
        'description': {'type': 'string', 'description': 'Item description',
                'description_key': 'modules.api.github.get_repo.output.description.description'},
        'stars': {'type': 'number', 'description': 'Number of stars',
                'description_key': 'modules.api.github.get_repo.output.stars.description'},
        'forks': {'type': 'number', 'description': 'Number of forks',
                'description_key': 'modules.api.github.get_repo.output.forks.description'},
        'url': {'type': 'string', 'description': 'URL address',
                'description_key': 'modules.api.github.get_repo.output.url.description'},
        'outcome': {'type': 'object', 'description': (
                    'How far the effect was followed: "accepted" when GitHub '
                    'answered 200 with a repository body, "failed" when it '
                    'answered anything else. Never higher -- nothing reads GitHub '
                    'state back'),
                'description_key': 'modules.api.github.get_repo.output.outcome.description'}
    },
    examples=[
        {
            'name': 'Get repository info',
            'params': {
                'owner': 'octocat',
                'repo': 'Hello-World'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class GitHubGetRepoModule(BaseModule):
    """Get GitHub repository information"""

    module_name = "Get GitHub Repository"
    module_description = "Fetch information about a GitHub repository"

    def validate_params(self) -> None:
        if 'owner' not in self.params or not self.params['owner']:
            raise ValueError("Missing required parameter: owner")
        if 'repo' not in self.params or not self.params['repo']:
            raise ValueError("Missing required parameter: repo")

        self.owner = self.params['owner']
        self.repo = self.params['repo']
        self.token = self.params.get('token') or os.getenv(EnvVars.GITHUB_TOKEN)

    async def execute(self) -> Any:
        url = APIEndpoints.github_repo(self.owner, self.repo)

        headers = {
            'Accept': APIEndpoints.GITHUB_API_ACCEPT_HEADER,
            'User-Agent': 'Flyto2-Workflow-Engine'
        }

        if self.token:
            headers['Authorization'] = f'token {self.token}'

        # SECURITY: Set timeout to prevent hanging API calls
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'status': 'success',
                        'repo': data,
                        'name': data.get('name'),
                        'full_name': data.get('full_name'),
                        'description': data.get('description'),
                        'stars': data.get('stargazers_count'),
                        'forks': data.get('forks_count'),
                        'url': data.get('html_url'),
                        'outcome': envelope(
                            Outcome.ACCEPTED,
                            claim_by=ClaimBy.NONE,
                            effects=[
                                _peer_answered(response.status),
                                {
                                    'kind': 'repository_described_by_peer',
                                    'full_name': data.get('full_name'),
                                    'measured_by': (
                                        'full_name in the JSON body GitHub returned'
                                    ),
                                    'detail': (
                                        "GitHub's own description of a repository it "
                                        'holds. Nothing corroborates it: this module '
                                        'sends one request and reads its reply, so the '
                                        'evidence is exactly what the peer chose to say.'
                                    ),
                                },
                            ],
                        ),
                    }
                else:
                    error_text = await response.text()
                    return {
                        'status': 'error',
                        'message': f'Failed to fetch repository: HTTP {response.status} - {error_text}',
                        'outcome': _read_refused(response.status, 'repository'),
                    }


@register_module(
    module_id='api.github.list_issues',
    can_connect_to=['*'],
    can_receive_from=['*'],
    version='1.0.0',
    category='api',
    tags=['api', 'github', 'issues', 'integration', 'ssrf_protected'],
    label='List GitHub Issues',
    label_key='modules.api.github.list_issues.label',
    description='List issues from a GitHub repository',
    description_key='modules.api.github.list_issues.description',
    icon='AlertCircle',
    color='#24292e',

    # Connection types
    input_types=['string'],
    output_types=['array', 'json'],

    # Phase 2: Execution settings
    timeout_ms=30000,  # API calls should complete within 30s
    retryable=True,  # Network errors can be retried
    max_retries=3,
    concurrent_safe=True,  # Multiple API calls can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['GITHUB_TOKEN'],
    handles_sensitive_data=False,  # Issue data is typically public
    required_permissions=['network.access'],

    params_schema={
        'owner': {
            'type': 'string',
            'label': 'Owner',
            'description': 'Repository owner',
            'placeholder': 'username',
            'required': True
        },
        'repo': {
            'type': 'string',
            'label': 'Repository',
            'description': 'Repository name',
            'placeholder': 'username/repo',
            'required': True
        },
        'state': {
            'type': 'select',
            'label': 'State',
            'description': 'Issue state filter',
            'options': ['open', 'closed', 'all'],
            'default': 'open',
            'required': False
        },
        'labels': {
            'type': 'string',
            'label': 'Labels',
            'description': 'Filter by labels (comma-separated)',
            'placeholder': 'bug,enhancement',
            'required': False
        },
        'limit': {
            'type': 'number',
            'label': 'Limit',
            'description': 'Maximum number of issues to fetch',
            'default': 30,
            'min': 1,
            'max': 100,
            'required': False
        },
        'token': {
            'type': 'string',
            'label': 'Access Token',
            'description': 'GitHub Personal Access Token',
            'placeholder': '${env.GITHUB_TOKEN}',
            'required': False,
            'sensitive': True
        }
    },
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)'},
        'issues': {'type': 'array', 'description': 'The issues'},
        'count': {'type': 'number', 'description': 'Number of items'},
        'outcome': {'type': 'object', 'description': (
            'How far the effect was followed: "accepted" when GitHub answered '
            '200, "failed" when it answered anything else. `count` is the size '
            'of one page of the reply, not a total')}
    },
    examples=[
        {
            'name': 'List open issues',
            'params': {
                'owner': 'facebook',
                'repo': 'react',
                'state': 'open',
                'limit': 10
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class GitHubListIssuesModule(BaseModule):
    """List GitHub issues"""

    module_name = "List GitHub Issues"
    module_description = "Fetch issues from a GitHub repository"

    def validate_params(self) -> None:
        if 'owner' not in self.params or not self.params['owner']:
            raise ValueError("Missing required parameter: owner")
        if 'repo' not in self.params or not self.params['repo']:
            raise ValueError("Missing required parameter: repo")

        self.owner = self.params['owner']
        self.repo = self.params['repo']
        self.state = self.params.get('state', 'open')
        self.labels = self.params.get('labels')
        self.limit = self.params.get('limit', 30)
        self.token = self.params.get('token') or os.getenv(EnvVars.GITHUB_TOKEN)

    async def execute(self) -> Any:
        url = APIEndpoints.github_issues(self.owner, self.repo)
        headers = _github_headers(self.token)
        params = {'state': self.state, 'per_page': min(self.limit, 100)}
        if self.labels:
            params['labels'] = self.labels

        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    issues = _simplify_issues(data)
                    return {
                        'status': 'success',
                        'issues': issues,
                        'count': len(issues),
                        'outcome': envelope(
                            Outcome.ACCEPTED,
                            claim_by=ClaimBy.NONE,
                            effects=[
                                _peer_answered(response.status),
                                {
                                    'kind': 'issues_returned',
                                    'count': len(issues),
                                    'measured_by': (
                                        'len() over the JSON array GitHub returned'
                                    ),
                                    'detail': (
                                        'How many issue objects came back in THIS '
                                        'reply, which is not how many the repository '
                                        'has: per_page caps it at `limit` and only the '
                                        'first page is requested, so a count equal to '
                                        'the limit means "at least this many". A count '
                                        'of 0 is the peer saying it matched nothing, '
                                        'and is no weaker evidence than any other '
                                        'number -- the rung rests on the reply, not on '
                                        'the count.'
                                    ),
                                },
                            ],
                        ),
                    }
                error_text = await response.text()
                return {
                    'status': 'error',
                    'message': f'Failed to fetch issues: HTTP {response.status} - {error_text}',
                    'outcome': _read_refused(response.status, 'issues'),
                }


@register_module(
    module_id='api.github.create_issue',
    can_connect_to=['*'],
    can_receive_from=['*'],
    version='1.0.0',
    category='api',
    tags=['api', 'github', 'issues', 'create', 'ssrf_protected'],
    label='Create GitHub Issue',
    label_key='modules.api.github.create_issue.label',
    description='Create a new issue in a GitHub repository',
    description_key='modules.api.github.create_issue.description',
    icon='Plus',
    color='#24292e',

    # Connection types
    input_types=['string', 'object'],
    output_types=['json', 'object'],

    # Phase 2: Execution settings
    timeout_ms=30000,  # API calls should complete within 30s
    retryable=False,  # Could create duplicate issues if retried
    concurrent_safe=True,  # Multiple API calls can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['GITHUB_TOKEN'],
    handles_sensitive_data=False,  # Issue data is typically public
    required_permissions=['network.access'],

    params_schema={
        'owner': {
            'type': 'string',
            'label': 'Owner',
            'description': 'Repository owner',
            'placeholder': 'username',
            'required': True
        },
        'repo': {
            'type': 'string',
            'label': 'Repository',
            'description': 'Repository name',
            'placeholder': 'username/repo',
            'required': True
        },
        'title': {
            'type': 'string',
            'label': 'Title',
            'description': 'Issue title',
            'placeholder': 'Bug: Application crashes on startup',
            'required': True
        },
        'body': {
            'type': 'text',
            'label': 'Body',
            'description': 'Issue description (Markdown supported)',
            'placeholder': 'Detailed description of the issue...',
            'required': False
        },
        'labels': {
            'type': 'array',
            'label': 'Labels',
            'description': 'Issue labels',
            'placeholder': ['bug', 'high-priority'],
            'required': False
        },
        'assignees': {
            'type': 'array',
            'label': 'Assignees',
            'description': 'GitHub usernames to assign',
            'placeholder': ['username1', 'username2'],
            'required': False
        },
        'token': {
            'type': 'string',
            'label': 'Access Token',
            'description': 'GitHub Personal Access Token (required for creation)',
            'placeholder': '${env.GITHUB_TOKEN}',
            'required': True,
            'sensitive': True
        }
    },
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)'},
        'issue': {'type': 'object', 'description': 'Issue information'},
        'number': {'type': 'number', 'description': 'Issue or PR number'},
        'url': {'type': 'string', 'description': 'URL address'},
        'outcome': {'type': 'object', 'description': (
            'How far the effect was followed: "accepted" on a 201 (GitHub says '
            'it created the issue; nothing reads it back), "failed" on a 4xx '
            '(refused, nothing created), "indeterminate" on a 5xx (it may exist)')}
    },
    examples=[
        {
            'name': 'Create bug report',
            'params': {
                'owner': 'myorg',
                'repo': 'myproject',
                'title': 'Bug: Login fails',
                'body': 'Users cannot log in after the latest deployment.',
                'labels': ['bug', 'urgent']
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class GitHubCreateIssueModule(BaseModule):
    """Create GitHub issue"""

    module_name = "Create GitHub Issue"
    module_description = "Create a new issue in a GitHub repository"

    def validate_params(self) -> None:
        required = ['owner', 'repo', 'title']
        for param in required:
            if param not in self.params or not self.params[param]:
                raise ValueError(f"Missing required parameter: {param}")

        self.owner = self.params['owner']
        self.repo = self.params['repo']
        self.title = self.params['title']
        self.body = self.params.get('body', '')
        self.labels = self.params.get('labels', [])
        self.assignees = self.params.get('assignees', [])

        self.token = self.params.get('token') or os.getenv(EnvVars.GITHUB_TOKEN)
        if not self.token:
            raise ValueError(
                f"GitHub token is required to create issues. "
                f"Set {EnvVars.GITHUB_TOKEN} environment variable or provide token parameter. "
                f"Get token from: https://github.com/settings/tokens"
            )

    async def execute(self) -> Any:
        url = APIEndpoints.github_issues(self.owner, self.repo)

        headers = {
            'Accept': APIEndpoints.GITHUB_API_ACCEPT_HEADER,
            'Authorization': f'token {self.token}',
            'User-Agent': 'Flyto2-Workflow-Engine'
        }

        payload = {
            'title': self.title,
            'body': self.body
        }

        if self.labels:
            payload['labels'] = self.labels
        if self.assignees:
            payload['assignees'] = self.assignees

        # SECURITY: Set timeout to prevent hanging API calls
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status == 201:
                    data = await response.json()
                    return {
                        'status': 'success',
                        'issue': data,
                        'number': data.get('number'),
                        'url': data.get('html_url'),
                        'outcome': envelope(
                            Outcome.ACCEPTED,
                            claim_by=ClaimBy.NONE,
                            effects=[
                                _peer_answered(response.status),
                                {
                                    'kind': 'issue_reported_created',
                                    'number': data.get('number'),
                                    'url': data.get('html_url'),
                                    'measured_by': (
                                        'number and html_url in the 201 body GitHub '
                                        'returned'
                                    ),
                                    'detail': (
                                        'GitHub asserting that it created an issue, and '
                                        'naming it. The number is not a value this '
                                        'module could have produced from its own '
                                        'inputs, which is why this is accepted rather '
                                        'than dispatched. It is still the peer '
                                        'reporting on its own work, which is why it is '
                                        'not observed: reading the issue back would be '
                                        'an observation and no second request is made.'
                                    ),
                                },
                            ],
                        ),
                    }
                else:
                    error_text = await response.text()
                    return {
                        'status': 'error',
                        'message': f'Failed to create issue: HTTP {response.status} - {error_text}',
                        'outcome': _mutation_unconfirmed(response.status, 'issue'),
                    }


@register_module(
    module_id='api.github.create_pr',
    can_connect_to=['*'],
    can_receive_from=['*'],
    version='1.0.0',
    category='api',
    tags=['api', 'github', 'pull-request', 'create', 'ssrf_protected'],
    label='Create GitHub Pull Request',
    label_key='modules.api.github.create_pr.label',
    description='Create a new pull request in a GitHub repository',
    description_key='modules.api.github.create_pr.description',
    icon='GitPullRequest',
    color='#24292e',

    # Connection types
    input_types=['string', 'object'],
    output_types=['json', 'object'],

    # Phase 2: Execution settings
    timeout_ms=30000,  # API calls should complete within 30s
    retryable=False,  # Could create duplicate PRs if retried
    concurrent_safe=True,  # Multiple API calls can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['GITHUB_TOKEN'],
    handles_sensitive_data=False,
    required_permissions=['network.access'],

    params_schema={
        'owner': {
            'type': 'string',
            'label': 'Owner',
            'description': 'Repository owner',
            'placeholder': 'username',
            'required': True
        },
        'repo': {
            'type': 'string',
            'label': 'Repository',
            'description': 'Repository name',
            'placeholder': 'my-repo',
            'required': True
        },
        'title': {
            'type': 'string',
            'label': 'Title',
            'description': 'Pull request title',
            'placeholder': 'Add new feature',
            'required': True
        },
        'body': {
            'type': 'text',
            'label': 'Body',
            'description': 'Pull request description (Markdown supported)',
            'placeholder': 'Detailed description of the changes...',
            'required': False
        },
        'head': {
            'type': 'string',
            'label': 'Head Branch',
            'description': 'The branch that contains your changes',
            'placeholder': 'feature/my-feature',
            'required': True
        },
        'base': {
            'type': 'string',
            'label': 'Base Branch',
            'description': 'The branch you want to merge into',
            'placeholder': 'main',
            'required': False,
            'default': 'main'
        },
        'draft': {
            'type': 'boolean',
            'label': 'Draft',
            'description': 'Create as draft pull request',
            'required': False,
            'default': False
        },
        'token': {
            'type': 'string',
            'label': 'Access Token',
            'description': 'GitHub Personal Access Token (required for creation)',
            'placeholder': '${env.GITHUB_TOKEN}',
            'required': True,
            'sensitive': True
        }
    },
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)'},
        'pr': {'type': 'object', 'description': 'Pull request information'},
        'number': {'type': 'number', 'description': 'Pull request number'},
        'url': {'type': 'string', 'description': 'Pull request URL'},
        'outcome': {'type': 'object', 'description': (
            'How far the effect was followed: "accepted" on a 201 (GitHub says '
            'it opened the PR; nothing reads it back), "failed" on a 4xx '
            '(refused, nothing created), "indeterminate" on a 5xx (it may exist)')}
    },
    examples=[
        {
            'name': 'Create a pull request',
            'params': {
                'owner': 'myorg',
                'repo': 'myproject',
                'title': 'Add user authentication',
                'body': 'Implements OAuth2 login flow with Google and GitHub providers.',
                'head': 'feature/auth',
                'base': 'main'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class GitHubCreatePRModule(BaseModule):
    """Create GitHub pull request"""

    module_name = "Create GitHub Pull Request"
    module_description = "Create a new pull request in a GitHub repository"

    def validate_params(self) -> None:
        required = ['owner', 'repo', 'title', 'head']
        for param in required:
            if param not in self.params or not self.params[param]:
                raise ValueError(f"Missing required parameter: {param}")

        self.owner = self.params['owner']
        self.repo = self.params['repo']
        self.title = self.params['title']
        self.body = self.params.get('body', '')
        self.head = self.params['head']
        self.base = self.params.get('base', 'main')
        self.draft = self.params.get('draft', False)

        self.token = self.params.get('token') or os.getenv(EnvVars.GITHUB_TOKEN)
        if not self.token:
            raise ValueError(
                f"GitHub token is required to create pull requests. "
                f"Set {EnvVars.GITHUB_TOKEN} environment variable or provide token parameter. "
                f"Get token from: https://github.com/settings/tokens"
            )

    async def execute(self) -> Any:
        url = f"{APIEndpoints.github_repo(self.owner, self.repo)}/pulls"

        headers = {
            'Accept': APIEndpoints.GITHUB_API_ACCEPT_HEADER,
            'Authorization': f'token {self.token}',
            'User-Agent': 'Flyto2-Workflow-Engine'
        }

        payload = {
            'title': self.title,
            'body': self.body,
            'head': self.head,
            'base': self.base,
            'draft': self.draft
        }

        # SECURITY: Set timeout to prevent hanging API calls
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status == 201:
                    data = await response.json()
                    return {
                        'status': 'success',
                        'pr': data,
                        'number': data.get('number'),
                        'url': data.get('html_url'),
                        'outcome': envelope(
                            Outcome.ACCEPTED,
                            claim_by=ClaimBy.NONE,
                            effects=[
                                _peer_answered(response.status),
                                {
                                    'kind': 'pull_request_reported_created',
                                    'number': data.get('number'),
                                    'url': data.get('html_url'),
                                    'measured_by': (
                                        'number and html_url in the 201 body GitHub '
                                        'returned'
                                    ),
                                    'detail': (
                                        'GitHub asserting that it opened a pull request '
                                        'and naming it. Server-assigned, so it is more '
                                        'than an echo of the inputs -- and still the '
                                        'peer reporting its own work, so it is not an '
                                        'observation. Note what is NOT claimed at any '
                                        'rung: that the branches merge, that CI ran, or '
                                        'that anyone can merge it.'
                                    ),
                                },
                            ],
                        ),
                    }
                else:
                    error_text = await response.text()
                    return {
                        'status': 'error',
                        'message': f'Failed to create pull request: HTTP {response.status} - {error_text}',
                        'outcome': _mutation_unconfirmed(response.status, 'pull request'),
                    }


@register_module(
    module_id='api.github.list_repos',
    can_connect_to=['*'],
    can_receive_from=['*'],
    version='1.0.0',
    category='api',
    tags=['api', 'github', 'repository', 'list', 'ssrf_protected'],
    label='List GitHub Repositories',
    label_key='modules.api.github.list_repos.label',
    description='List repositories for a GitHub user or the authenticated user',
    description_key='modules.api.github.list_repos.description',
    icon='Github',
    color='#24292e',

    # Connection types
    input_types=['string', 'object'],
    output_types=['json', 'array'],

    # Phase 2: Execution settings
    timeout_ms=30000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=False,
    credential_keys=['GITHUB_TOKEN'],
    handles_sensitive_data=False,
    required_permissions=['network.access'],

    params_schema={
        'owner': {
            'type': 'string',
            'label': 'Owner',
            'description': 'GitHub username, or "me" for authenticated user',
            'placeholder': 'username',
            'required': True
        },
        'type': {
            'type': 'select',
            'label': 'Repository Type',
            'description': 'Filter repositories by type',
            'options': [
                {'label': 'All', 'value': 'all'},
                {'label': 'Owner', 'value': 'owner'},
                {'label': 'Member', 'value': 'member'}
            ],
            'required': False,
            'default': 'all'
        },
        'sort': {
            'type': 'select',
            'label': 'Sort By',
            'description': 'Sort repositories by field',
            'options': [
                {'label': 'Created', 'value': 'created'},
                {'label': 'Updated', 'value': 'updated'},
                {'label': 'Pushed', 'value': 'pushed'},
                {'label': 'Full Name', 'value': 'full_name'}
            ],
            'required': False,
            'default': 'updated'
        },
        'limit': {
            'type': 'number',
            'label': 'Limit',
            'description': 'Maximum number of repositories to return',
            'placeholder': '30',
            'required': False,
            'default': 30
        },
        'token': {
            'type': 'string',
            'label': 'Access Token',
            'description': 'GitHub Personal Access Token (optional, required for private repos and "me")',
            'placeholder': '${env.GITHUB_TOKEN}',
            'required': False,
            'sensitive': True
        }
    },
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)'},
        'repos': {'type': 'array', 'description': 'List of repositories'},
        'count': {'type': 'number', 'description': 'Number of repositories returned'},
        'outcome': {'type': 'object', 'description': (
            'How far the effect was followed: "accepted" when GitHub answered '
            '200, "failed" when it answered anything else. `count` is the size '
            'of one page of the reply, not a total')}
    },
    examples=[
        {
            'name': 'List user repositories',
            'params': {
                'owner': 'octocat',
                'sort': 'updated',
                'limit': 10
            }
        },
        {
            'name': 'List my repositories',
            'params': {
                'owner': 'me',
                'type': 'owner',
                'sort': 'pushed'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class GitHubListReposModule(BaseModule):
    """List GitHub repositories"""

    module_name = "List GitHub Repositories"
    module_description = "List repositories for a GitHub user or the authenticated user"

    def validate_params(self) -> None:
        if 'owner' not in self.params or not self.params['owner']:
            raise ValueError("Missing required parameter: owner")

        self.owner = self.params['owner']
        self.repo_type = self.params.get('type', 'all')
        self.sort = self.params.get('sort', 'updated')
        self.limit = self.params.get('limit', 30)

        self.token = self.params.get('token') or os.getenv(EnvVars.GITHUB_TOKEN)

        if self.owner == 'me' and not self.token:
            raise ValueError(
                f"GitHub token is required when using 'me' as owner. "
                f"Set {EnvVars.GITHUB_TOKEN} environment variable or provide token parameter. "
                f"Get token from: https://github.com/settings/tokens"
            )

    async def execute(self) -> Any:
        if self.owner == 'me':
            url = f"{APIEndpoints.GITHUB_BASE_URL}/user/repos"
        else:
            url = f"{APIEndpoints.GITHUB_BASE_URL}/users/{self.owner}/repos"

        headers = _github_headers(self.token)
        params = {'type': self.repo_type, 'sort': self.sort, 'per_page': min(int(self.limit), 100)}

        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    repos = _simplify_repos(data)
                    return {
                        'status': 'success',
                        'repos': repos,
                        'count': len(repos),
                        'outcome': envelope(
                            Outcome.ACCEPTED,
                            claim_by=ClaimBy.NONE,
                            effects=[
                                _peer_answered(response.status),
                                {
                                    'kind': 'repositories_returned',
                                    'count': len(repos),
                                    'measured_by': (
                                        'len() over the JSON array GitHub returned'
                                    ),
                                    'detail': (
                                        'How many repository objects came back in THIS '
                                        'reply. One page only: per_page caps it at '
                                        '`limit` (max 100) and no pagination follows, '
                                        'so this is not "how many repositories the '
                                        'owner has".'
                                    ),
                                },
                            ],
                        ),
                    }
                error_text = await response.text()
                return {
                    'status': 'error',
                    'message': f'Failed to list repositories: HTTP {response.status} - {error_text}',
                    'outcome': _read_refused(response.status, 'repositories'),
                }
