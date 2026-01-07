"""
GitHub Daily Digest Composite Module

Fetches GitHub repository updates and sends a daily digest notification.
"""
from ..base import CompositeModule, register_composite


@register_composite(
    module_id='composite.developer.github_daily_digest',
    label='GitHub Daily Digest',
    icon='Github',
    color='#333333',

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
                'template': 'GitHub Daily Digest\n\nRepository: ${steps.get_repo.full_name}\nStars: ${steps.get_repo.stargazers_count}\nForks: ${steps.get_repo.forks_count}\nOpen Issues: ${steps.get_repo.open_issues_count}'
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

    params_schema={
        'owner': {
            'type': 'string',
            'label': 'Repository Owner',
            'required': True,
            'placeholder': 'facebook'
        },
        'repo': {
            'type': 'string',
            'label': 'Repository Name',
            'required': True,
            'placeholder': 'react'
        },
        'webhook_url': {
            'type': 'string',
            'label': 'Notification Webhook URL',
            'required': True,
            'placeholder': '${env.SLACK_WEBHOOK_URL}'
        },
        'github_token': {
            'type': 'string',
            'label': 'GitHub Token',
            'sensitive': True,
            'placeholder': '${env.GITHUB_TOKEN}'
        }
    },

    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)'},
        'repository': {'type': 'object', 'description': 'The repository'},
        'notification_sent': {'type': 'boolean', 'description': 'The notification sent'}
    },

    timeout=60,
    retryable=True,
    max_retries=2,
)
class GithubDailyDigest(CompositeModule):
    """GitHub Daily Digest - fetch repo stats and send to Slack/Discord"""

    def _build_output(self, metadata):
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
