# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Stripe Payment Integration Modules

Provides payment processing operations with Stripe.

HOW FAR A STRIPE CALL IS FOLLOWED

ACCEPTED, on all three, and the conservative reading is load-bearing here in a
way it is not for a Notion page or a Jira issue: this is the file where a green
tick would be read as "the money moved".

Every module here sends one HTTPS request and reads the reply to that same
request. None reads anything back. A 200 body is Stripe reporting on Stripe's
own work, which is `http.request`'s settled position for every 2xx in this
product and the definition of taking a peer's word for it. Reaching OBSERVED
would take a second request -- retrieving the object, or the balance, or the
charge -- and no module here makes one.

WHAT `create_payment` DOES NOT DO, stated here and again in its own effects
because the module id and the label both say "payment":

  * It creates a **PaymentIntent**. That is an intent, not a charge. No card is
    charged, no funds are authorised, captured, transferred or settled by this
    module, and nothing here confirms any ever will be.
  * The `status` it returns is Stripe's own field on that object, and on a
    freshly created intent it is normally `requires_payment_method` or
    `requires_confirmation` -- i.e. the payment has NOT happened. A consumer
    that treats a successful step as a completed payment is reading the rung
    for something it does not say, so `no_funds_movement_confirmed` is attached
    as an effect of its own rather than left as a caveat in prose.
  * `client_secret` is a handle for completing the payment somewhere else,
    which is the clearest evidence in the payload that nothing is finished.

THE ERROR PATHS CARRY NOTHING, and on a payment module that is the sharpest gap
in this file. Every non-200 raises, and the `except Exception` around each body
re-raises as `RuntimeError`, so the payload is discarded and no rung survives.
A 5xx or a timeout on the create is the textbook INDETERMINATE -- the intent may
exist -- and today it arrives as an ordinary step failure. Changing a raise into
a returned error dict is a decision about step semantics, not about reporting,
so it is written down rather than made.

WORSE THAN THE MISSING RUNG, on that same path: `payment.stripe.create_payment`
declares `retryable=True, max_retries=2` and sends no `Idempotency-Key` header,
so a timeout on a POST Stripe already accepted re-runs the create and leaves a
second PaymentIntent. Stripe's API is not idempotent without that header. No
rung can fix it and none pretends to; it is reported alongside this change,
unfixed, because choosing how the key is derived changes what this module sends
to a payment API and that is not a reporting decision.
"""
import logging
import os
from typing import Any, Dict

from ...base import BaseModule
from ...registry import register_module
from ....constants import APIEndpoints, EnvVars
from ....engine.outcome import ClaimBy, Outcome, envelope


logger = logging.getLogger(__name__)


def _stripe_answered(status: int) -> Dict[str, Any]:
    """The one thing every path in this file measures: a status line came back.

    This is the whole distance between DISPATCHED and ACCEPTED. A server
    received the request, processed it far enough to choose a reply, and sent
    one. It is not an observation of anything Stripe holds -- nothing in this
    file looks at anything except the answer to the message it just sent.
    """
    return {
        'kind': 'stripe_reply_read',
        'status': status,
        'measured_by': 'response.status -- the status line of the reply to this request',
        'detail': (
            'A server received this request and chose a reply. That is what '
            'separates accepted from dispatched, and it is all it separates: no '
            'Stripe object is read back anywhere in this module.'
        ),
    }


def _simplify_charges(charges_data):
    """Extract essential fields from Stripe charge list."""
    return [{
        'id': c['id'], 'amount': c['amount'], 'currency': c['currency'],
        'status': c['status'], 'paid': c['paid'], 'created': c['created'],
        'description': c.get('description'),
    } for c in charges_data]


@register_module(
    module_id='payment.stripe.create_payment',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'http.*', 'flow.*', 'start'],
    version='1.0.0',
    category='productivity',
    subcategory='payment',
    tags=['stripe', 'payment', 'charge', 'checkout', 'ssrf_protected'],
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
    timeout_ms=30000,
    retryable=True,
    max_retries=2,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['STRIPE_API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['payment.process'],

    params_schema={
        'api_key': {
            'type': 'string',
            'label': 'API Key',
            'label_key': 'modules.payment.stripe.create_payment.params.api_key.label',
            'description': 'Stripe secret key (or use STRIPE_API_KEY env)',
            'description_key': 'modules.payment.stripe.create_payment.params.api_key.description',
            'required': False,
            'sensitive': True
        ,
            'placeholder': 'sk-...',
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
        ,
            'placeholder': 'usd',
},
        'description': {
            'type': 'string',
            'label': 'Description',
            'label_key': 'modules.payment.stripe.create_payment.params.description.label',
            'description': 'Payment description',
            'description_key': 'modules.payment.stripe.create_payment.params.description.description',
            'required': False
        ,
            'placeholder': 'Description text',
},
        'customer': {
            'type': 'string',
            'label': 'Customer ID',
            'label_key': 'modules.payment.stripe.create_payment.params.customer.label',
            'description': 'Stripe customer ID (optional)',
            'description_key': 'modules.payment.stripe.create_payment.params.customer.description',
            'required': False
        ,
            'placeholder': 'Enter customer...',
}
    },
    output_schema={
        'id': {'type': 'string', 'description': 'Unique identifier',
                'description_key': 'modules.payment.stripe.create_payment.output.id.description'},
        'amount': {'type': 'number', 'description': 'Payment amount',
                'description_key': 'modules.payment.stripe.create_payment.output.amount.description'},
        'currency': {'type': 'string', 'description': 'Currency code',
                'description_key': 'modules.payment.stripe.create_payment.output.currency.description'},
        'status': {'type': 'string', 'description': (
                    "Stripe's status for the PaymentIntent -- normally "
                    "requires_payment_method or requires_confirmation on a new one, "
                    "i.e. the payment has not been made. Not the status of this step"),
                'description_key': 'modules.payment.stripe.create_payment.output.status.description'},
        'client_secret': {'type': 'string', 'description': 'Client secret for completing the payment elsewhere',
                'description_key': 'modules.payment.stripe.create_payment.output.client_secret.description'},
        'outcome': {'type': 'object', 'description': (
                    'How far the effect was followed. Always "accepted" on the path '
                    'that returns: Stripe says it created a PaymentIntent and names '
                    'it. NOT a statement that money moved -- no charge, capture or '
                    'transfer is confirmed anywhere in this module. Error paths '
                    'raise, so they carry no outcome at all'),
                'description_key': 'modules.payment.stripe.create_payment.output.outcome.description'}
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

    def validate_params(self) -> None:
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

            # SECURITY: Set timeout to prevent hanging API calls
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
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
                        "client_secret": result.get('client_secret'),
                        "outcome": envelope(
                            Outcome.ACCEPTED,
                            claim_by=ClaimBy.NONE,
                            effects=[
                                _stripe_answered(response.status),
                                {
                                    'kind': 'payment_intent_reported_created',
                                    'payment_intent_id': result['id'],
                                    'intent_status': result['status'],
                                    'amount': result['amount'],
                                    'currency': result['currency'],
                                    'measured_by': (
                                        'id and status in the 200 body Stripe returned '
                                        'to this POST'
                                    ),
                                    'detail': (
                                        'Stripe asserting that it created a '
                                        'PaymentIntent, and naming it. The id is '
                                        'server-assigned, so it is more than an echo '
                                        'of the amount sent -- and still the peer '
                                        'reporting on its own work, so it is not an '
                                        'observation. The intent is never retrieved '
                                        'again.'
                                    ),
                                },
                                {
                                    # The effect this file exists to state
                                    # plainly. A PaymentIntent is not a payment,
                                    # and the module id says "create_payment".
                                    'kind': 'no_funds_movement_confirmed',
                                    'intent_status': result['status'],
                                    'measured_by': None,
                                    'detail': (
                                        'NOT CONFIRMED: that any card was charged, '
                                        'that funds were authorised, captured, '
                                        'transferred or settled, or that the payment '
                                        'will ever complete. Creating a PaymentIntent '
                                        'reserves an amount and a currency and hands '
                                        'back a client_secret for finishing the '
                                        'payment somewhere else; intent_status beside '
                                        'this is Stripe\'s own field on that object '
                                        'and on a new intent it normally says the '
                                        'payment still needs a method or a '
                                        'confirmation. No balance, charge, transfer or '
                                        'webhook is read anywhere in this module. The '
                                        'rung above says one thing only: Stripe '
                                        'answered and said it made the object.'
                                    ),
                                },
                            ],
                        ),
                    }

        except Exception as e:
            raise RuntimeError(f"Stripe payment creation error: {str(e)}")


@register_module(
    module_id='payment.stripe.get_customer',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'http.*', 'flow.*', 'start'],
    version='1.0.0',
    category='productivity',
    subcategory='payment',
    tags=['stripe', 'customer', 'retrieve', 'ssrf_protected'],
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
    timeout_ms=15000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['STRIPE_API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['payment.process'],

    params_schema={
        'api_key': {
            'type': 'string',
            'label': 'API Key',
            'label_key': 'modules.payment.stripe.get_customer.params.api_key.label',
            'description': 'Stripe secret key (or use STRIPE_API_KEY env)',
            'description_key': 'modules.payment.stripe.get_customer.params.api_key.description',
            'placeholder': 'sk-...',
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
        ,
            'placeholder': 'cus_xxxxx',
}
    },
    output_schema={
        'id': {'type': 'string', 'description': 'Customer id -- the one that was asked for'},
        'email': {'type': 'string', 'description': 'Email address'},
        'name': {'type': 'string', 'description': 'Name of the item'},
        'created': {'type': 'number', 'description': 'Creation timestamp'},
        'balance': {'type': 'number', 'description': (
                    "Stripe's customer balance, or a literal 0 when the body omitted "
                    "it -- see outcome.effects.balance_reported")},
        'outcome': {'type': 'object', 'description': (
                    'How far the read was followed. Always "accepted" on the path '
                    'that returns: Stripe answered with a customer object, read '
                    'once. Error paths raise, so they carry no outcome at all')}
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

    def validate_params(self) -> None:
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

            # SECURITY: Set timeout to prevent hanging API calls
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
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
                        "balance": result.get('balance', 0),
                        "outcome": envelope(
                            Outcome.ACCEPTED,
                            claim_by=ClaimBy.NONE,
                            effects=[
                                _stripe_answered(response.status),
                                {
                                    'kind': 'customer_described_by_peer',
                                    'customer_id': result['id'],
                                    # `balance` in the payload defaults to 0.
                                    # This keeps "Stripe said 0" and "this
                                    # module filled in 0" apart -- a customer
                                    # balance is money, and the two are not the
                                    # same fact.
                                    'balance_reported': 'balance' in result,
                                    'measured_by': (
                                        'the JSON body Stripe returned for this '
                                        'customer id'
                                    ),
                                    'detail': (
                                        "Stripe's own description of a customer it "
                                        'holds, read once, with nothing corroborating '
                                        'it. Note that the id in that body is the id '
                                        'this module asked for, so it is an echo and '
                                        'not evidence of anything beyond a reply '
                                        'arriving; what the reply does establish is '
                                        'that Stripe answered 200 with a customer '
                                        'object rather than refusing. When '
                                        'balance_reported is false, the balance beside '
                                        'this is a default written in this module and '
                                        'not a number Stripe sent.'
                                    ),
                                },
                            ],
                        ),
                    }

        except Exception as e:
            raise RuntimeError(f"Stripe get customer error: {str(e)}")


@register_module(
    module_id='payment.stripe.list_charges',
    can_connect_to=['*'],
    can_receive_from=['data.*', 'http.*', 'flow.*', 'start'],
    version='1.0.0',
    category='productivity',
    subcategory='payment',
    tags=['stripe', 'charges', 'list', 'transactions', 'ssrf_protected'],
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
    timeout_ms=20000,
    retryable=True,
    max_retries=3,
    concurrent_safe=True,

    # Phase 2: Security settings
    requires_credentials=True,
    credential_keys=['STRIPE_API_KEY'],
    handles_sensitive_data=True,
    required_permissions=['payment.process'],

    params_schema={
        'api_key': {
            'type': 'string',
            'label': 'API Key',
            'label_key': 'modules.payment.stripe.list_charges.params.api_key.label',
            'description': 'Stripe secret key (or use STRIPE_API_KEY env)',
            'description_key': 'modules.payment.stripe.list_charges.params.api_key.description',
            'placeholder': 'sk-...',
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
            'placeholder': 'cus_xxxxx',
            'required': False
        }
    },
    output_schema={
        'charges': {'type': 'array', 'description': 'One page of charges, bounded by limit'},
        'count': {'type': 'number', 'description': (
                    'Charges returned on this page. Not the number of charges on the '
                    'account -- no pagination cursor is followed')},
        'has_more': {'type': 'boolean', 'description': (
                    "Stripe's flag saying further pages exist, or a literal false "
                    "when the body omitted it -- see outcome.effects.has_more_reported")},
        'outcome': {'type': 'object', 'description': (
                    'How far the read was followed. Always "accepted" on the path '
                    'that returns: Stripe answered with one page of charges, read '
                    'once. Error paths raise, so they carry no outcome at all')}
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

    def validate_params(self) -> None:
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

            params = {'limit': self.limit}
            if self.customer:
                params['customer'] = self.customer
            headers = {'Authorization': f'Bearer {self.api_key}'}

            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(APIEndpoints.STRIPE_CHARGES, headers=headers, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise RuntimeError(f"Stripe API error ({response.status}): {error_text}")
                    result = await response.json()
                    status = response.status

            charges = _simplify_charges(result['data'])
            return {
                "charges": charges,
                "count": len(charges),
                "has_more": result.get('has_more', False),
                "outcome": envelope(
                    Outcome.ACCEPTED,
                    claim_by=ClaimBy.NONE,
                    effects=[
                        _stripe_answered(status),
                        {
                            'kind': 'charges_returned',
                            'count': len(charges),
                            'limit_requested': self.limit,
                            'customer_filter': self.customer,
                            'has_more': result.get('has_more', False),
                            # False means the has_more beside it was written
                            # here, not sent -- so "there are no more charges"
                            # and "Stripe did not say" stay distinguishable.
                            'has_more_reported': 'has_more' in result,
                            'measured_by': (
                                "len() over the data array Stripe returned, and "
                                "has_more in that same body"
                            ),
                            'detail': (
                                'count counts charges Stripe RETURNED on this page, '
                                'never charges that exist: limit bounds it, Stripe '
                                'paginates with starting_after which this module never '
                                'sends, and when has_more is true the account holds '
                                'charges that are not in this list. Each entry is '
                                "Stripe's record of a charge, read once -- nothing "
                                'here confirms anything about the money behind it.'
                            ),
                        },
                    ],
                ),
            }
        except Exception as e:
            raise RuntimeError(f"Stripe list charges error: {str(e)}")
