"""
Headless Browser Manager
Manages headless browser instances for JS-heavy sites
"""
from typing import Optional, Dict, Any, List
from pathlib import Path


class HeadlessManager:
    """
    Manages headless browser configuration and optimization
    """

    def __init__(self):
        self.default_config = {
            'headless': True,
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-gpu',
                '--disable-software-rasterizer',
                '--disable-extensions'
            ],
            'viewport': {'width': 1920, 'height': 1080},
            'user_agent': None,  # Use default
            'javascript_enabled': True,
            'ignore_https_errors': False
        }

        self.performance_config = {
            'block_resources': ['image', 'stylesheet', 'font'],
            'timeout': 30000,
            'wait_until': 'domcontentloaded'  # vs 'networkidle'
        }

    def get_launch_config(
        self,
        mode: str = 'default',
        **overrides
    ) -> Dict[str, Any]:
        """
        Get browser launch configuration

        Args:
            mode: Configuration mode (default, performance, stealth)
            **overrides: Override specific config values

        Returns:
            Launch configuration dict
        """
        if mode == 'performance':
            config = {
                **self.default_config,
                'args': self.default_config['args'] + [
                    '--disable-images',
                    '--blink-settings=imagesEnabled=false'
                ]
            }
        elif mode == 'stealth':
            config = {
                **self.default_config,
                'args': self.default_config['args'] + [
                    '--disable-blink-features=AutomationControlled',
                    '--exclude-switches=enable-automation',
                    '--disable-web-security'
                ]
            }
        else:
            config = self.default_config.copy()

        # Apply overrides
        config.update(overrides)

        return config

    def get_performance_config(self) -> Dict[str, Any]:
        """Get performance optimization config"""
        return self.performance_config.copy()

    def should_block_resource(self, resource_type: str) -> bool:
        """
        Check if resource type should be blocked for performance

        Args:
            resource_type: Resource type (image, stylesheet, script, etc.)

        Returns:
            True if should be blocked
        """
        return resource_type in self.performance_config['block_resources']

    def optimize_for_speed(self) -> Dict[str, Any]:
        """Get config optimized for maximum speed"""
        return {
            **self.get_launch_config('performance'),
            'performance': {
                **self.performance_config,
                'block_resources': ['image', 'stylesheet', 'font', 'media'],
                'wait_until': 'domcontentloaded'
            }
        }

    def optimize_for_stealth(self) -> Dict[str, Any]:
        """Get config optimized for stealth (avoiding detection)"""
        return {
            **self.get_launch_config('stealth'),
            'performance': {
                **self.performance_config,
                'block_resources': [],  # Don't block to appear normal
                'wait_until': 'networkidle'
            }
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get configuration statistics"""
        return {
            'default_args_count': len(self.default_config['args']),
            'blocked_resources': self.performance_config['block_resources'],
            'default_timeout': self.performance_config['timeout'],
            'viewport': self.default_config['viewport']
        }


class ResourceBlocker:
    """
    Manages resource blocking for performance
    """

    def __init__(self):
        self.blocked_types = set()
        self.blocked_patterns = []
        self.blocked_count = 0

    def block_type(self, resource_type: str):
        """Add resource type to block list"""
        self.blocked_types.add(resource_type)

    def block_pattern(self, pattern: str):
        """Add URL pattern to block list"""
        self.blocked_patterns.append(pattern)

    def should_block(self, resource_type: str, url: str) -> bool:
        """
        Check if resource should be blocked

        Args:
            resource_type: Type of resource
            url: Resource URL

        Returns:
            True if should be blocked
        """
        # Check type
        if resource_type in self.blocked_types:
            self.blocked_count += 1
            return True

        # Check patterns
        for pattern in self.blocked_patterns:
            if pattern in url:
                self.blocked_count += 1
                return True

        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get blocking statistics"""
        return {
            'blocked_types': list(self.blocked_types),
            'blocked_patterns': self.blocked_patterns,
            'total_blocked': self.blocked_count
        }
