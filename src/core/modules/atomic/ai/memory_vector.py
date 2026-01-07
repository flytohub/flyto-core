"""
AI Vector Memory Sub-Node
Vector-based semantic memory using embeddings for AI Agent

Stores conversation history with embeddings and retrieves
relevant context using semantic similarity search.
"""

from typing import Any, Dict, List, Optional
from ...registry import register_module
from ...schema import compose, field
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='ai.memory.vector',
    stability="beta",
    version='1.0.0',
    category='ai',
    subcategory='memory',
    tags=['ai', 'memory', 'vector', 'embeddings', 'semantic', 'rag', 'sub-node'],
    label='Vector Memory',
    label_key='modules.ai.memory.vector.label',
    description='Semantic memory using vector embeddings for relevant context retrieval',
    description_key='modules.ai.memory.vector.description',
    icon='Database',
    color='#8B5CF6',

    node_type=NodeType.AI_SUB_NODE,
    input_types=[],
    output_types=['ai_memory'],
    can_receive_from=[],
    can_connect_to=['llm.agent'],
    input_ports=[],

    output_ports=[
        {
            'id': 'memory',
            'label': 'Memory',
            'label_key': 'modules.ai.memory.vector.ports.memory',
            'data_type': DataType.AI_MEMORY.value,
            'edge_type': EdgeType.RESOURCE.value,
            'color': '#8B5CF6'
        }
    ],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['ai.memory'],

    params_schema=compose(
        field(
            'embedding_model',
            type='select',
            label='Embedding Model',
            label_key='modules.ai.memory.vector.params.embedding_model',
            description='Model to use for generating embeddings',
            required=True,
            default='text-embedding-3-small',
            options=[
                {'value': 'text-embedding-3-small', 'label': 'OpenAI Small'},
                {'value': 'text-embedding-3-large', 'label': 'OpenAI Large'},
                {'value': 'text-embedding-ada-002', 'label': 'OpenAI Ada'},
                {'value': 'local', 'label': 'Local Model'},
            ]
        ),
        field(
            'top_k',
            type='number',
            label='Top K Results',
            label_key='modules.ai.memory.vector.params.top_k',
            description='Number of most relevant memories to retrieve',
            required=False,
            default=5,
            min=1,
            max=50
        ),
        field(
            'similarity_threshold',
            type='number',
            label='Similarity Threshold',
            label_key='modules.ai.memory.vector.params.similarity_threshold',
            description='Minimum similarity score (0-1) for retrieval',
            required=False,
            default=0.7,
            min=0,
            max=1,
            step=0.1
        ),
        field(
            'session_id',
            type='string',
            label='Session ID',
            label_key='modules.ai.memory.vector.params.session_id',
            description='Unique identifier for this memory session',
            required=False,
            default='',
            placeholder='Leave empty to auto-generate'
        ),
        field(
            'include_metadata',
            type='boolean',
            label='Include Metadata',
            label_key='modules.ai.memory.vector.params.include_metadata',
            description='Include timestamp and other metadata with memories',
            required=False,
            default=True
        ),
    ),

    output_schema={
        'memory_type': {'type': 'string', 'description': 'Type of memory (vector)',
                'description_key': 'modules.ai.memory.vector.output.memory_type.description'},
        'session_id': {'type': 'string', 'description': 'Session identifier',
                'description_key': 'modules.ai.memory.vector.output.session_id.description'},
        'embedding_model': {'type': 'string', 'description': 'Embedding model used',
                'description_key': 'modules.ai.memory.vector.output.embedding_model.description'},
        'config': {'type': 'object', 'description': 'Full memory configuration',
                'description_key': 'modules.ai.memory.vector.output.config.description'}
    },

    examples=[
        {
            'title': 'Default Vector Memory',
            'params': {
                'embedding_model': 'text-embedding-3-small',
                'top_k': 5
            }
        },
        {
            'title': 'High Precision Memory',
            'params': {
                'embedding_model': 'text-embedding-3-large',
                'top_k': 10,
                'similarity_threshold': 0.85
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def ai_memory_vector(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Vector-based semantic memory for AI Agent.

    Stores messages with embeddings and retrieves relevant context
    using cosine similarity search.
    """
    import uuid
    import time

    params = context['params']
    embedding_model = params.get('embedding_model', 'text-embedding-3-small')
    top_k = params.get('top_k', 5)
    similarity_threshold = params.get('similarity_threshold', 0.7)
    session_id = params.get('session_id') or str(uuid.uuid4())
    include_metadata = params.get('include_metadata', True)

    # Initialize vector store (in-memory for now)
    vector_store = context.get('_vector_store', {
        'embeddings': [],
        'messages': [],
        'metadata': []
    })

    config = {
        'memory_type': 'vector',
        'session_id': session_id,
        'embedding_model': embedding_model,
        'top_k': top_k,
        'similarity_threshold': similarity_threshold,
        'include_metadata': include_metadata
    }

    return {
        'ok': True,
        '__data_type__': 'ai_memory',
        'memory_type': 'vector',
        'session_id': session_id,
        'embedding_model': embedding_model,
        'vector_store': vector_store,
        'config': config,
        '__methods__': {
            'add_message': '_vector_add_message',
            'search': '_vector_search',
            'get_relevant': '_vector_get_relevant',
            'clear': '_vector_clear'
        }
    }


async def _vector_add_message(memory_state: Dict, role: str, content: str, embedding: List[float] = None) -> None:
    """Add a message with its embedding to vector memory"""
    import time

    store = memory_state['vector_store']

    message = {
        'role': role,
        'content': content
    }

    metadata = {
        'timestamp': time.time(),
        'index': len(store['messages'])
    }

    store['messages'].append(message)
    store['metadata'].append(metadata)

    # Store embedding if provided
    if embedding:
        store['embeddings'].append(embedding)
    else:
        # Placeholder - actual embedding would be generated
        store['embeddings'].append([0.0] * 1536)


def _vector_search(memory_state: Dict, query_embedding: List[float], top_k: int = None) -> List[Dict]:
    """Search for similar messages using cosine similarity"""
    import math

    store = memory_state['vector_store']
    config = memory_state['config']

    top_k = top_k or config['top_k']
    threshold = config['similarity_threshold']

    results = []

    for i, emb in enumerate(store['embeddings']):
        # Cosine similarity
        dot_product = sum(a * b for a, b in zip(query_embedding, emb))
        norm_a = math.sqrt(sum(a * a for a in query_embedding))
        norm_b = math.sqrt(sum(b * b for b in emb))

        if norm_a > 0 and norm_b > 0:
            similarity = dot_product / (norm_a * norm_b)
        else:
            similarity = 0

        if similarity >= threshold:
            results.append({
                'message': store['messages'][i],
                'metadata': store['metadata'][i],
                'similarity': similarity
            })

    # Sort by similarity and return top_k
    results.sort(key=lambda x: x['similarity'], reverse=True)
    return results[:top_k]


def _vector_get_relevant(memory_state: Dict, query: str) -> List[Dict]:
    """Get relevant messages for a query (placeholder for embedding generation)"""
    # In production, this would generate embedding for query
    # and call _vector_search
    return memory_state['vector_store']['messages'][-5:]


def _vector_clear(memory_state: Dict) -> None:
    """Clear all vector memory"""
    memory_state['vector_store'] = {
        'embeddings': [],
        'messages': [],
        'metadata': []
    }
