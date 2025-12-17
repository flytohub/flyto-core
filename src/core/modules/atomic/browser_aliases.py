"""
Browser Module Aliases
Provides browser.* aliases for core.browser.* modules
"""
from core.modules.registry import register_module, ModuleRegistry


# Get existing core.browser modules
def create_browser_aliases():
    """Create browser.* aliases for all core.browser.* modules"""

    all_modules = ModuleRegistry.list_all()

    # Find all core.browser modules
    browser_modules = [m for m in all_modules if m.startswith('core.browser.')]

    for module_id in browser_modules:
        # Create alias without 'core.' prefix
        alias_id = module_id.replace('core.', '')

        # Get the module class
        try:
            module_class = ModuleRegistry.get(module_id)
            if module_class:
                # Register alias
                register_module(alias_id)(module_class)
        except:
            pass


# Create aliases on import
create_browser_aliases()
