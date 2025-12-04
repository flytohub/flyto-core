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
    version='1.0.0',
    category='api',
    tags=['api', 'github', 'repository', 'integration'],
    label='Get GitHub Repository',
    label_key='modules.api.github.get_repo.label',
    description='Get information about a GitHub repository',
    description_key='modules.api.github.get_repo.description',
    icon='Github',
    color='#24292e',

    # Connection types
    input_types=['any'],
    output_types=['any'],

    # Phase 2: Execution settings
    timeout=30,  # API calls should complete within 30s
    retryable=True,  # Network errors can be retried
    max_retries=3,
    concurrent_safe=True,  # Multiple API calls can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,  # Needs GITHUB_TOKEN (recommended)
    handles_sensitive_data=False,  # Repository data is typically public
    required_permissions=['network.access'],

    params_schema={
        'owner': {
            'type': 'string',
            'label': 'Owner',
            'description': 'Repository owner (username or organization)',
            'placeholder': 'octocat',
            'required': True
        },
        'repo': {
            'type': 'string',
            'label': 'Repository',
            'description': 'Repository name',
            'placeholder': 'Hello-World',
            'required': True
        },
        'token': {
            'type': 'string',
            'label': 'Access Token',
            'description': 'GitHub Personal Access Token (optional but recommended)',
            'placeholder': '${env.GITHUB_TOKEN}',
            'required': False,
            'sensitive': True
        }
    },
    output_schema={
        'status': {'type': 'string'},
        'repo': {'type': 'object'},
        'name': {'type': 'string'},
        'full_name': {'type': 'string'},
        'description': {'type': 'string'},
        'stars': {'type': 'number'},
        'forks': {'type': 'number'},
        'url': {'type': 'string'}
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

    def validate_params(self):
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

        async with aiohttp.ClientSession() as session:
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
    version='1.0.0',
    category='api',
    tags=['api', 'github', 'issues', 'integration'],
    label='List GitHub Issues',
    label_key='modules.api.github.list_issues.label',
    description='List issues from a GitHub repository',
    description_key='modules.api.github.list_issues.description',
    icon='AlertCircle',
    color='#24292e',

    # Connection types
    input_types=['any'],
    output_types=['any'],

    # Phase 2: Execution settings
    timeout=30,  # API calls should complete within 30s
    retryable=True,  # Network errors can be retried
    max_retries=3,
    concurrent_safe=True,  # Multiple API calls can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,  # Needs GITHUB_TOKEN (recommended)
    handles_sensitive_data=False,  # Issue data is typically public
    required_permissions=['network.access'],

    params_schema={
        'owner': {
            'type': 'string',
            'label': 'Owner',
            'description': 'Repository owner',
            'required': True
        },
        'repo': {
            'type': 'string',
            'label': 'Repository',
            'description': 'Repository name',
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
        'status': {'type': 'string'},
        'issues': {'type': 'array'},
        'count': {'type': 'number'}
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

    def validate_params(self):
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
            'User-Agent': 'Flyto2-Workflow-Engine'
        }

        if self.token:
            headers['Authorization'] = f'token {self.token}'

        params = {
            'state': self.state,
            'per_page': min(self.limit, 100)
        }

        if self.labels:
            params['labels'] = self.labels

        async with aiohttp.ClientSession() as session:
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
    version='1.0.0',
    category='api',
    tags=['api', 'github', 'issues', 'create'],
    label='Create GitHub Issue',
    label_key='modules.api.github.create_issue.label',
    description='Create a new issue in a GitHub repository',
    description_key='modules.api.github.create_issue.description',
    icon='Plus',
    color='#24292e',

    # Connection types
    input_types=['any'],
    output_types=['any'],

    # Phase 2: Execution settings
    timeout=30,  # API calls should complete within 30s
    retryable=False,  # Could create duplicate issues if retried
    concurrent_safe=True,  # Multiple API calls can run in parallel

    # Phase 2: Security settings
    requires_credentials=True,  # Needs GITHUB_TOKEN (required for creation)
    handles_sensitive_data=False,  # Issue data is typically public
    required_permissions=['network.access'],

    params_schema={
        'owner': {
            'type': 'string',
            'label': 'Owner',
            'description': 'Repository owner',
            'required': True
        },
        'repo': {
            'type': 'string',
            'label': 'Repository',
            'description': 'Repository name',
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
        'status': {'type': 'string'},
        'issue': {'type': 'object'},
        'number': {'type': 'number'},
        'url': {'type': 'string'}
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

    def validate_params(self):
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

        async with aiohttp.ClientSession() as session:
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
