"""
Proxy Rotation Manager
Automatic proxy switching for distributed requests
"""
import random
from typing import List, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class ProxyConfig:
    """Proxy configuration"""
    url: str
    username: Optional[str] = None
    password: Optional[str] = None
    max_requests: int = 100
    current_requests: int = 0


class ProxyManager:
    """
    Manages proxy rotation for requests
    """

    def __init__(self, proxies: Optional[List[str]] = None):
        """
        Initialize proxy manager

        Args:
            proxies: List of proxy URLs
        """
        self.proxy_configs = []
        if proxies:
            for proxy_url in proxies:
                self.proxy_configs.append(ProxyConfig(url=proxy_url))

        self.current_index = 0
        self.rotation_strategy = 'round_robin'  # or 'random', 'least_used'

    def add_proxy(self, proxy_url: str, username: Optional[str] = None, password: Optional[str] = None):
        """Add a proxy to the pool"""
        self.proxy_configs.append(ProxyConfig(
            url=proxy_url,
            username=username,
            password=password
        ))

    def get_next_proxy(self) -> Optional[Dict[str, Any]]:
        """
        Get next proxy based on rotation strategy

        Returns:
            Proxy configuration or None if no proxies available
        """
        if not self.proxy_configs:
            return None

        if self.rotation_strategy == 'round_robin':
            proxy = self.proxy_configs[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxy_configs)

        elif self.rotation_strategy == 'random':
            proxy = random.choice(self.proxy_configs)

        elif self.rotation_strategy == 'least_used':
            proxy = min(self.proxy_configs, key=lambda p: p.current_requests)

        else:
            proxy = self.proxy_configs[0]

        # Increment usage
        proxy.current_requests += 1

        # Rotate if max requests reached
        if proxy.current_requests >= proxy.max_requests:
            proxy.current_requests = 0

        return {
            'http': proxy.url,
            'https': proxy.url,
            'username': proxy.username,
            'password': proxy.password
        }

    def set_strategy(self, strategy: str):
        """Set rotation strategy: round_robin, random, or least_used"""
        if strategy in ['round_robin', 'random', 'least_used']:
            self.rotation_strategy = strategy

    def get_stats(self) -> Dict[str, Any]:
        """Get proxy usage statistics"""
        return {
            'total_proxies': len(self.proxy_configs),
            'strategy': self.rotation_strategy,
            'proxies': [
                {
                    'url': p.url,
                    'requests': p.current_requests,
                    'max_requests': p.max_requests
                }
                for p in self.proxy_configs
            ]
        }

    def remove_proxy(self, proxy_url: str):
        """Remove proxy from pool"""
        self.proxy_configs = [p for p in self.proxy_configs if p.url != proxy_url]

    def clear_all(self):
        """Clear all proxies"""
        self.proxy_configs = []
        self.current_index = 0
