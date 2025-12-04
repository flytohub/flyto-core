"""
Knowledge Base Management
Manage, clean, and optimize vector database
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from .knowledge_store import KnowledgeStore
from .embeddings import EmbeddingGenerator


class KnowledgeManager:
    """
    Manages knowledge base operations
    """

    def __init__(self, knowledge_store: KnowledgeStore):
        """
        Initialize knowledge manager

        Args:
            knowledge_store: KnowledgeStore instance
        """
        self.store = knowledge_store

    def list_all(
        self,
        limit: int = 100,
        offset: int = 0,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List all knowledge entries

        Args:
            limit: Maximum entries to return
            offset: Offset for pagination
            category: Optional category filter

        Returns:
            List of knowledge entries
        """
        entries = self.store.list_entries(limit=limit, offset=offset)

        if category:
            entries = [
                e for e in entries
                if e.get("metadata", {}).get("category") == category
            ]

        return entries

    def filter_by_source(self, source: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Filter entries by source

        Args:
            source: Source identifier
            limit: Maximum entries

        Returns:
            Filtered entries
        """
        all_entries = self.store.list_entries(limit=limit * 2)

        filtered = [
            e for e in all_entries
            if source in e.get("metadata", {}).get("source", "")
        ]

        return filtered[:limit]

    def filter_by_category(
        self,
        category: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Filter entries by category

        Args:
            category: Category name
            limit: Maximum entries

        Returns:
            Filtered entries
        """
        all_entries = self.store.list_entries(limit=limit * 2)

        filtered = [
            e for e in all_entries
            if e.get("metadata", {}).get("category") == category
        ]

        return filtered[:limit]

    def find_duplicates(
        self,
        similarity_threshold: float = 0.99
    ) -> List[tuple]:
        """
        Find duplicate or near-duplicate entries

        Args:
            similarity_threshold: Similarity threshold for duplicates

        Returns:
            List of (id1, id2, similarity) tuples
        """
        duplicates = []
        entries = self.store.list_entries(limit=500)

        # Compare each entry with others
        for i, entry1 in enumerate(entries):
            for entry2 in entries[i+1:]:
                # Search for similarity
                results = self.store.search(
                    query=entry1["content"],
                    top_k=2
                )

                for result in results:
                    if result["id"] == entry2["id"]:
                        if result["score"] >= similarity_threshold:
                            duplicates.append((
                                entry1["id"],
                                entry2["id"],
                                result["score"]
                            ))
                        break

        return duplicates

    def delete_old_entries(
        self,
        days_old: int = 90,
        category: Optional[str] = None
    ) -> int:
        """
        Delete entries older than specified days

        Args:
            days_old: Age threshold in days
            category: Optional category filter

        Returns:
            Number of entries deleted
        """
        cutoff_date = datetime.now() - timedelta(days=days_old)
        entries = self.store.list_entries(limit=1000)

        deleted_count = 0

        for entry in entries:
            timestamp_str = entry.get("metadata", {}).get("timestamp")
            if not timestamp_str:
                continue

            try:
                entry_date = datetime.fromisoformat(timestamp_str)

                if entry_date < cutoff_date:
                    # Check category filter
                    if category:
                        entry_category = entry.get("metadata", {}).get("category")
                        if entry_category != category:
                            continue

                    # Delete entry
                    if self.store.delete(entry["id"]):
                        deleted_count += 1

            except Exception:
                continue

        return deleted_count

    def cleanup_duplicates(
        self,
        similarity_threshold: float = 0.99,
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Remove duplicate entries

        Args:
            similarity_threshold: Similarity threshold
            dry_run: If True, don't actually delete

        Returns:
            Cleanup stats
        """
        duplicates = self.find_duplicates(similarity_threshold)

        deleted_ids = []
        kept_ids = []

        for id1, id2, score in duplicates:
            # Keep first, delete second
            kept_ids.append(id1)

            if not dry_run:
                if self.store.delete(id2):
                    deleted_ids.append(id2)
            else:
                deleted_ids.append(id2)

        return {
            "duplicates_found": len(duplicates),
            "entries_deleted": len(deleted_ids),
            "entries_kept": len(set(kept_ids)),
            "dry_run": dry_run,
            "deleted_ids": deleted_ids
        }

    def reindex_collection(
        self,
        embedding_provider: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Reindex collection with new embeddings

        Args:
            embedding_provider: New embedding provider (optional)

        Returns:
            Reindex stats
        """
        # Get all entries
        entries = self.store.list_entries(limit=1000)

        if not entries:
            return {"status": "no_entries"}

        # Update embedding provider if specified
        if embedding_provider:
            old_provider = self.store.embedder.provider
            self.store.embedder = EmbeddingGenerator(provider=embedding_provider)
            provider_changed = True
        else:
            old_provider = self.store.embedder.provider
            provider_changed = False

        # Reindex each entry
        reindexed = 0

        for entry in entries:
            try:
                # Update with same content (regenerates embedding)
                if self.store.update(
                    entry_id=entry["id"],
                    content=entry["content"]
                ):
                    reindexed += 1
            except Exception:
                continue

        return {
            "total_entries": len(entries),
            "reindexed": reindexed,
            "provider_changed": provider_changed,
            "old_provider": old_provider if provider_changed else None,
            "new_provider": self.store.embedder.provider
        }

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get knowledge base statistics

        Returns:
            Comprehensive statistics
        """
        entries = self.store.list_entries(limit=1000)

        # Count by category
        categories = {}
        sources = {}
        total_content_length = 0

        for entry in entries:
            metadata = entry.get("metadata", {})

            # Count categories
            category = metadata.get("category", "unknown")
            categories[category] = categories.get(category, 0) + 1

            # Count sources
            source = metadata.get("source", "unknown")
            sources[source] = sources.get(source, 0) + 1

            # Content length
            total_content_length += len(entry.get("content", ""))

        store_stats = self.store.get_stats()

        return {
            "total_entries": len(entries),
            "categories": categories,
            "sources": sources,
            "avg_content_length": total_content_length // len(entries) if entries else 0,
            "embedding_provider": store_stats.get("embedding_provider"),
            "vector_dimension": store_stats.get("vector_dimension"),
            "collection": store_stats.get("collection")
        }

    def export_entries(
        self,
        output_file: str,
        format: str = "json"
    ) -> bool:
        """
        Export knowledge entries to file

        Args:
            output_file: Output file path
            format: Export format (json, csv)

        Returns:
            True if successful
        """
        import json
        from pathlib import Path

        entries = self.store.list_entries(limit=10000)

        try:
            output_path = Path(output_file)

            if format == "json":
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(entries, f, indent=2, ensure_ascii=False)

            elif format == "csv":
                import csv

                with open(output_path, 'w', encoding='utf-8', newline='') as f:
                    if not entries:
                        return False

                    # Get all possible keys
                    all_keys = set()
                    for entry in entries:
                        all_keys.update(entry.keys())
                        all_keys.update(entry.get("metadata", {}).keys())

                    writer = csv.DictWriter(f, fieldnames=sorted(all_keys))
                    writer.writeheader()

                    for entry in entries:
                        # Flatten metadata
                        row = {**entry}
                        metadata = row.pop("metadata", {})
                        row.update({f"meta_{k}": v for k, v in metadata.items()})
                        writer.writerow(row)

            return True

        except Exception:
            return False


class KnowledgeSearch:
    """
    Advanced search capabilities
    """

    def __init__(self, knowledge_store: KnowledgeStore):
        """
        Initialize knowledge search

        Args:
            knowledge_store: KnowledgeStore instance
        """
        self.store = knowledge_store

    def search_by_date_range(
        self,
        query: str,
        start_date: datetime,
        end_date: datetime,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search within date range

        Args:
            query: Search query
            start_date: Start date
            end_date: End date
            top_k: Number of results

        Returns:
            Filtered search results
        """
        # Get more results than needed
        results = self.store.search(query, top_k=top_k * 3)

        # Filter by date
        filtered = []

        for result in results:
            timestamp_str = result.get("metadata", {}).get("timestamp")
            if not timestamp_str:
                continue

            try:
                entry_date = datetime.fromisoformat(timestamp_str)
                if start_date <= entry_date <= end_date:
                    filtered.append(result)
            except Exception:
                continue

        return filtered[:top_k]

    def search_with_score_threshold(
        self,
        query: str,
        min_score: float = 0.7,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search with minimum score threshold

        Args:
            query: Search query
            min_score: Minimum similarity score
            top_k: Maximum results

        Returns:
            Filtered results above threshold
        """
        results = self.store.search(
            query=query,
            top_k=top_k,
            score_threshold=min_score
        )

        return results
