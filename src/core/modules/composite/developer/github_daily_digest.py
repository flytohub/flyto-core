"""
GitHub Daily Digest Composite Module

Fetches GitHub repository updates and sends a daily digest notification.
"""
from ..base import CompositeModule, register_composite, UIVisibility


@register_composite(
    module_id='composite.developer.github_daily_digest',
    version='1.0.0',
    category='developer',
    subcategory='github',
    tags=['github', 'digest', 'notification', 'developer', 'daily'],

    # Context requirements
    requires_context=None,
    provides_context=['data', 'api_response'],

    # UI metadata
    ui_visibility=UIVisibility.DEFAULT,
    ui_label='GitHub Daily Digest',
    ui_label_key='composite.github_daily_digest.label',
    ui_description='Fetch GitHub repository updates and send a daily digest to Slack or Discord',
    ui_description_key='composite.github_daily_digest.desc',
    ui_group='Developer / GitHub',
    ui_icon='Github',
    ui_color='#333333',

    # UI form generation
    ui_params_schema={
        'owner': {
            'type': 'string',
            'label': 'Repository Owner',
            'label_key': 'composite.github_daily_digest.owner.label',
            'description': 'GitHub username or organization',
            'description_key': 'composite.github_daily_digest.owner.desc',
            'placeholder': 'facebook',
            'required': True,
            'ui_component': 'input',
        },
        'repo': {
            'type': 'string',
            'label': 'Repository Name',
            'label_key': 'composite.github_daily_digest.repo.label',
            'description': 'GitHub repository name',
            'description_key': 'composite.github_daily_digest.repo.desc',
            'placeholder': 'react',
            'required': True,
            'ui_component': 'input',
        },
        'webhook_url': {
            'type': 'string',
            'label': 'Notification Webhook URL',
            'label_key': 'composite.github_daily_digest.webhook_url.label',
            'description': 'Slack or Discord webhook URL',
            'description_key': 'composite.github_daily_digest.webhook_url.desc',
            'placeholder': '${env.SLACK_WEBHOOK_URL}',
            'required': True,
            'ui_component': 'input',
        },
        'github_token': {
            'type': 'string',
            'label': 'GitHub Token',
            'label_key': 'composite.github_daily_digest.github_token.label',
            'description': 'GitHub personal access token (optional for public repos)',
            'description_key': 'composite.github_daily_digest.github_token.desc',
            'placeholder': '${env.GITHUB_TOKEN}',
            'required': False,
            'sensitive': True,
            'ui_component': 'password',
        }
    },

    # Connection types
    input_types=['text'],
    output_types=['api_response'],

    # Steps definition
    steps=[
        {
            'id': 'get_repo',
            'module': 'api.github.get_repo',
            'params': {
                'owner': '${params.owner}',
                'repo': '${params.repo}'
            }
        },
        {
            'id': 'get_issues',
            'module': 'api.github.list_issues',
            'params': {
                'owner': '${params.owner}',
                'repo': '${params.repo}',
                'state': 'open',
                'per_page': 10
            }
        },
        {
            'id': 'format_message',
            'module': 'data.text.template',
            'params': {
                'template': 'GitHub Daily Digest\n\nRepository: ${steps.get_repo.full_name}\nStars: ${steps.get_repo.stargazers_count}\nForks: ${steps.get_repo.forks_count}\nOpen Issues: ${steps.get_repo.open_issues_count}\n\nRecent Issues:\n${steps.get_issues.formatted}'
            },
            'on_error': 'continue'
        },
        {
            'id': 'notify',
            'module': 'notification.slack.send_message',
            'params': {
                'webhook_url': '${params.webhook_url}',
                'text': '${steps.format_message.result}'
            },
            'on_error': 'continue'
        }
    ],

    # Output schema
    output_schema={
        'status': {'type': 'string'},
        'repository': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string'},
                'stars': {'type': 'number'},
                'forks': {'type': 'number'},
                'open_issues': {'type': 'number'}
            }
        },
        'notification_sent': {'type': 'boolean'}
    },

    # Execution settings
    timeout=60,
    retryable=True,
    max_retries=2,

    # Documentation
    examples=[
        {
            'name': 'React repository digest',
            'description': 'Get daily digest for React repository',
            'params': {
                'owner': 'facebook',
                'repo': 'react',
                'webhook_url': '${env.SLACK_WEBHOOK_URL}'
            }
        }
    ],
    author='Flyto Core Team',
    license='MIT'
)
class GithubDailyDigest(CompositeModule):
    """
    GitHub Daily Digest Composite Module

    This composite module:
    1. Fetches repository information from GitHub API
    2. Gets recent open issues
    3. Formats a digest message
    4. Sends notification to Slack/Discord
    """

    def _build_output(self, metadata):
        """Build output with repository stats"""
        repo_data = self.step_results.get('get_repo', {})
        notify_result = self.step_results.get('notify', {})

        return {
            'status': 'success',
            'repository': {
                'name': repo_data.get('full_name', ''),
                'stars': repo_data.get('stargazers_count', 0),
                'forks': repo_data.get('forks_count', 0),
                'open_issues': repo_data.get('open_issues_count', 0)
            },
            'notification_sent': notify_result.get('sent', False)
        }
