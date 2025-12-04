"""
Stripe Payment Integration Modules

Provides payment processing operations with Stripe.
"""
import logging
import os
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module
from ....constants import APIEndpoints, EnvVars


logger = logging.getLogger(__name__)


@register_module(
    module_id='payment.stripe.create_payment',
    version='1.0.0',
    category='productivity',
    subcategory='payment',
    tags=['stripe', 'payment', 'charge', 'checkout'],
    label='Stripe Create Payment',
    label_key='modules.payment.stripe.create_payment.label',
    description='Create a payment intent with Stripe',
    description_key='modules.payment.stripe.create_payment.description',
    icon='CreditCard',
    color='#635BFF',

    # Connection types
    input_types=['json'],
    output_types=['json'],

    # Phase 2: Execution settings
    timeout=30,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['network.access', 'payment.process'],

    params_schema={
        'api_key': {
            'type': 'string',
            'label': 'API Key',
            'label_key': 'modules.payment.stripe.create_payment.params.api_key.label',
            'description': 'Stripe secret key (or use STRIPE_API_KEY env)',
            'description_key': 'modules.payment.stripe.create_payment.params.api_key.description',
            'required': False,
            'sensitive': True
        },
        'amount': {
            'type': 'number',
            'label': 'Amount',
            'label_key': 'modules.payment.stripe.create_payment.params.amount.label',
            'description': 'Amount in cents (e.g. 1000 for $10.00)',
            'description_key': 'modules.payment.stripe.create_payment.params.amount.description',
            'required': True,
            'min': 1
        },
        'currency': {
            'type': 'string',
            'label': 'Currency',
            'label_key': 'modules.payment.stripe.create_payment.params.currency.label',
            'description': 'Three-letter currency code (e.g. usd, eur)',
            'description_key': 'modules.payment.stripe.create_payment.params.currency.description',
            'default': 'usd',
            'required': False
        },
        'description': {
            'type': 'string',
            'label': 'Description',
            'label_key': 'modules.payment.stripe.create_payment.params.description.label',
            'description': 'Payment description',
            'description_key': 'modules.payment.stripe.create_payment.params.description.description',
            'required': False
        },
        'customer': {
            'type': 'string',
            'label': 'Customer ID',
            'label_key': 'modules.payment.stripe.create_payment.params.customer.label',
            'description': 'Stripe customer ID (optional)',
            'description_key': 'modules.payment.stripe.create_payment.params.customer.description',
            'required': False
        }
    },
    output_schema={
        'id': {'type': 'string'},
        'amount': {'type': 'number'},
        'currency': {'type': 'string'},
        'status': {'type': 'string'},
        'client_secret': {'type': 'string'}
    },
    examples=[
        {
            'title': 'Create $50 payment',
            'params': {
                'amount': 5000,
                'currency': 'usd',
                'description': 'Product purchase'
            }
        },
        {
            'title': 'Create payment for customer',
            'params': {
                'amount': 2999,
                'currency': 'usd',
                'customer': 'cus_XXXXXXXXXXXXXXX',
                'description': 'Subscription payment'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class StripeCreatePaymentModule(BaseModule):
    """Stripe Create Payment Intent Module"""

    def validate_params(self):
        self.api_key = self.params.get('api_key')
        self.amount = self.params.get('amount')
        self.currency = self.params.get('currency', 'usd')
        self.description = self.params.get('description')
        self.customer = self.params.get('customer')

        if not self.api_key:
            self.api_key = os.environ.get(EnvVars.STRIPE_API_KEY)
            if not self.api_key:
                raise ValueError(f"api_key or {EnvVars.STRIPE_API_KEY} environment variable is required")

        if not self.amount:
            raise ValueError("amount is required")

    async def execute(self) -> Any:
        try:
            import aiohttp

            # Build request body
            data = {
                'amount': int(self.amount),
                'currency': self.currency
            }
            if self.description:
                data['description'] = self.description
            if self.customer:
                data['customer'] = self.customer

            # Make API request
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    APIEndpoints.STRIPE_PAYMENT_INTENTS,
                    headers=headers,
                    data=data
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(f"Stripe API error ({response.status}): {error_text}")

                    result = await response.json()

                    return {
                        "id": result['id'],
                        "amount": result['amount'],
                        "currency": result['currency'],
                        "status": result['status'],
                        "client_secret": result.get('client_secret')
                    }

        except Exception as e:
            raise RuntimeError(f"Stripe payment creation error: {str(e)}")


@register_module(
    module_id='payment.stripe.get_customer',
    version='1.0.0',
    category='productivity',
    subcategory='payment',
    tags=['stripe', 'customer', 'retrieve'],
    label='Stripe Get Customer',
    label_key='modules.payment.stripe.get_customer.label',
    description='Retrieve customer information from Stripe',
    description_key='modules.payment.stripe.get_customer.description',
    icon='User',
    color='#635BFF',

    # Connection types
    input_types=['text'],
    output_types=['json'],

    # Phase 2: Execution settings
    timeout=15,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['network.access', 'payment.read'],

    params_schema={
        'api_key': {
            'type': 'string',
            'label': 'API Key',
            'label_key': 'modules.payment.stripe.get_customer.params.api_key.label',
            'description': 'Stripe secret key (or use STRIPE_API_KEY env)',
            'description_key': 'modules.payment.stripe.get_customer.params.api_key.description',
            'required': False,
            'sensitive': True
        },
        'customer_id': {
            'type': 'string',
            'label': 'Customer ID',
            'label_key': 'modules.payment.stripe.get_customer.params.customer_id.label',
            'description': 'Stripe customer ID',
            'description_key': 'modules.payment.stripe.get_customer.params.customer_id.description',
            'required': True
        }
    },
    output_schema={
        'id': {'type': 'string'},
        'email': {'type': 'string'},
        'name': {'type': 'string'},
        'created': {'type': 'number'},
        'balance': {'type': 'number'}
    },
    examples=[
        {
            'title': 'Get customer info',
            'params': {
                'customer_id': 'cus_XXXXXXXXXXXXXXX'
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class StripeGetCustomerModule(BaseModule):
    """Stripe Get Customer Module"""

    def validate_params(self):
        self.api_key = self.params.get('api_key')
        self.customer_id = self.params.get('customer_id')

        if not self.api_key:
            self.api_key = os.environ.get(EnvVars.STRIPE_API_KEY)
            if not self.api_key:
                raise ValueError(f"api_key or {EnvVars.STRIPE_API_KEY} environment variable is required")

        if not self.customer_id:
            raise ValueError("customer_id is required")

    async def execute(self) -> Any:
        try:
            import aiohttp

            # Make API request
            headers = {
                'Authorization': f'Bearer {self.api_key}'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{APIEndpoints.STRIPE_CUSTOMERS}/{self.customer_id}",
                    headers=headers
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(f"Stripe API error ({response.status}): {error_text}")

                    result = await response.json()

                    return {
                        "id": result['id'],
                        "email": result.get('email'),
                        "name": result.get('name'),
                        "created": result.get('created'),
                        "balance": result.get('balance', 0)
                    }

        except Exception as e:
            raise RuntimeError(f"Stripe get customer error: {str(e)}")


@register_module(
    module_id='payment.stripe.list_charges',
    version='1.0.0',
    category='productivity',
    subcategory='payment',
    tags=['stripe', 'charges', 'list', 'transactions'],
    label='Stripe List Charges',
    label_key='modules.payment.stripe.list_charges.label',
    description='List recent charges from Stripe',
    description_key='modules.payment.stripe.list_charges.description',
    icon='List',
    color='#635BFF',

    # Connection types
    input_types=['json'],
    output_types=['array', 'json'],

    # Phase 2: Execution settings
    timeout=20,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    handles_sensitive_data=True,
    required_permissions=['network.access', 'payment.read'],

    params_schema={
        'api_key': {
            'type': 'string',
            'label': 'API Key',
            'label_key': 'modules.payment.stripe.list_charges.params.api_key.label',
            'description': 'Stripe secret key (or use STRIPE_API_KEY env)',
            'description_key': 'modules.payment.stripe.list_charges.params.api_key.description',
            'required': False,
            'sensitive': True
        },
        'limit': {
            'type': 'number',
            'label': 'Limit',
            'label_key': 'modules.payment.stripe.list_charges.params.limit.label',
            'description': 'Number of charges to return (1-100)',
            'description_key': 'modules.payment.stripe.list_charges.params.limit.description',
            'default': 10,
            'min': 1,
            'max': 100,
            'required': False
        },
        'customer': {
            'type': 'string',
            'label': 'Customer ID',
            'label_key': 'modules.payment.stripe.list_charges.params.customer.label',
            'description': 'Filter by customer ID (optional)',
            'description_key': 'modules.payment.stripe.list_charges.params.customer.description',
            'required': False
        }
    },
    output_schema={
        'charges': {'type': 'array'},
        'count': {'type': 'number'},
        'has_more': {'type': 'boolean'}
    },
    examples=[
        {
            'title': 'List recent charges',
            'params': {
                'limit': 20
            }
        },
        {
            'title': 'List customer charges',
            'params': {
                'customer': 'cus_XXXXXXXXXXXXXXX',
                'limit': 50
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
class StripeListChargesModule(BaseModule):
    """Stripe List Charges Module"""

    def validate_params(self):
        self.api_key = self.params.get('api_key')
        self.limit = self.params.get('limit', 10)
        self.customer = self.params.get('customer')

        if not self.api_key:
            self.api_key = os.environ.get(EnvVars.STRIPE_API_KEY)
            if not self.api_key:
                raise ValueError(f"api_key or {EnvVars.STRIPE_API_KEY} environment variable is required")

    async def execute(self) -> Any:
        try:
            import aiohttp

            # Build query parameters
            params = {
                'limit': self.limit
            }
            if self.customer:
                params['customer'] = self.customer

            # Make API request
            headers = {
                'Authorization': f'Bearer {self.api_key}'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    APIEndpoints.STRIPE_CHARGES,
                    headers=headers,
                    params=params
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(f"Stripe API error ({response.status}): {error_text}")

                    result = await response.json()

                    # Simplify charge data
                    simplified_charges = []
                    for charge in result['data']:
                        simplified_charges.append({
                            'id': charge['id'],
                            'amount': charge['amount'],
                            'currency': charge['currency'],
                            'status': charge['status'],
                            'paid': charge['paid'],
                            'created': charge['created'],
                            'description': charge.get('description')
                        })

                    return {
                        "charges": simplified_charges,
                        "count": len(simplified_charges),
                        "has_more": result.get('has_more', False)
                    }

        except Exception as e:
            raise RuntimeError(f"Stripe list charges error: {str(e)}")
