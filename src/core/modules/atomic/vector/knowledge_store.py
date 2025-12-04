"""
Knowledge Storage and Retrieval
Stores and retrieves vectorized knowledge in Qdrant
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
from .connector import VectorDBConnector
from .embeddings import EmbeddingGenerator


class KnowledgeStore:
    """
    Manages storage and retrieval of knowledge entries with vector embeddings
    """

    def __init__(
        self,
        connector: VectorDBConnector,
        collection_name: str = "flyto2_knowledge",
        embedding_provider: str = "local"
    ):
        """
        Initialize knowledge store

        Args:
            connector: Vector database connector
            collection_name: Name of collection to use
            embedding_provider: Embedding generator provider
        """
        self.connector = connector
        self.collection_name = collection_name
        self.embedder = EmbeddingGenerator(provider=embedding_provider)

        # Ensure collection exists
        self._ensure_collection()

    def _ensure_collection(self):
        """Ensure collection exists in database"""
        if not self.connector.collection_exists(self.collection_name):
            vector_size = self.embedder.get_dimension()
            self.connector.create_collection(
                self.collection_name,
                vector_size=vector_size
            )

    def store(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        entry_id: Optional[str] = None
    ) -> str:
        """
        Store knowledge entry with auto-generated embedding

        Args:
            content: Text content to store
            metadata: Additional metadata
            entry_id: Optional custom ID (auto-generated if not provided)

        Returns:
            ID of stored entry
        """
        from qdrant_client.models import PointStruct

        if not self.connector.is_connected():
            raise ConnectionError("Not connected to database")

        # Generate ID
        if entry_id is None:
            entry_id = str(uuid.uuid4())

        # Generate embedding
        embedding = self.embedder.generate(content)

        # Prepare payload
        payload = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }

        # Store in Qdrant
        self.connector.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=entry_id,
                    vector=embedding,
                    payload=payload
                )
            ]
        )

        return entry_id

    def store_batch(
        self,
        entries: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Store multiple knowledge entries at once

        Args:
            entries: List of dicts with 'content' and optional 'metadata'

        Returns:
            List of stored entry IDs
        """
        from qdrant_client.models import PointStruct

        if not self.connector.is_connected():
            raise ConnectionError("Not connected to database")

        # Generate embeddings for all entries
        contents = [entry["content"] for entry in entries]
        embeddings = self.embedder.generate_batch(contents)

        # Prepare points
        points = []
        ids = []

        for entry, embedding in zip(entries, embeddings):
            entry_id = entry.get("id") or str(uuid.uuid4())
            ids.append(entry_id)

            payload = {
                "content": entry["content"],
                "timestamp": datetime.now().isoformat(),
                "metadata": entry.get("metadata", {})
            }

            points.append(
                PointStruct(
                    id=entry_id,
                    vector=embedding,
                    payload=payload
                )
            )

        # Store all points
        self.connector.client.upsert(
            collection_name=self.collection_name,
            points=points
        )

        return ids

    def search(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: Optional[float] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic search for similar knowledge entries

        Args:
            query: Search query text
            top_k: Number of results to return
            score_threshold: Minimum similarity score
            filters: Metadata filters

        Returns:
            List of matching entries with scores
        """
        if not self.connector.is_connected():
            raise ConnectionError("Not connected to database")

        # Generate query embedding
        query_embedding = self.embedder.generate(query)

        # Build filter if provided
        search_filter = None
        if filters:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            conditions = []
            for key, value in filters.items():
                conditions.append(
                    FieldCondition(
                        key=f"metadata.{key}",
                        match=MatchValue(value=value)
                    )
                )

            if conditions:
                search_filter = Filter(must=conditions)

        # Search using query_points
        results = self.connector.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            limit=top_k,
            score_threshold=score_threshold,
            query_filter=search_filter
        ).points

        # Format results
        formatted = []
        for result in results:
            formatted.append({
                "id": result.id,
                "content": result.payload.get("content"),
                "metadata": result.payload.get("metadata", {}),
                "timestamp": result.payload.get("timestamp"),
                "score": result.score
            })

        return formatted

    def delete(self, entry_id: str) -> bool:
        """Delete knowledge entry by ID"""
        if not self.connector.is_connected():
            raise ConnectionError("Not connected to database")

        try:
            self.connector.client.delete(
                collection_name=self.collection_name,
                points_selector=[entry_id]
            )
            return True
        except Exception:
            return False

    def update(
        self,
        entry_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update knowledge entry

        Args:
            entry_id: ID of entry to update
            content: New content (if updating)
            metadata: New metadata (if updating)

        Returns:
            True if updated successfully
        """
        if not self.connector.is_connected():
            raise ConnectionError("Not connected to database")

        try:
            # Get existing entry
            existing = self.connector.client.retrieve(
                collection_name=self.collection_name,
                ids=[entry_id]
            )

            if not existing:
                return False

            existing_payload = existing[0].payload

            # Update content if provided
            if content is not None:
                # Generate new embedding
                embedding = self.embedder.generate(content)
                existing_payload["content"] = content
            else:
                # Keep existing embedding
                embedding = existing[0].vector

            # Update metadata if provided
            if metadata is not None:
                existing_payload["metadata"].update(metadata)

            # Update timestamp
            existing_payload["timestamp"] = datetime.now().isoformat()

            # Upsert updated entry
            from qdrant_client.models import PointStruct

            self.connector.client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=entry_id,
                        vector=embedding,
                        payload=existing_payload
                    )
                ]
            )

            return True

        except Exception:
            return False

    def list_entries(
        self,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List knowledge entries

        Args:
            limit: Maximum number of entries to return
            offset: Offset for pagination

        Returns:
            List of entries
        """
        if not self.connector.is_connected():
            raise ConnectionError("Not connected to database")

        try:
            # Scroll through points
            results, _ = self.connector.client.scroll(
                collection_name=self.collection_name,
                limit=limit,
                offset=offset
            )

            formatted = []
            for point in results:
                formatted.append({
                    "id": point.id,
                    "content": point.payload.get("content"),
                    "metadata": point.payload.get("metadata", {}),
                    "timestamp": point.payload.get("timestamp")
                })

            return formatted

        except Exception:
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Get knowledge store statistics"""
        if not self.connector.is_connected():
            return {"error": "Not connected"}

        try:
            collection_info = self.connector.client.get_collection(
                self.collection_name
            )

            return {
                "collection": self.collection_name,
                "total_entries": collection_info.points_count,
                "embedding_provider": self.embedder.provider,
                "embedding_model": self.embedder.model,
                "vector_dimension": self.embedder.get_dimension()
            }

        except Exception as e:
            return {"error": str(e)}
