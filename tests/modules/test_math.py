"""
Tests for math.* modules

Tests all math manipulation modules:
- math.abs
- math.floor
- math.ceil
- math.round
- math.power
"""

import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from core.modules.errors import ValidationError


class TestMathAbs:
    """Tests for math.abs module."""

    MODULE_ID = "math.abs"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_negative_number(self, module_class):
        """Test absolute value of negative number."""
        instance = module_class({"number": -5}, {})
        result = await instance.execute()
        assert result["ok"] is True
        assert result["data"]["result"] == 5
        assert result["data"]["original"] == -5

    @pytest.mark.asyncio
    async def test_positive_number(self, module_class):
        """Test absolute value of positive number."""
        instance = module_class({"number": 3.14}, {})
        result = await instance.execute()
        assert result["ok"] is True
        assert result["data"]["result"] == 3.14

    @pytest.mark.asyncio
    async def test_zero(self, module_class):
        """Test absolute value of zero."""
        instance = module_class({"number": 0}, {})
        result = await instance.execute()
        assert result["ok"] is True
        assert result["data"]["result"] == 0

    @pytest.mark.asyncio
    async def test_missing_param(self, module_class):
        """Test missing number parameter raises ValidationError."""
        instance = module_class({}, {})
        with pytest.raises(ValidationError):
            await instance.execute()


class TestMathFloor:
    """Tests for math.floor module."""

    MODULE_ID = "math.floor"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_positive_number(self, module_class):
        """Test floor of positive number."""
        instance = module_class({"number": 3.7}, {})
        result = await instance.execute()
        assert result["ok"] is True
        assert result["data"]["result"] == 3
        assert result["data"]["original"] == 3.7

    @pytest.mark.asyncio
    async def test_negative_number(self, module_class):
        """Test floor of negative number."""
        instance = module_class({"number": -2.3}, {})
        result = await instance.execute()
        assert result["ok"] is True
        assert result["data"]["result"] == -3

    @pytest.mark.asyncio
    async def test_integer(self, module_class):
        """Test floor of integer."""
        instance = module_class({"number": 5}, {})
        result = await instance.execute()
        assert result["ok"] is True
        assert result["data"]["result"] == 5


class TestMathCeil:
    """Tests for math.ceil module."""

    MODULE_ID = "math.ceil"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_positive_number(self, module_class):
        """Test ceiling of positive number."""
        instance = module_class({"number": 3.2}, {})
        result = await instance.execute()
        assert result["ok"] is True
        assert result["data"]["result"] == 4
        assert result["data"]["original"] == 3.2

    @pytest.mark.asyncio
    async def test_negative_number(self, module_class):
        """Test ceiling of negative number."""
        instance = module_class({"number": -2.7}, {})
        result = await instance.execute()
        assert result["ok"] is True
        assert result["data"]["result"] == -2

    @pytest.mark.asyncio
    async def test_integer(self, module_class):
        """Test ceiling of integer."""
        instance = module_class({"number": 5}, {})
        result = await instance.execute()
        assert result["ok"] is True
        assert result["data"]["result"] == 5


class TestMathRound:
    """Tests for math.round module."""

    MODULE_ID = "math.round"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_round_to_integer(self, module_class):
        """Test rounding to integer."""
        instance = module_class({"number": 3.7}, {})
        result = await instance.execute()
        assert result["ok"] is True
        assert result["data"]["result"] == 4
        assert result["data"]["decimals"] == 0

    @pytest.mark.asyncio
    async def test_round_to_decimals(self, module_class):
        """Test rounding to 2 decimal places."""
        instance = module_class({"number": 3.14159, "decimals": 2}, {})
        result = await instance.execute()
        assert result["ok"] is True
        assert result["data"]["result"] == 3.14

    @pytest.mark.asyncio
    async def test_round_down(self, module_class):
        """Test rounding down."""
        instance = module_class({"number": 3.4}, {})
        result = await instance.execute()
        assert result["ok"] is True
        assert result["data"]["result"] == 3


class TestMathPower:
    """Tests for math.power module."""

    MODULE_ID = "math.power"

    @pytest.fixture
    def module_class(self):
        from core.modules.registry import ModuleRegistry
        from core.modules import atomic
        return ModuleRegistry.get(self.MODULE_ID)

    @pytest.mark.asyncio
    async def test_square(self, module_class):
        """Test squaring a number."""
        instance = module_class({"base": 5, "exponent": 2}, {})
        result = await instance.execute()
        assert result["ok"] is True
        assert result["data"]["result"] == 25
        assert result["data"]["base"] == 5
        assert result["data"]["exponent"] == 2

    @pytest.mark.asyncio
    async def test_cube(self, module_class):
        """Test cubing a number."""
        instance = module_class({"base": 3, "exponent": 3}, {})
        result = await instance.execute()
        assert result["ok"] is True
        assert result["data"]["result"] == 27

    @pytest.mark.asyncio
    async def test_square_root(self, module_class):
        """Test square root."""
        instance = module_class({"base": 16, "exponent": 0.5}, {})
        result = await instance.execute()
        assert result["ok"] is True
        assert result["data"]["result"] == 4.0

    @pytest.mark.asyncio
    async def test_missing_base(self, module_class):
        """Test missing base parameter raises ValidationError."""
        instance = module_class({"exponent": 2}, {})
        with pytest.raises(ValidationError):
            await instance.execute()

    @pytest.mark.asyncio
    async def test_missing_exponent(self, module_class):
        """Test missing exponent parameter raises ValidationError."""
        instance = module_class({"base": 5}, {})
        with pytest.raises(ValidationError):
            await instance.execute()
