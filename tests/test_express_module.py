"""
Tests for Express Module (@module decorator)

Verifies the simplified @module decorator works correctly and
auto-infers metadata from class definitions.
"""
import os
import pytest
import sys
from pathlib import Path

# Set validation mode to dev to avoid blocking during tests
os.environ["FLYTO_VALIDATION_MODE"] = "dev"

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.modules.express import (
    module,
    mod,
    _class_name_to_label,
    _extract_docstring,
    ParamHelper,
    create_simple_module,
)
from core.modules.base import BaseModule
from core.modules.registry import ModuleRegistry


class TestClassNameToLabel:
    """Test the class name to label conversion."""

    def test_simple_module_suffix(self):
        """AbsModule -> Abs"""
        assert _class_name_to_label("AbsModule") == "Abs"

    def test_multi_word(self):
        """BrowserLaunchModule -> Browser Launch"""
        assert _class_name_to_label("BrowserLaunchModule") == "Browser Launch"

    def test_acronym_handling(self):
        """HTTPRequestModule -> HTTP Request"""
        assert _class_name_to_label("HTTPRequestModule") == "HTTP Request"

    def test_json_prefix(self):
        """JSONParseModule -> JSON Parse"""
        assert _class_name_to_label("JSONParseModule") == "JSON Parse"

    def test_handler_suffix(self):
        """ClickHandler -> Click"""
        assert _class_name_to_label("ClickHandler") == "Click"

    def test_no_suffix(self):
        """Calculator -> Calculator"""
        assert _class_name_to_label("Calculator") == "Calculator"

    def test_action_suffix(self):
        """SendEmailAction -> Send Email"""
        assert _class_name_to_label("SendEmailAction") == "Send Email"


class TestExtractDocstring:
    """Test docstring extraction."""

    def test_single_line_docstring(self):
        """Extract single line docstring."""
        class TestClass:
            """This is a test class."""
            pass

        assert _extract_docstring(TestClass) == "This is a test class."

    def test_multiline_docstring(self):
        """Extract first line of multiline docstring."""
        class TestClass:
            """First line description.

            This is more detail.
            And even more.
            """
            pass

        assert _extract_docstring(TestClass) == "First line description."

    def test_no_docstring(self):
        """Return empty string if no docstring."""
        class TestClass:
            pass

        assert _extract_docstring(TestClass) == ""


class TestModuleDecorator:
    """Test the @module decorator."""

    def test_minimal_usage(self):
        """Minimal usage with just module_id."""
        @module('test.express_minimal')
        class MinimalModule(BaseModule):
            """A minimal test module."""

            def validate_params(self) -> None:
                pass

            async def execute(self):
                return self.success(result="ok")

        # Verify registration
        metadata = ModuleRegistry.get_metadata('test.express_minimal')
        assert metadata is not None
        assert metadata['module_id'] == 'test.express_minimal'
        assert metadata['category'] == 'test'  # Inferred from module_id
        assert metadata['ui_label'] == 'Minimal'  # Inferred from class name
        assert metadata['ui_description'] == 'A minimal test module.'

    def test_auto_infer_category(self):
        """Category is inferred from module_id prefix."""
        @module('math.express_abs')
        class AbsModule(BaseModule):
            """Get absolute value."""

            def validate_params(self) -> None:
                pass

            async def execute(self):
                return self.success(result=42)

        metadata = ModuleRegistry.get_metadata('math.express_abs')
        assert metadata['category'] == 'math'

    def test_override_inferred_values(self):
        """Can override auto-inferred values."""
        @module(
            'test.express_override',
            ui_label='Custom Label',
            ui_description='Custom description',
            category='custom_cat',
        )
        class OverrideModule(BaseModule):
            """This docstring will be ignored."""

            def validate_params(self) -> None:
                pass

            async def execute(self):
                return self.success(result="ok")

        metadata = ModuleRegistry.get_metadata('test.express_override')
        assert metadata['ui_label'] == 'Custom Label'
        assert metadata['ui_description'] == 'Custom description'
        assert metadata['category'] == 'custom_cat'

    def test_connection_rules_default_to_wildcard(self):
        """Connection rules default to ['*']."""
        @module('test.express_connections')
        class ConnectionModule(BaseModule):
            """Test connection defaults."""

            def validate_params(self) -> None:
                pass

            async def execute(self):
                return self.success(result="ok")

        metadata = ModuleRegistry.get_metadata('test.express_connections')
        assert metadata['can_receive_from'] == ['*']
        assert metadata['can_connect_to'] == ['*']

    def test_mod_alias(self):
        """mod is an alias for module."""
        @mod('test.express_mod_alias')
        class AliasModule(BaseModule):
            """Test mod alias."""

            def validate_params(self) -> None:
                pass

            async def execute(self):
                return self.success(result="ok")

        assert ModuleRegistry.get('test.express_mod_alias') is not None


class TestParamHelper:
    """Test the ParamHelper mixin."""

    def test_require_present(self):
        """require() returns value when present."""
        class TestModule(ParamHelper):
            params = {'name': 'test'}

        mod = TestModule()
        assert mod.require('name', expected_type=str) == 'test'

    def test_require_missing(self):
        """require() raises ValidationError when missing."""
        from core.modules.errors import ValidationError

        class TestModule(ParamHelper):
            params = {}

        mod = TestModule()
        with pytest.raises(ValidationError, match="Missing required parameter: name"):
            mod.require('name', expected_type=str)

    def test_require_wrong_type(self):
        """require() raises InvalidTypeError for wrong type."""
        from core.modules.errors import InvalidTypeError

        class TestModule(ParamHelper):
            params = {'number': 'not a number'}

        mod = TestModule()
        with pytest.raises(InvalidTypeError):
            mod.require('number', expected_type=int)

    def test_optional_present(self):
        """optional() returns value when present."""
        class TestModule(ParamHelper):
            params = {'timeout': 30}

        mod = TestModule()
        assert mod.optional('timeout', default=10, expected_type=int) == 30

    def test_optional_missing(self):
        """optional() returns default when missing."""
        class TestModule(ParamHelper):
            params = {}

        mod = TestModule()
        assert mod.optional('timeout', default=10, expected_type=int) == 10


class TestCreateSimpleModule:
    """Test create_simple_module helper."""

    def test_create_from_function(self):
        """Create a module from a simple function."""
        async def my_execute(self):
            return self.success(result=42)

        MyModule = create_simple_module(
            'test.express_simple_fn',
            my_execute,
            description='Returns 42',
        )

        # Verify it's registered
        assert ModuleRegistry.get('test.express_simple_fn') is not None

        metadata = ModuleRegistry.get_metadata('test.express_simple_fn')
        assert metadata['ui_description'] == 'Returns 42'


class TestExpressModuleExecution:
    """Test that express modules actually execute correctly."""

    @pytest.mark.asyncio
    async def test_execute_express_module(self):
        """Express module can be instantiated and executed."""
        @module('test.express_exec')
        class ExecModule(BaseModule):
            """Execute test."""

            def validate_params(self) -> None:
                self.value = self.params.get('value', 100)

            async def execute(self):
                return self.success(data=self.value * 2)

        # Instantiate and execute (BaseModule requires both params and context)
        mod_cls = ModuleRegistry.get('test.express_exec')
        instance = mod_cls(params={'value': 21}, context={})
        # Note: validate_params() is called automatically in __init__
        result = await instance.execute()

        assert result['ok'] is True
        assert result['data'] == 42


class TestBackwardCompatibility:
    """Verify express mode doesn't break existing patterns."""

    def test_register_module_still_works(self):
        """@register_module still works alongside @module."""
        from core.modules.registry import register_module

        @register_module(
            module_id='test.express_compat_old',
            version='1.0.0',
            category='test',
            ui_label='Old Style',
            ui_description='Using register_module',
            can_receive_from=['*'],
            can_connect_to=['*'],
        )
        class OldStyleModule(BaseModule):
            """Old style registration."""

            def validate_params(self) -> None:
                pass

            async def execute(self):
                return self.success(result="old")

        assert ModuleRegistry.get('test.express_compat_old') is not None

    def test_both_styles_coexist(self):
        """Both registration styles can coexist."""
        # Express style
        @module('test.express_coexist_new')
        class NewStyle(BaseModule):
            """New express style."""

            def validate_params(self) -> None:
                pass

            async def execute(self):
                return self.success(result="new")

        # Both should be registered
        assert ModuleRegistry.get('test.express_coexist_new') is not None


class TestImportPaths:
    """Test that @module can be imported from expected locations."""

    def test_import_from_express(self):
        """Import from core.modules.express."""
        from core.modules.express import module, mod
        assert callable(module)
        assert callable(mod)

    def test_import_from_registry(self):
        """Import from core.modules.registry."""
        from core.modules.registry import module, mod
        assert callable(module)
        assert callable(mod)

    def test_import_from_modules(self):
        """Import from core.modules."""
        from core.modules import module, mod
        assert callable(module)
        assert callable(mod)
