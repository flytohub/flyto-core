"""
Connection Index

Pre-computed index for fast connection lookups.
Built once at startup, O(1) queries afterward.
"""

from typing import Dict, List, Optional
import threading


class ConnectionIndex:
    """
    Pre-computed connection index for fast lookups.

    Built from ModuleRegistry at first access.
    Singleton pattern - one instance per process.
    """

    _instance: Optional['ConnectionIndex'] = None
    _lock = threading.Lock()

    def __init__(self):
        # module_id -> [connectable module_ids]
        self.connectable_next: Dict[str, List[str]] = {}
        self.connectable_prev: Dict[str, List[str]] = {}

        # module_id -> {category: count}
        self._summary_cache: Dict[str, Dict[str, Dict[str, int]]] = {}

        # Startable modules list
        self.startable_modules: List[str] = []

        # Build status
        self._built = False

    @classmethod
    def get_instance(cls) -> 'ConnectionIndex':
        """Get or create singleton instance"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    cls._instance._build()
        return cls._instance

    @classmethod
    def rebuild(cls) -> 'ConnectionIndex':
        """Force rebuild of index (e.g., after module registration)"""
        with cls._lock:
            cls._instance = cls()
            cls._instance._build()
        return cls._instance

    def _build(self):
        """
        Build index from ModuleRegistry.
        Complexity: O(n^2) but only runs once.
        """
        if self._built:
            return

        from ..modules.registry import ModuleRegistry

        all_metadata = ModuleRegistry.get_all_metadata()

        for module_id, meta in all_metadata.items():
            can_connect_to = meta.get('can_connect_to', ['*'])
            can_receive_from = meta.get('can_receive_from', ['*'])
            output_types = meta.get('output_types', [])
            input_types = meta.get('input_types', [])

            # Build connectable_next
            next_list = []
            for other_id, other_meta in all_metadata.items():
                if other_id == module_id:
                    continue
                if self._can_connect(
                    can_connect_to, output_types,
                    other_meta.get('can_receive_from', ['*']),
                    other_meta.get('input_types', [])
                ):
                    next_list.append(other_id)
            self.connectable_next[module_id] = next_list

            # Build connectable_prev
            prev_list = []
            for other_id, other_meta in all_metadata.items():
                if other_id == module_id:
                    continue
                if self._can_connect(
                    other_meta.get('can_connect_to', ['*']),
                    other_meta.get('output_types', []),
                    can_receive_from, input_types
                ):
                    prev_list.append(other_id)
            self.connectable_prev[module_id] = prev_list

            # Build startable modules
            if meta.get('can_be_start', False):
                self.startable_modules.append(module_id)

        self._built = True

    def _can_connect(
        self,
        from_can_connect: List[str],
        from_output_types: List[str],
        to_can_receive: List[str],
        to_input_types: List[str],
    ) -> bool:
        """Check if connection is allowed based on rules and types"""
        # Check wildcard rules
        from_allows = '*' in from_can_connect
        to_allows = '*' in to_can_receive

        if not from_allows and not to_allows:
            # Both have restrictions - need to check patterns
            # For now, allow if not explicitly blocked
            pass

        # Check type compatibility
        if from_output_types and to_input_types:
            if '*' not in to_input_types and '*' not in from_output_types:
                # Check if any output type matches any input type
                if not any(t in to_input_types for t in from_output_types):
                    if 'any' not in to_input_types:
                        return False

        return True

    def get_summary(self, module_id: str, direction: str) -> Dict[str, int]:
        """Get category counts for connectable modules"""
        cache_key = f"{module_id}:{direction}"
        if cache_key in self._summary_cache:
            return self._summary_cache[cache_key]

        if direction == 'next':
            modules = self.connectable_next.get(module_id, [])
        else:
            modules = self.connectable_prev.get(module_id, [])

        summary: Dict[str, int] = {}
        for mid in modules:
            category = mid.split('.')[0]
            summary[category] = summary.get(category, 0) + 1

        self._summary_cache[cache_key] = summary
        return summary
