"""
GitHub API Integration Modules
Work with GitHub repositories, issues, pull requests, etc.
"""
import logging
import os
from typing import Any, Dict

import aiohttp

from ...base import BaseModule
from ...registry import register_module
from ....constants import APIEndpoints, EnvVars


logger = logging.getLogger(__name__)


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
                'description_key': 'modules.api.github.get_repo.output.url.description'}
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
    author='Flyto Team',
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
            'User-Agent': 'Flyto-Workflow-Engine'
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
                        'url': data.get('html_url')
                    }
                else:
                    error_text = await response.text()
                    return {
                        'status': 'error',
                        'message': f'Failed to fetch repository: HTTP {response.status} - {error_text}'
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
        'count': {'type': 'number', 'description': 'Number of items'}
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
    author='Flyto Team',
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

        headers = {
            'Accept': APIEndpoints.GITHUB_API_ACCEPT_HEADER,
            'User-Agent': 'Flyto-Workflow-Engine'
        }

        if self.token:
            headers['Authorization'] = f'token {self.token}'

        params = {
            'state': self.state,
            'per_page': min(self.limit, 100)
        }

        if self.labels:
            params['labels'] = self.labels

        # SECURITY: Set timeout to prevent hanging API calls
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    # Simplify issue data
                    issues = []
                    for issue in data:
                        issues.append({
                            'number': issue.get('number'),
                            'title': issue.get('title'),
                            'state': issue.get('state'),
                            'url': issue.get('html_url'),
                            'created_at': issue.get('created_at'),
                            'updated_at': issue.get('updated_at'),
                            'labels': [label['name'] for label in issue.get('labels', [])],
                            'user': issue.get('user', {}).get('login')
                        })

                    return {
                        'status': 'success',
                        'issues': issues,
                        'count': len(issues)
                    }
                else:
                    error_text = await response.text()
                    return {
                        'status': 'error',
                        'message': f'Failed to fetch issues: HTTP {response.status} - {error_text}'
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
        'url': {'type': 'string', 'description': 'URL address'}
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
    author='Flyto Team',
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
            'User-Agent': 'Flyto-Workflow-Engine'
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
                        'url': data.get('html_url')
                    }
                else:
                    error_text = await response.text()
                    return {
                        'status': 'error',
                        'message': f'Failed to create issue: HTTP {response.status} - {error_text}'
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
        'url': {'type': 'string', 'description': 'Pull request URL'}
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
    author='Flyto Team',
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
            'User-Agent': 'Flyto-Workflow-Engine'
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
                        'url': data.get('html_url')
                    }
                else:
                    error_text = await response.text()
                    return {
                        'status': 'error',
                        'message': f'Failed to create pull request: HTTP {response.status} - {error_text}'
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
        'count': {'type': 'number', 'description': 'Number of repositories returned'}
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
    author='Flyto Team',
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

        # "me" requires authentication
        if self.owner == 'me' and not self.token:
            raise ValueError(
                f"GitHub token is required when using 'me' as owner. "
                f"Set {EnvVars.GITHUB_TOKEN} environment variable or provide token parameter. "
                f"Get token from: https://github.com/settings/tokens"
            )

    async def execute(self) -> Any:
        # Determine API endpoint
        if self.owner == 'me':
            url = f"{APIEndpoints.GITHUB_BASE_URL}/user/repos"
        else:
            url = f"{APIEndpoints.GITHUB_BASE_URL}/users/{self.owner}/repos"

        headers = {
            'Accept': APIEndpoints.GITHUB_API_ACCEPT_HEADER,
            'User-Agent': 'Flyto-Workflow-Engine'
        }

        if self.token:
            headers['Authorization'] = f'token {self.token}'

        params = {
            'type': self.repo_type,
            'sort': self.sort,
            'per_page': min(int(self.limit), 100)
        }

        # SECURITY: Set timeout to prevent hanging API calls
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    repos = []
                    for repo in data:
                        repos.append({
                            'name': repo.get('name'),
                            'full_name': repo.get('full_name'),
                            'description': repo.get('description'),
                            'url': repo.get('html_url'),
                            'private': repo.get('private'),
                            'language': repo.get('language'),
                            'stars': repo.get('stargazers_count'),
                            'forks': repo.get('forks_count'),
                            'created_at': repo.get('created_at'),
                            'updated_at': repo.get('updated_at'),
                            'pushed_at': repo.get('pushed_at')
                        })

                    return {
                        'status': 'success',
                        'repos': repos,
                        'count': len(repos)
                    }
                else:
                    error_text = await response.text()
                    return {
                        'status': 'error',
                        'message': f'Failed to list repositories: HTTP {response.status} - {error_text}'
                    }
