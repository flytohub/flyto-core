"""
Math Operation Modules
Mathematical calculations and operations
"""

from typing import Any, Dict
from ...base import BaseModule
from ...registry import register_module
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
    input_types=['any'],
    output_types=['any'],

    # Phase 2: Execution settings
    # No timeout - instant math operation
    retryable=False,  # Logic errors won't fix themselves
    concurrent_safe=True,  # Stateless operation

    # Phase 2: Security settings
    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'operation': {
            'type': 'string',
            'label': 'Operation',
            'label_key': 'modules.math.calculate.params.operation.label',
            'description': 'Mathematical operation to perform',
            'description_key': 'modules.math.calculate.params.operation.description',
            'required': True,
            'options': [
                {'value': 'add', 'label': 'Add'},
                {'value': 'subtract', 'label': 'Subtract'},
                {'value': 'multiply', 'label': 'Multiply'},
                {'value': 'divide', 'label': 'Divide'},
                {'value': 'power', 'label': 'Power'},
                {'value': 'modulo', 'label': 'Modulo'},
                {'value': 'sqrt', 'label': 'Square Root'},
                {'value': 'abs', 'label': 'Absolute Value'}
            ]
        },
        'a': {
            'type': 'number',
            'label': 'First Number',
            'label_key': 'modules.math.calculate.params.a.label',
            'description': 'First operand',
            'description_key': 'modules.math.calculate.params.a.description',
            'required': True
        },
        'b': {
            'type': 'number',
            'label': 'Second Number',
            'label_key': 'modules.math.calculate.params.b.label',
            'description': 'Second operand (not required for sqrt and abs)',
            'description_key': 'modules.math.calculate.params.b.description',
            'required': False
        },
        'precision': {
            'type': 'number',
            'label': 'Decimal Precision',
            'label_key': 'modules.math.calculate.params.precision.label',
            'description': 'Number of decimal places',
            'description_key': 'modules.math.calculate.params.precision.description',
            'default': 2,
            'required': False
        }
    },
    output_schema={
        'result': {
            'type': 'number',
            'description': 'Calculation result'
        },
        'operation': {
            'type': 'string',
            'description': 'Operation performed'
        },
        'expression': {
            'type': 'string',
            'description': 'Human-readable expression'
        }
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
    author='Flyto2 Team',
    license='MIT'
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
        'result': result,
        'operation': operation,
        'expression': expression
    }
