"""
AI Entity Memory Sub-Node
Entity extraction and tracking memory for AI Agent

Extracts and remembers entities (people, places, concepts)
from conversations for long-term context.
"""

from typing import Any, Dict, List, Optional
from ...registry import register_module
from ...schema import compose, field
from ...types import NodeType, EdgeType, DataType


@register_module(
    module_id='ai.memory.entity',
    stability="beta",
    version='1.0.0',
    category='ai',
    subcategory='memory',
    tags=['ai', 'memory', 'entity', 'extraction', 'ner', 'knowledge', 'sub-node'],
    label='Entity Memory',
    label_key='modules.ai.memory.entity.label',
    description='Extract and track entities (people, places, concepts) from conversations',
    description_key='modules.ai.memory.entity.description',
    icon='Users',
    color='#EC4899',

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
            'label_key': 'modules.ai.memory.entity.ports.memory',
            'data_type': DataType.AI_MEMORY.value,
            'edge_type': EdgeType.RESOURCE.value,
            'color': '#EC4899'
        }
    ],

    retryable=False,
    concurrent_safe=True,
    requires_credentials=False,
    handles_sensitive_data=True,
    required_permissions=['ai.memory'],

    params_schema=compose(
        field(
            'entity_types',
            type='multiselect',
            label='Entity Types',
            label_key='modules.ai.memory.entity.params.entity_types',
            description='Types of entities to extract and track',
            required=False,
            default=['person', 'organization', 'location'],
            options=[
                {'value': 'person', 'label': 'People'},
                {'value': 'organization', 'label': 'Organizations'},
                {'value': 'location', 'label': 'Locations'},
                {'value': 'date', 'label': 'Dates'},
                {'value': 'product', 'label': 'Products'},
                {'value': 'concept', 'label': 'Concepts'},
                {'value': 'event', 'label': 'Events'},
            ]
        ),
        field(
            'extraction_model',
            type='select',
            label='Extraction Model',
            label_key='modules.ai.memory.entity.params.extraction_model',
            description='Model for entity extraction',
            required=True,
            default='llm',
            options=[
                {'value': 'llm', 'label': 'LLM-based'},
                {'value': 'spacy', 'label': 'SpaCy NER'},
                {'value': 'regex', 'label': 'Rule-based'},
            ]
        ),
        field(
            'session_id',
            type='string',
            label='Session ID',
            label_key='modules.ai.memory.entity.params.session_id',
            description='Unique identifier for this memory session',
            required=False,
            default='',
            placeholder='Leave empty to auto-generate'
        ),
        field(
            'track_relationships',
            type='boolean',
            label='Track Relationships',
            label_key='modules.ai.memory.entity.params.track_relationships',
            description='Track relationships between entities',
            required=False,
            default=True
        ),
        field(
            'max_entities',
            type='number',
            label='Max Entities',
            label_key='modules.ai.memory.entity.params.max_entities',
            description='Maximum number of entities to remember',
            required=False,
            default=100,
            min=10,
            max=1000
        ),
    ),

    output_schema={
        'memory_type': {'type': 'string', 'description': 'Type of memory (entity)'},
        'session_id': {'type': 'string', 'description': 'Session identifier'},
        'entities': {'type': 'object', 'description': 'Tracked entities by type'},
        'relationships': {'type': 'array', 'description': 'Entity relationships'},
        'config': {'type': 'object', 'description': 'Full memory configuration'}
    },

    examples=[
        {
            'title': 'People & Organizations',
            'params': {
                'entity_types': ['person', 'organization'],
                'extraction_model': 'llm'
            }
        },
        {
            'title': 'Full Entity Tracking',
            'params': {
                'entity_types': ['person', 'organization', 'location', 'concept'],
                'track_relationships': True,
                'max_entities': 200
            }
        }
    ],
    author='Flyto2 Team',
    license='MIT'
)
async def ai_memory_entity(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entity-based memory for AI Agent.

    Extracts entities from conversations and maintains
    a knowledge base of people, places, and concepts.
    """
    import uuid

    params = context['params']
    entity_types = params.get('entity_types', ['person', 'organization', 'location'])
    extraction_model = params.get('extraction_model', 'llm')
    session_id = params.get('session_id') or str(uuid.uuid4())
    track_relationships = params.get('track_relationships', True)
    max_entities = params.get('max_entities', 100)

    # Initialize entity store
    entity_store = context.get('_entity_store', {
        'entities': {t: {} for t in entity_types},
        'relationships': [],
        'mentions': []
    })

    config = {
        'memory_type': 'entity',
        'session_id': session_id,
        'entity_types': entity_types,
        'extraction_model': extraction_model,
        'track_relationships': track_relationships,
        'max_entities': max_entities
    }

    return {
        'ok': True,
        '__data_type__': 'ai_memory',
        'memory_type': 'entity',
        'session_id': session_id,
        'entity_store': entity_store,
        'entities': entity_store['entities'],
        'relationships': entity_store['relationships'],
        'config': config,
        '__methods__': {
            'add_entity': '_entity_add',
            'add_relationship': '_entity_add_relationship',
            'get_entity': '_entity_get',
            'get_context': '_entity_get_context',
            'search': '_entity_search',
            'clear': '_entity_clear'
        }
    }


def _entity_add(memory_state: Dict, entity_type: str, name: str, attributes: Dict = None) -> Dict:
    """Add or update an entity"""
    import time

    store = memory_state['entity_store']
    config = memory_state['config']

    if entity_type not in store['entities']:
        store['entities'][entity_type] = {}

    # Normalize name for lookup
    key = name.lower().strip()

    if key in store['entities'][entity_type]:
        # Update existing entity
        entity = store['entities'][entity_type][key]
        entity['mention_count'] += 1
        entity['last_seen'] = time.time()
        if attributes:
            entity['attributes'].update(attributes)
    else:
        # Create new entity
        entity = {
            'name': name,
            'type': entity_type,
            'attributes': attributes or {},
            'mention_count': 1,
            'first_seen': time.time(),
            'last_seen': time.time()
        }
        store['entities'][entity_type][key] = entity

    # Track mention
    store['mentions'].append({
        'entity': key,
        'type': entity_type,
        'timestamp': time.time()
    })

    # Enforce max entities limit
    _entity_enforce_limit(memory_state)

    return entity


def _entity_add_relationship(memory_state: Dict, entity1: str, relationship: str, entity2: str) -> Dict:
    """Add a relationship between two entities"""
    import time

    store = memory_state['entity_store']

    rel = {
        'subject': entity1.lower().strip(),
        'predicate': relationship,
        'object': entity2.lower().strip(),
        'timestamp': time.time()
    }

    # Avoid duplicates
    existing = [r for r in store['relationships']
                if r['subject'] == rel['subject'] and
                r['predicate'] == rel['predicate'] and
                r['object'] == rel['object']]

    if not existing:
        store['relationships'].append(rel)

    return rel


def _entity_get(memory_state: Dict, entity_type: str, name: str) -> Optional[Dict]:
    """Get an entity by type and name"""
    store = memory_state['entity_store']
    key = name.lower().strip()

    if entity_type in store['entities']:
        return store['entities'][entity_type].get(key)
    return None


def _entity_get_context(memory_state: Dict, query: str = None) -> Dict:
    """Get entity context summary for the AI"""
    store = memory_state['entity_store']

    # Get most relevant entities
    all_entities = []
    for entity_type, entities in store['entities'].items():
        for key, entity in entities.items():
            all_entities.append(entity)

    # Sort by mention count and recency
    all_entities.sort(key=lambda e: (e['mention_count'], e['last_seen']), reverse=True)

    # Build context summary
    context = {
        'known_entities': all_entities[:20],
        'relationships': store['relationships'][-20:],
        'summary': _entity_build_summary(all_entities[:10])
    }

    return context


def _entity_search(memory_state: Dict, query: str) -> List[Dict]:
    """Search entities by name"""
    store = memory_state['entity_store']
    query_lower = query.lower()
    results = []

    for entity_type, entities in store['entities'].items():
        for key, entity in entities.items():
            if query_lower in key or query_lower in entity['name'].lower():
                results.append(entity)

    return results


def _entity_clear(memory_state: Dict) -> None:
    """Clear all entity memory"""
    config = memory_state['config']
    memory_state['entity_store'] = {
        'entities': {t: {} for t in config['entity_types']},
        'relationships': [],
        'mentions': []
    }


def _entity_enforce_limit(memory_state: Dict) -> None:
    """Remove least relevant entities if over limit"""
    store = memory_state['entity_store']
    config = memory_state['config']
    max_entities = config['max_entities']

    # Count total entities
    total = sum(len(entities) for entities in store['entities'].values())

    if total > max_entities:
        # Collect all entities with scores
        all_entities = []
        for entity_type, entities in store['entities'].items():
            for key, entity in entities.items():
                all_entities.append((entity_type, key, entity['mention_count'], entity['last_seen']))

        # Sort by relevance (mention count + recency)
        all_entities.sort(key=lambda x: (x[2], x[3]))

        # Remove least relevant
        to_remove = total - max_entities
        for entity_type, key, _, _ in all_entities[:to_remove]:
            del store['entities'][entity_type][key]


def _entity_build_summary(entities: List[Dict]) -> str:
    """Build a text summary of known entities"""
    if not entities:
        return "No entities tracked yet."

    parts = []
    for entity in entities:
        parts.append(f"- {entity['name']} ({entity['type']})")

    return "Known entities:\n" + "\n".join(parts)
