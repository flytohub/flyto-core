"""
Module Catalog Manager - Export, Search, and Sync

Manages module catalog with export, search, and VectorDB sync capabilities.
"""
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

from .core import ModuleRegistry


logger = logging.getLogger(__name__)


class ModuleCatalogManager:
    """
    Module Catalog Manager - Phase 1 Core Infrastructure

    Manages module catalog with export, search, and sync capabilities.
    """

    def __init__(self):
        self.registry = ModuleRegistry()

    def export_catalog(self, lang: str = 'en') -> Dict[str, Any]:
        """
        Export complete module catalog

        Args:
            lang: Language for localized fields

        Returns:
            Complete catalog with all modules
        """
        all_metadata = self.registry.get_all_metadata(lang=lang)

        catalog = {
            "version": "1.0.0",
            "generated_at": self._get_timestamp(),
            "total_modules": len(all_metadata),
            "modules": all_metadata,
            "categories": self._get_categories(all_metadata),
            "tags": self._get_all_tags(all_metadata)
        }

        return catalog

    def export_to_json_file(self, filepath: str, lang: str = 'en'):
        """Export catalog to JSON file"""
        import json
        from pathlib import Path

        catalog = self.export_catalog(lang)

        file_path = Path(filepath)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)

        logger.info(f"Catalog exported to: {file_path}")
        logger.info(f"Total modules: {catalog['total_modules']}")

    def search_modules(
        self,
        query: str,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        lang: str = 'en'
    ) -> List[Dict[str, Any]]:
        """
        Search modules by query string

        Args:
            query: Search query
            category: Filter by category
            tags: Filter by tags
            lang: Language for results

        Returns:
            List of matching modules
        """
        all_modules = self.registry.get_all_metadata(category=category, tags=tags, lang=lang)

        query_lower = query.lower()
        results = []

        for module_id, metadata in all_modules.items():
            # Search in module_id, label, description
            searchable_text = " ".join([
                module_id,
                str(metadata.get('label', '')),
                str(metadata.get('description', ''))
            ]).lower()

            if query_lower in searchable_text:
                results.append({
                    "module_id": module_id,
                    **metadata
                })

        return results

    def get_module_by_category(self, category: str, lang: str = 'en') -> List[Dict[str, Any]]:
        """Get all modules in a category"""
        modules = self.registry.get_all_metadata(category=category, lang=lang)
        return [{"module_id": mid, **meta} for mid, meta in modules.items()]

    def get_statistics(self) -> Dict[str, Any]:
        """Get catalog statistics"""
        all_modules = self.registry.get_all_metadata()

        categories = {}
        tags_count = {}

        for module_id, metadata in all_modules.items():
            cat = metadata.get('category', 'unknown')
            categories[cat] = categories.get(cat, 0) + 1

            for tag in metadata.get('tags', []):
                tags_count[tag] = tags_count.get(tag, 0) + 1

        return {
            "total_modules": len(all_modules),
            "categories": categories,
            "most_common_tags": sorted(tags_count.items(), key=lambda x: x[1], reverse=True)[:10],
            "total_categories": len(categories),
            "total_unique_tags": len(tags_count)
        }

    async def sync_to_vectordb(self, lang: str = 'en'):
        """
        Sync module catalog to VectorDB for RAG

        Uses knowledge store to make modules searchable via RAG.
        """
        try:
            from core.knowledge.knowledge_store import KnowledgeStore

            store = KnowledgeStore()
            all_modules = self.registry.get_all_metadata(lang=lang)

            ingested_count = 0
            for module_id, metadata in all_modules.items():
                # Create searchable content
                content = self._format_module_for_rag(module_id, metadata)

                # Ingest to vector store
                await store.ingest_text(
                    content=content,
                    metadata={
                        "type": "module",
                        "module_id": module_id,
                        "category": metadata.get('category', 'unknown'),
                        "source": "catalog"
                    }
                )
                ingested_count += 1

            logger.info(f"Synced {ingested_count} modules to VectorDB")
            return {"success": True, "count": ingested_count}

        except Exception as e:
            logger.error(f"Failed to sync to VectorDB: {e}")
            return {"success": False, "error": str(e)}

    def _format_module_for_rag(self, module_id: str, metadata: Dict[str, Any]) -> str:
        """Format module information for RAG ingestion"""
        lines = [
            f"Module: {module_id}",
            f"Label: {metadata.get('label', '')}",
            f"Category: {metadata.get('category', '')}",
            f"Description: {metadata.get('description', '')}",
            ""
        ]

        if metadata.get('tags'):
            lines.append(f"Tags: {', '.join(metadata['tags'])}")

        if metadata.get('params_schema'):
            lines.append("\nParameters:")
            for param_name, param_def in metadata['params_schema'].items():
                if isinstance(param_def, dict):
                    lines.append(f"  - {param_name}: {param_def.get('description', '')}")

        if metadata.get('examples'):
            lines.append("\nExamples:")
            for example in metadata['examples'][:2]:  # First 2 examples
                if isinstance(example, dict):
                    lines.append(f"  {example.get('description', '')}")

        return "\n".join(lines)

    def _get_categories(self, modules: Dict[str, Dict[str, Any]]) -> List[str]:
        """Extract unique categories"""
        return list(set(m.get('category', 'unknown') for m in modules.values()))

    def _get_all_tags(self, modules: Dict[str, Dict[str, Any]]) -> List[str]:
        """Extract all unique tags"""
        tags = set()
        for metadata in modules.values():
            tags.update(metadata.get('tags', []))
        return sorted(list(tags))

    def _get_timestamp(self) -> str:
        """Get current ISO timestamp"""
        return datetime.now().isoformat()

    # ========================================
    # Tier-based Catalog (Frontend API)
    # ========================================

    def get_tiered_catalog(
        self,
        lang: str = 'en',
        filter_by_stability: bool = True,
        env: Optional[str] = None,
        include_internal: bool = False,
    ) -> Dict[str, Any]:
        """
        Get module catalog grouped by tier for frontend display.

        Returns structured catalog for node picker dialogs:
        - Modules grouped by tier (featured, standard, toolkit)
        - Within each tier, grouped by category
        - Sorted by tier display order

        Args:
            lang: Language code for localization
            filter_by_stability: Filter modules by stability level
            env: Environment override
            include_internal: Include INTERNAL tier modules

        Returns:
            Tiered catalog structure
        """
        return self.registry.get_catalog(
            lang=lang,
            filter_by_stability=filter_by_stability,
            env=env,
            include_internal=include_internal,
        )

    def get_start_module_catalog(
        self,
        lang: str = 'en',
        filter_by_stability: bool = True,
        env: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get modules that can be used as workflow start nodes.

        For "Select Start Module" dialog.

        Args:
            lang: Language code
            filter_by_stability: Filter by stability level
            env: Environment override

        Returns:
            Tiered catalog of start-capable modules
        """
        return self.registry.get_start_modules(
            lang=lang,
            filter_by_stability=filter_by_stability,
            env=env,
        )

    def get_tier_statistics(self) -> Dict[str, Any]:
        """Get statistics by tier"""
        all_modules = self.registry.get_all_metadata()

        tier_counts = {}
        tier_categories = {}

        for module_id, metadata in all_modules.items():
            tier = metadata.get('tier', 'standard')
            category = metadata.get('category', 'unknown')

            tier_counts[tier] = tier_counts.get(tier, 0) + 1

            if tier not in tier_categories:
                tier_categories[tier] = set()
            tier_categories[tier].add(category)

        return {
            "tier_counts": tier_counts,
            "tier_categories": {t: list(cats) for t, cats in tier_categories.items()},
            "total_modules": len(all_modules),
        }


# Global catalog manager instance
_catalog_manager = None


def get_catalog_manager() -> ModuleCatalogManager:
    """Get singleton catalog manager instance"""
    global _catalog_manager
    if _catalog_manager is None:
        _catalog_manager = ModuleCatalogManager()
    return _catalog_manager
