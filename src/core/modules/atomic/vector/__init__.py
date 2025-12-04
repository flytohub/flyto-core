"""
Vector Database Module
Knowledge storage and retrieval with embeddings
"""
from .connector import VectorDBConnector, get_connector, close_global_connector
from .embeddings import EmbeddingGenerator, embed_text, embed_texts
from .knowledge_store import KnowledgeStore
from .auto_archive import ExperienceArchiver, AutoArchiveTrigger
from .rag import RAGRetriever, RAGFormatter, RAGPipeline
from .knowledge_manager import KnowledgeManager, KnowledgeSearch
from .quality_filter import QualityFilter, ConversationFilter, FileChangeFilter, create_filter

__all__ = [
    "VectorDBConnector",
    "get_connector",
    "close_global_connector",
    "EmbeddingGenerator",
    "embed_text",
    "embed_texts",
    "KnowledgeStore",
    "ExperienceArchiver",
    "AutoArchiveTrigger",
    "RAGRetriever",
    "RAGFormatter",
    "RAGPipeline",
    "KnowledgeManager",
    "KnowledgeSearch",
    "QualityFilter",
    "ConversationFilter",
    "FileChangeFilter",
    "create_filter"
]
