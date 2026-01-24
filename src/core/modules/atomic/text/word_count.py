"""
Word Count Module
Count words in text
"""
from typing import Any, Dict
import re

from ...registry import register_module
from ...errors import ValidationError


@register_module(
    module_id='text.word_count',
    version='1.0.0',
    category='text',
    tags=['text', 'word', 'count', 'analysis', 'statistics'],
    label='Word Count',
    label_key='modules.text.word_count.label',
    description='Count words in text',
    description_key='modules.text.word_count.description',
    icon='FileText',
    color='#F59E0B',
    input_types=['string'],
    output_types=['object'],

    can_receive_from=['*'],
    can_connect_to=['data.*', 'flow.*', 'notification.*'],

    retryable=False,
    concurrent_safe=True,

    requires_credentials=False,
    handles_sensitive_data=False,
    required_permissions=[],

    params_schema={
        'text': {
            'type': 'text',
            'label': 'Text',
            'label_key': 'modules.text.word_count.params.text.label',
            'description': 'Text to analyze',
            'description_key': 'modules.text.word_count.params.text.description',
            'placeholder': 'Enter text to count words',
            'required': True
        }
    },
    output_schema={
        'word_count': {
            'type': 'number',
            'description': 'Total word count',
            'description_key': 'modules.text.word_count.output.word_count.description'
        },
        'unique_words': {
            'type': 'number',
            'description': 'Number of unique words',
            'description_key': 'modules.text.word_count.output.unique_words.description'
        },
        'sentence_count': {
            'type': 'number',
            'description': 'Approximate sentence count',
            'description_key': 'modules.text.word_count.output.sentence_count.description'
        },
        'paragraph_count': {
            'type': 'number',
            'description': 'Paragraph count',
            'description_key': 'modules.text.word_count.output.paragraph_count.description'
        },
        'avg_word_length': {
            'type': 'number',
            'description': 'Average word length',
            'description_key': 'modules.text.word_count.output.avg_word_length.description'
        }
    },
    timeout_ms=5000,
)
async def text_word_count(context: Dict[str, Any]) -> Dict[str, Any]:
    """Count words in text."""
    params = context['params']
    text = params.get('text')

    if text is None:
        raise ValidationError("Missing required parameter: text", field="text")

    text = str(text)

    words = re.findall(r'\b\w+\b', text, re.UNICODE)
    word_count = len(words)

    unique_words = len(set(word.lower() for word in words))

    sentences = re.split(r'[.!?]+', text)
    sentence_count = len([s for s in sentences if s.strip()])

    paragraphs = text.split('\n\n')
    paragraph_count = len([p for p in paragraphs if p.strip()])

    avg_word_length = 0.0
    if word_count > 0:
        total_length = sum(len(word) for word in words)
        avg_word_length = round(total_length / word_count, 2)

    return {
        'ok': True,
        'data': {
            'word_count': word_count,
            'unique_words': unique_words,
            'sentence_count': sentence_count,
            'paragraph_count': paragraph_count,
            'avg_word_length': avg_word_length
        }
    }
