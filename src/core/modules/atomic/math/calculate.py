"""
Math Operation Modules
Mathematical calculations and operations
"""

from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
from ...schema import compose, presets
from ...errors import ValidationError, InvalidValueError
import math


@register_module(
    module_id='math.calculate',
    version='1.0.0',
    category='atomic',
    subcategory='math',
    tags=['math', 'calculate', 'arithmetic', 'atomic'],
    label='Calculate',
    label_key='modules.math.calculate.label',
    description='Perform basic mathematical operations',
    description_key='modules.math.calculate.description',
    icon='Calculator',
    color='#F59E0B',

    # Connection types
    input_types=['number'],
    output_types=['number'],


    can_receive_from=['*'],
    can_connect_to=['*'],    # Phase 2: Execution settings
    # No timeout - instant math operation
    retryable=False,  # Logic errors won't fix themselves
    concurrent_safe=True,  # Stateless operation

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    # Schema-driven params
    params_schema=compose(
        presets.MATH_OPERATION(required=True),
        presets.FIRST_OPERAND(required=True),
        presets.SECOND_OPERAND(required=False),
        presets.DECIMAL_PRECISION(default=2),
    ),
    output_schema={
        'result': {
            'type': 'number',
            'description': 'Calculation result'
        ,
                'description_key': 'modules.math.calculate.output.result.description'},
        'operation': {
            'type': 'string',
            'description': 'Operation performed'
        ,
                'description_key': 'modules.math.calculate.output.operation.description'},
        'expression': {
            'type': 'string',
            'description': 'Human-readable expression'
        ,
                'description_key': 'modules.math.calculate.output.expression.description'}
    },
    examples=[
        {
            'title': 'Add two numbers',
            'title_key': 'modules.math.calculate.examples.add.title',
            'params': {
                'operation': 'add',
                'a': 10,
                'b': 5
            }
        },
        {
            'title': 'Calculate power',
            'title_key': 'modules.math.calculate.examples.power.title',
            'params': {
                'operation': 'power',
                'a': 2,
                'b': 8
            }
        }
    ],
    author='Flyto Team',
    license='MIT',
    timeout_ms=5000,
)
async def math_calculate(context):
    """Perform mathematical operations"""
    params = context['params']
    operation = params['operation']
    a = params['a']
    b = params.get('b')
    precision = params.get('precision', 2)

    result = None
    expression = ""

    if operation == 'add':
        result = a + b
        expression = f"{a} + {b} = {result}"
    elif operation == 'subtract':
        result = a - b
        expression = f"{a} - {b} = {result}"
    elif operation == 'multiply':
        result = a * b
        expression = f"{a} × {b} = {result}"
    elif operation == 'divide':
        if b == 0:
            raise ValueError("Division by zero is not allowed")
        result = a / b
        expression = f"{a} ÷ {b} = {result}"
    elif operation == 'power':
        result = a ** b
        expression = f"{a}^{b} = {result}"
    elif operation == 'modulo':
        result = a % b
        expression = f"{a} mod {b} = {result}"
    elif operation == 'sqrt':
        if a < 0:
            raise ValueError("Cannot calculate square root of negative number")
        result = math.sqrt(a)
        expression = f"√{a} = {result}"
    elif operation == 'abs':
        result = abs(a)
        expression = f"|{a}| = {result}"

    # Round to specified precision
    if precision is not None:
        result = round(result, precision)

    return {
        'ok': True,
        'data': {
            'result': result,
            'operation': operation,
            'expression': expression
        }
    }
