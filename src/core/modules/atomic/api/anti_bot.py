"""
Anti-Bot Detection and Evasion
Detects and responds to anti-bot mechanisms
"""
import re
from typing import Dict, Any, Optional, List


class AntiBotDetector:
    """
    Detects anti-bot mechanisms in responses
    """

    # Common anti-bot indicators
    BOT_INDICATORS = [
        'captcha',
        'recaptcha',
        'hcaptcha',
        'cloudflare',
        'access denied',
        'blocked',
        'bot detected',
        'unusual traffic',
        'verify you are human',
        'security check',
        'ray id',
        'cf-ray'
    ]

    def __init__(self):
        self.detection_count = 0
        self.detections = []

    def detect(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect anti-bot mechanisms in response

        Args:
            response: HTTP response dict with status, headers, body

        Returns:
            Detection result with indicators found
        """
        indicators_found = []
        detection_type = None

        # Check status code
        status = response.get('status', 200)
        if status in [403, 429, 503]:
            indicators_found.append(f'status_{status}')

        # Check headers
        headers = response.get('headers', {})
        if isinstance(headers, dict):
            for header_name, header_value in headers.items():
                header_lower = header_name.lower()
                value_lower = str(header_value).lower()

                if 'cf-ray' in header_lower or 'cloudflare' in value_lower:
                    indicators_found.append('cloudflare')
                    detection_type = 'cloudflare'

                if 'captcha' in value_lower:
                    indicators_found.append('captcha')
                    detection_type = 'captcha'

        # Check body content
        body = response.get('body', '')
        if isinstance(body, str):
            body_lower = body.lower()

            for indicator in self.BOT_INDICATORS:
                if indicator in body_lower:
                    indicators_found.append(indicator)

                    if 'captcha' in indicator:
                        detection_type = 'captcha'
                    elif 'cloudflare' in indicator:
                        detection_type = 'cloudflare'
                    elif not detection_type:
                        detection_type = 'generic_block'

        is_detected = len(indicators_found) > 0

        if is_detected:
            self.detection_count += 1
            self.detections.append({
                'timestamp': None,
                'type': detection_type,
                'indicators': indicators_found
            })

        return {
            'detected': is_detected,
            'detection_type': detection_type,
            'indicators': indicators_found,
            'confidence': self._calculate_confidence(indicators_found),
            'suggested_action': self._suggest_action(detection_type)
        }

    def _calculate_confidence(self, indicators: List[str]) -> float:
        """Calculate detection confidence score"""
        if not indicators:
            return 0.0

        # More indicators = higher confidence
        base_confidence = min(len(indicators) * 0.3, 1.0)

        # Strong indicators boost confidence
        strong_indicators = ['captcha', 'recaptcha', 'cloudflare', 'status_403']
        if any(ind in indicators for ind in strong_indicators):
            base_confidence = min(base_confidence + 0.3, 1.0)

        return base_confidence

    def _suggest_action(self, detection_type: Optional[str]) -> str:
        """Suggest action based on detection type"""
        if detection_type == 'captcha':
            return 'human_intervention_required'
        elif detection_type == 'cloudflare':
            return 'retry_with_delay'
        elif detection_type == 'generic_block':
            return 'rotate_proxy_or_user_agent'
        else:
            return 'none'

    def get_stats(self) -> Dict[str, Any]:
        """Get detection statistics"""
        detection_types = {}
        for detection in self.detections:
            det_type = detection.get('type', 'unknown')
            detection_types[det_type] = detection_types.get(det_type, 0) + 1

        return {
            'total_detections': self.detection_count,
            'detection_types': detection_types,
            'recent_detections': self.detections[-10:]  # Last 10
        }


class UserAgentRotator:
    """
    Rotates user agents to avoid detection
    """

    DEFAULT_USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
    ]

    def __init__(self, user_agents: Optional[List[str]] = None):
        self.user_agents = user_agents or self.DEFAULT_USER_AGENTS
        self.current_index = 0

    def get_next(self) -> str:
        """Get next user agent"""
        ua = self.user_agents[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.user_agents)
        return ua

    def add_user_agent(self, user_agent: str):
        """Add user agent to rotation pool"""
        if user_agent not in self.user_agents:
            self.user_agents.append(user_agent)

    def get_random(self) -> str:
        """Get random user agent"""
        import random
        return random.choice(self.user_agents)
