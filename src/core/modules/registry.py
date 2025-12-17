"""
Module Registry - Manage all available modules

Enhanced Features:
- Multi-language support (i18n)
- Version management
- Tags and categories
- Rich metadata for module marketplace
- Filtering and querying capabilities
- Module level classification (ATOMIC/THIRD_PARTY/AI_TOOL/EXTERNAL)
"""
import logging
from typing import Dict, Type, Any, Optional, List

from .base import BaseModule
from .types import (
    ModuleLevel,
    UIVisibility,
    ContextType,
    ExecutionEnvironment,
    LEVEL_PRIORITY,
    DEFAULT_CONTEXT_REQUIREMENTS,
    DEFAULT_CONTEXT_PROVISIONS,
    get_default_visibility,
    get_module_environment,
)
from ..constants import ErrorMessages


logger = logging.getLogger(__name__)


def _get_localized_value(value: Any, lang: str = 'en') -> str:
    """
    Extract localized string from value

    Supports:
    1. String: returns as-is
    2. Dict: {"en": "...", "zh": "...", "ja": "..."}

    Args:
        value: Value to process (string or dict)
        lang: Language code (en, zh, ja, es)

    Returns:
        Localized string, falls back to English if specified lang not found
    """
    if isinstance(value, str):
        return value
    elif isinstance(value, dict):
        # Try to get specified language
        if lang in value:
            return value[lang]
        # Fallback to English
        if 'en' in value:
            return value['en']
        # If no English, return first available
        return next(iter(value.values())) if value else ''
    return str(value) if value else ''


class ModuleRegistry:
    """
    Module Registry - Singleton Pattern

    Manages all registered modules and their metadata.
    Provides querying, filtering, and execution capabilities.
    """

    _instance = None
    _modules: Dict[str, Type[BaseModule]] = {}
    _metadata: Dict[str, Dict[str, Any]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, module_id: str, module_class: Type[BaseModule], metadata: Optional[Dict[str, Any]] = None):
        """
        Register a module

        Args:
            module_id: Unique module identifier (e.g., "browser.goto")
            module_class: Module class inheriting from BaseModule
            metadata: Module metadata (optional)
        """
        cls._modules[module_id] = module_class
        if metadata:
            # Ensure required fields
            metadata.setdefault('module_id', module_id)
            metadata.setdefault('version', '1.0.0')
            metadata.setdefault('category', module_id.split('.')[0])
            metadata.setdefault('tags', [])
            cls._metadata[module_id] = metadata
        logger.debug(f"Module registered: {module_id}")

    @classmethod
    def unregister(cls, module_id: str):
        """Remove a module from registry"""
        if module_id in cls._modules:
            del cls._modules[module_id]
            if module_id in cls._metadata:
                del cls._metadata[module_id]
            logger.debug(f"Module unregistered: {module_id}")

    @classmethod
    def get(cls, module_id: str) -> Type[BaseModule]:
        """
        Get module class by ID

        Args:
            module_id: Module identifier

        Returns:
            Module class

        Raises:
            ValueError: If module not found
        """
        if module_id not in cls._modules:
            raise ValueError(
                ErrorMessages.format(
                    ErrorMessages.MODULE_NOT_FOUND,
                    module_id=module_id
                )
            )
        return cls._modules[module_id]

    @classmethod
    def has(cls, module_id: str) -> bool:
        """Check if module exists"""
        return module_id in cls._modules

    @classmethod
    def list_all(cls) -> Dict[str, Type[BaseModule]]:
        """List all registered module classes"""
        return cls._modules.copy()

    @classmethod
    def get_all_metadata(
        cls,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        lang: str = 'en'
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get all module metadata (with optional filtering)

        Args:
            category: Filter by category (e.g., "browser", "data")
            tags: Filter by tags (module must have at least one matching tag)
            lang: Language code for localized fields

        Returns:
            Dict of module_id -> metadata
        """
        result = {}

        for module_id, metadata in cls._metadata.items():
            # Filter by category
            if category and metadata.get('category') != category:
                continue

            # Filter by tags
            if tags:
                module_tags = metadata.get('tags', [])
                if not any(tag in module_tags for tag in tags):
                    continue

            # Localize fields
            localized_metadata = cls._localize_metadata(metadata, lang)
            result[module_id] = localized_metadata

        return result

    @classmethod
    def get_metadata(cls, module_id: str, lang: str = 'en') -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific module

        Args:
            module_id: Module identifier
            lang: Language code

        Returns:
            Localized metadata or None if not found
        """
        metadata = cls._metadata.get(module_id)
        if not metadata:
            return None
        return cls._localize_metadata(metadata, lang)

    @classmethod
    def _localize_metadata(cls, metadata: Dict[str, Any], lang: str) -> Dict[str, Any]:
        """
        Localize metadata fields based on language

        Fields that support i18n: label, description, and nested labels in params_schema
        """
        result = metadata.copy()

        # Localize top-level fields
        if 'label' in result:
            result['label'] = _get_localized_value(result['label'], lang)
        if 'description' in result:
            result['description'] = _get_localized_value(result['description'], lang)

        # Localize params_schema labels
        if 'params_schema' in result:
            params = result['params_schema'].copy()
            for param_name, param_def in params.items():
                if isinstance(param_def, dict):
                    param_copy = param_def.copy()
                    if 'label' in param_copy:
                        param_copy['label'] = _get_localized_value(param_copy['label'], lang)
                    if 'description' in param_copy:
                        param_copy['description'] = _get_localized_value(param_copy['description'], lang)
                    if 'placeholder' in param_copy:
                        param_copy['placeholder'] = _get_localized_value(param_copy['placeholder'], lang)

                    # Localize select options
                    if 'options' in param_copy and isinstance(param_copy['options'], list):
                        localized_options = []
                        for opt in param_copy['options']:
                            if isinstance(opt, dict) and 'label' in opt:
                                opt_copy = opt.copy()
                                opt_copy['label'] = _get_localized_value(opt['label'], lang)
                                localized_options.append(opt_copy)
                            else:
                                localized_options.append(opt)
                        param_copy['options'] = localized_options

                    params[param_name] = param_copy
            result['params_schema'] = params

        return result

    @classmethod
    async def execute(cls, module_id: str, params: Dict[str, Any], context: Dict[str, Any]) -> Any:
        """
        Execute a module

        Args:
            module_id: Module identifier
            params: Parameters to pass to module
            context: Execution context (shared state, browser instance, etc.)

        Returns:
            Module execution result
        """
        module_class = cls.get(module_id)
        module_instance = module_class(params, context)
        return await module_instance.execute()


def register_module(
    module_id: str,
    version: str = "1.0.0",
    level: ModuleLevel = ModuleLevel.ATOMIC,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    tags: Optional[List[str]] = None,

    # Context requirements (for connection validation)
    requires_context: Optional[List[str]] = None,
    provides_context: Optional[List[str]] = None,

    # UI visibility and metadata
    # None = auto-detect based on category (see types.DEFAULT_VISIBILITY_CATEGORIES)
    ui_visibility: Optional[UIVisibility] = None,
    ui_label: Optional[Any] = None,
    ui_label_key: Optional[str] = None,
    ui_description: Optional[Any] = None,
    ui_description_key: Optional[str] = None,
    ui_group: Optional[str] = None,
    ui_icon: Optional[str] = None,
    ui_color: Optional[str] = None,

    # Legacy label fields (deprecated, use ui_label instead)
    label: Optional[Any] = None,
    label_key: Optional[str] = None,
    description: Optional[Any] = None,
    description_key: Optional[str] = None,

    # Legacy visual fields (deprecated, use ui_icon instead)
    icon: Optional[str] = None,
    color: Optional[str] = None,

    # Connection types (for UI compatibility)
    input_types: Optional[List[str]] = None,
    output_types: Optional[List[str]] = None,
    can_receive_from: Optional[List[str]] = None,
    can_connect_to: Optional[List[str]] = None,

    # Schema
    params_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,

    # Execution settings
    timeout: Optional[int] = None,
    retryable: bool = False,
    max_retries: int = 3,
    concurrent_safe: bool = True,

    # Security settings
    requires_credentials: bool = False,
    handles_sensitive_data: bool = False,
    required_permissions: Optional[List[str]] = None,

    # Execution environment (LOCAL/CLOUD/ALL)
    # None = auto-detect based on category (see types.LOCAL_ONLY_CATEGORIES)
    execution_environment: Optional[ExecutionEnvironment] = None,

    # Advanced
    requires: Optional[List[str]] = None,
    permissions: Optional[List[str]] = None,
    examples: Optional[List[Dict[str, Any]]] = None,
    docs_url: Optional[str] = None,
    author: Optional[str] = None,
    license: str = "MIT"
):
    """
    Module registration decorator

    UI Visibility Auto-Detection:
        When ui_visibility is not specified (None), it will be automatically
        determined based on the module's category:
        - DEFAULT (shown to all users): ai, agent, notification, api, browser, cloud, database, productivity, payment, image
        - EXPERT (advanced users only): string, array, object, math, datetime, file, element, flow, data, utility, meta, test

        See types.DEFAULT_VISIBILITY_CATEGORIES for the full mapping.

    Example:
        @register_module(
            module_id="browser.goto",
            level=ModuleLevel.ATOMIC,
            category="browser",

            # Context for connection validation
            requires_context=["browser"],
            provides_context=["browser", "page"],

            # UI metadata (ui_visibility auto-detected from category "browser" -> DEFAULT)
            ui_label="Open URL",
            ui_description="Navigate browser to a URL",
            ui_group="Browser / Navigation",
            ui_icon="Globe",
            ui_color="#8B5CF6",

            params_schema={
                "url": {
                    "type": "string",
                    "required": True,
                    "label": "URL"
                }
            }
        )
        class BrowserGotoModule(BaseModule):
            async def execute(self):
                pass

    Args:
        module_id: Unique identifier (e.g., "browser.goto")
        version: Semantic version (default: "1.0.0")
        level: Module level classification
        category: Primary category (default: extracted from module_id)
        subcategory: Optional subcategory
        tags: List of tags for filtering

        requires_context: List of context types this module requires (e.g., ["browser"])
        provides_context: List of context types this module provides (e.g., ["browser", "page"])

        ui_visibility: UI visibility level (DEFAULT/EXPERT/HIDDEN), or None for auto-detection
        ui_label: Display name for UI
        ui_label_key: i18n translation key for label
        ui_description: Description for UI
        ui_description_key: i18n translation key for description
        ui_group: UI grouping category
        ui_icon: Lucide icon name
        ui_color: Hex color code

        params_schema: Parameter definitions
        output_schema: Output structure definition

        timeout: Execution timeout in seconds
        retryable: Whether module can be retried on failure
        max_retries: Maximum retry attempts
        concurrent_safe: Whether module can run concurrently

        requires_credentials: Whether module needs API keys
        handles_sensitive_data: Whether module processes sensitive data
        required_permissions: List of required permissions

        execution_environment: Where module can run (LOCAL/CLOUD/ALL), or None for auto-detection

        examples: Usage examples
        docs_url: Documentation URL
        author: Module author
        license: License identifier
    """
    def decorator(module_class_or_func):
        # Check if it's a function or a class
        import inspect
        is_function = inspect.isfunction(module_class_or_func) or inspect.iscoroutinefunction(module_class_or_func)

        if is_function:
            # Wrap function in a class
            class FunctionModuleWrapper(BaseModule):
                """Wrapper to make function-based modules work with class-based engine"""

                def __init__(self, params: Dict[str, Any], context: Dict[str, Any]):
                    self.params = params
                    self.context = context

                def validate_params(self):
                    """Validation handled by function"""
                    pass

                async def execute(self) -> Any:
                    """Execute the wrapped function"""
                    # Build context dict for function
                    func_context = {
                        'params': self.params,
                        **self.context
                    }
                    return await module_class_or_func(func_context)

            FunctionModuleWrapper.module_id = module_id
            FunctionModuleWrapper.__name__ = f"{module_class_or_func.__name__}_Wrapper"
            FunctionModuleWrapper.__doc__ = module_class_or_func.__doc__
            module_class = FunctionModuleWrapper
        else:
            # It's already a class
            module_class = module_class_or_func
            module_class.module_id = module_id

        # Determine category from module_id if not provided
        resolved_category = category or module_id.split('.')[0]

        # Auto-resolve UI visibility from category if not explicitly provided
        resolved_visibility = ui_visibility
        if resolved_visibility is None:
            resolved_visibility = get_default_visibility(resolved_category)

        # Auto-resolve context from category defaults if not explicitly provided
        resolved_requires_context = requires_context
        resolved_provides_context = provides_context

        if resolved_requires_context is None:
            resolved_requires_context = DEFAULT_CONTEXT_REQUIREMENTS.get(resolved_category, [])

        if resolved_provides_context is None:
            resolved_provides_context = DEFAULT_CONTEXT_PROVISIONS.get(resolved_category, [])

        # Auto-resolve execution environment from category if not explicitly provided
        resolved_execution_env = execution_environment
        if resolved_execution_env is None:
            resolved_execution_env = get_module_environment(module_id, resolved_category)

        # Build metadata
        metadata = {
            "module_id": module_id,
            "version": version,
            "level": level.value if isinstance(level, ModuleLevel) else level,
            "category": resolved_category,
            "subcategory": subcategory,
            "tags": tags or [],

            # Context for connection validation
            "requires_context": resolved_requires_context,
            "provides_context": resolved_provides_context,

            # UI metadata (prefer new ui_* fields, fallback to legacy)
            "ui_visibility": resolved_visibility.value if isinstance(resolved_visibility, UIVisibility) else resolved_visibility,
            "ui_label": ui_label or label or module_id,
            "ui_label_key": ui_label_key or label_key,
            "ui_description": ui_description or description or "",
            "ui_description_key": ui_description_key or description_key,
            "ui_group": ui_group,
            "ui_icon": ui_icon or icon,
            "ui_color": ui_color or color,

            # Legacy fields (for backward compatibility)
            "label": ui_label or label or module_id,
            "description": ui_description or description or "",
            "icon": ui_icon or icon,
            "color": ui_color or color,

            # Connection types
            "input_types": input_types or [],
            "output_types": output_types or [],
            "can_receive_from": can_receive_from or [],
            "can_connect_to": can_connect_to or [],

            # Schema
            "params_schema": params_schema or {},
            "output_schema": output_schema or {},

            # Execution settings
            "timeout": timeout,
            "retryable": retryable,
            "max_retries": max_retries,
            "concurrent_safe": concurrent_safe,

            # Security settings
            "requires_credentials": requires_credentials,
            "handles_sensitive_data": handles_sensitive_data,
            "required_permissions": required_permissions or [],

            # Execution environment
            "execution_environment": resolved_execution_env.value if isinstance(resolved_execution_env, ExecutionEnvironment) else resolved_execution_env,

            # Advanced
            "requires": requires or [],
            "permissions": permissions or [],
            "examples": examples or [],
            "docs_url": docs_url,
            "author": author,
            "license": license
        }

        ModuleRegistry.register(module_id, module_class, metadata)
        return module_class

    return decorator


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

        print(f"Catalog exported to: {file_path}")
        print(f"Total modules: {catalog['total_modules']}")

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

            print(f"Synced {ingested_count} modules to VectorDB")
            return {"success": True, "count": ingested_count}

        except Exception as e:
            print(f"Failed to sync to VectorDB: {e}")
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
        from datetime import datetime
        return datetime.now().isoformat()


# Global catalog manager instance
_catalog_manager = None

def get_catalog_manager() -> ModuleCatalogManager:
    """Get singleton catalog manager instance"""
    global _catalog_manager
    if _catalog_manager is None:
        _catalog_manager = ModuleCatalogManager()
    return _catalog_manager


if __name__ == "__main__":
    """
    Command-line interface for module catalog management

    Usage:
        python -m src.core.modules.registry export [--output PATH] [--lang LANG]
        python -m src.core.modules.registry stats
        python -m src.core.modules.registry sync
    """
    import sys
    import asyncio

    if len(sys.argv) < 2:
        print("Usage: python -m src.core.modules.registry <command>")
        print("Commands:")
        print("  export [--output PATH] [--lang LANG]  Export catalog to JSON")
        print("  stats                                  Show catalog statistics")
        print("  sync                                   Sync to VectorDB")
        sys.exit(1)

    command = sys.argv[1]
    manager = get_catalog_manager()

    if command == "export":
        output = "modules/catalog.json"
        lang = "en"

        # Parse optional arguments
        for i, arg in enumerate(sys.argv[2:], start=2):
            if arg == "--output" and i + 1 < len(sys.argv):
                output = sys.argv[i + 1]
            elif arg == "--lang" and i + 1 < len(sys.argv):
                lang = sys.argv[i + 1]

        manager.export_to_json_file(output, lang=lang)

    elif command == "stats":
        stats = manager.get_statistics()
        print("\nModule Catalog Statistics:")
        print(f"  Total modules: {stats['total_modules']}")
        print(f"  Total categories: {stats['total_categories']}")
        print(f"  Total unique tags: {stats['total_unique_tags']}")
        print("\nModules by category:")
        for cat, count in sorted(stats['categories'].items()):
            print(f"  - {cat}: {count}")

    elif command == "sync":
        print("Syncing catalog to VectorDB...")
        result = asyncio.run(manager.sync_to_vectordb())
        if result['success']:
            print(f"✅ Successfully synced {result['count']} modules")
        else:
            print(f"❌ Sync failed: {result['error']}")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
