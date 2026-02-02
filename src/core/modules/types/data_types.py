"""
Data Type Compatibility

Type compatibility matrix and validation functions.
"""

from typing import Dict, List

from .enums import DataType


# Types that are compatible with each other
# Key can connect to any value in its list
DATA_TYPE_COMPATIBILITY: Dict[DataType, List[DataType]] = {
    DataType.ANY: list(DataType),  # ANY accepts everything
    DataType.STRING: [DataType.ANY, DataType.STRING, DataType.JSON, DataType.XML, DataType.HTML],
    DataType.NUMBER: [DataType.ANY, DataType.NUMBER, DataType.STRING],
    DataType.BOOLEAN: [DataType.ANY, DataType.BOOLEAN, DataType.STRING, DataType.NUMBER],
    DataType.OBJECT: [DataType.ANY, DataType.OBJECT, DataType.JSON],
    DataType.ARRAY: [DataType.ANY, DataType.ARRAY, DataType.TABLE],
    DataType.JSON: [DataType.ANY, DataType.JSON, DataType.OBJECT, DataType.STRING],
    DataType.TABLE: [DataType.ANY, DataType.TABLE, DataType.ARRAY],
    DataType.BROWSER: [DataType.ANY, DataType.BROWSER],
    DataType.PAGE: [DataType.ANY, DataType.PAGE, DataType.BROWSER],
    DataType.ELEMENT: [DataType.ANY, DataType.ELEMENT],
    DataType.FILE: [DataType.ANY, DataType.FILE, DataType.BINARY],
    DataType.IMAGE: [DataType.ANY, DataType.IMAGE, DataType.FILE, DataType.BINARY],
    DataType.BINARY: [DataType.ANY, DataType.BINARY],
    DataType.XML: [DataType.ANY, DataType.XML, DataType.STRING],
    DataType.HTML: [DataType.ANY, DataType.HTML, DataType.STRING],
    DataType.CREDENTIAL: [DataType.ANY, DataType.CREDENTIAL],
    # Flow control types
    DataType.CONTROL: [DataType.ANY, DataType.CONTROL],
    DataType.TRIGGER: [DataType.ANY, DataType.TRIGGER, DataType.CONTROL],
    DataType.RESULT: [DataType.ANY, DataType.RESULT, DataType.CONTROL],
}


def is_data_type_compatible(source: DataType, target: DataType) -> bool:
    """
    Check if source data type can connect to target data type.

    Args:
        source: Output port data type
        target: Input port data type

    Returns:
        True if connection is valid
    """
    # ANY target accepts everything
    if target == DataType.ANY:
        return True

    # Check compatibility matrix
    compatible_types = DATA_TYPE_COMPATIBILITY.get(source, [DataType.ANY])
    return target in compatible_types
