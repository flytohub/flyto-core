"""
Browser Geolocation Module

Mock browser geolocation.
"""
from typing import Any, Dict, Optional
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets, field


@register_module(
    module_id='browser.geolocation',
    version='1.0.0',
    category='browser',
    tags=['browser', 'geolocation', 'location', 'gps', 'ssrf_protected'],
    label='Mock Geolocation',
    label_key='modules.browser.geolocation.label',
    description='Mock browser geolocation',
    description_key='modules.browser.geolocation.description',
    icon='MapPin',
    color='#0D6EFD',

    # Connection types
    input_types=['browser'],
    output_types=['object'],


    can_receive_from=['browser.*', 'flow.*'],
    can_connect_to=['browser.*', 'element.*', 'page.*', 'screenshot.*', 'flow.*'],    params_schema=compose(
        field(
            'latitude',
            type='number',
            label='Latitude',
            label_key='modules.browser.geolocation.params.latitude.label',
            placeholder='37.7749',
            description='Latitude coordinate (-90 to 90)',
            required=True,
            min=-90,
            max=90,
        ),
        field(
            'longitude',
            type='number',
            label='Longitude',
            label_key='modules.browser.geolocation.params.longitude.label',
            placeholder='-122.4194',
            description='Longitude coordinate (-180 to 180)',
            required=True,
            min=-180,
            max=180,
        ),
        field(
            'accuracy',
            type='number',
            label='Accuracy (meters)',
            label_key='modules.browser.geolocation.params.accuracy.label',
            description='Position accuracy in meters',
            default=100,
            min=0,
        ),
    ),
    output_schema={
        'status': {'type': 'string', 'description': 'Operation status (success/error)',
                'description_key': 'modules.browser.geolocation.output.status.description'},
        'location': {'type': 'object', 'description': 'The location',
                'description_key': 'modules.browser.geolocation.output.location.description'}
    },
    examples=[
        {
            'name': 'Set location to San Francisco',
            'params': {'latitude': 37.7749, 'longitude': -122.4194}
        },
        {
            'name': 'Set location with high accuracy',
            'params': {'latitude': 51.5074, 'longitude': -0.1278, 'accuracy': 10}
        },
        {
            'name': 'Set location to Tokyo',
            'params': {'latitude': 35.6762, 'longitude': 139.6503}
        }
    ],
    author='Flyto2 Team',
    license='MIT',
    timeout_ms=30000,
    required_permissions=["browser.automation"],
)
class BrowserGeolocationModule(BaseModule):
    """Mock Geolocation Module"""

    module_name = "Mock Geolocation"
    module_description = "Mock browser geolocation"
    required_permission = "browser.automation"

    def validate_params(self) -> None:
        if 'latitude' not in self.params:
            raise ValueError("Missing required parameter: latitude")
        if 'longitude' not in self.params:
            raise ValueError("Missing required parameter: longitude")

        self.latitude = self.params['latitude']
        self.longitude = self.params['longitude']
        self.accuracy = self.params.get('accuracy', 100)

        # Validate ranges
        if self.latitude < -90 or self.latitude > 90:
            raise ValueError(f"Latitude must be between -90 and 90, got: {self.latitude}")
        if self.longitude < -180 or self.longitude > 180:
            raise ValueError(f"Longitude must be between -180 and 180, got: {self.longitude}")
        if self.accuracy < 0:
            raise ValueError(f"Accuracy must be positive, got: {self.accuracy}")

    async def execute(self) -> Any:
        browser = self.context.get('browser')
        if not browser:
            raise RuntimeError("Browser not launched. Please run browser.launch first")

        context = browser._context

        # Grant geolocation permission and set location
        await context.grant_permissions(['geolocation'])
        await context.set_geolocation({
            'latitude': self.latitude,
            'longitude': self.longitude,
            'accuracy': self.accuracy
        })

        return {
            "status": "success",
            "location": {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "accuracy": self.accuracy
            }
        }
