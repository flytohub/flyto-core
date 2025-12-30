"""
Connection Rules Definitions

Default connection rules by category.
"""

from typing import Dict

from .models import ConnectionRule


# Special nodes
SPECIAL_NODES = {"start", "end", "trigger"}


# Default rules by category
# Pattern format: "category.*" or "category.specific" or "*" for any

CONNECTION_RULES: Dict[str, ConnectionRule] = {
    # -------------------------------------------------------------------------
    # Browser Automation - Must stay in browser context chain
    # -------------------------------------------------------------------------
    "browser": ConnectionRule(
        category="browser",
        can_connect_to=[
            "browser.*",    # Other browser actions
            "flow.*",       # Flow control (if, loop, etc.)
            "data.*",       # Data extraction/transformation
            "file.*",       # Save screenshots, downloads
            "analysis.*",   # Analyze page content
            "ai.*",         # AI analysis of page
        ],
        can_receive_from=[
            "browser.*",    # Chain browser actions
            "flow.*",       # Start from flow control
            "start",        # Can be first node
        ],
        description="Browser modules chain with other browser actions or data processing"
    ),

    # -------------------------------------------------------------------------
    # Flow Control - Universal connectors
    # -------------------------------------------------------------------------
    "flow": ConnectionRule(
        category="flow",
        can_connect_to=["*"],      # Can connect to anything
        can_receive_from=["*"],    # Can receive from anything
        description="Flow control modules are universal connectors"
    ),

    # -------------------------------------------------------------------------
    # Data Transformation - Universal
    # -------------------------------------------------------------------------
    "data": ConnectionRule(
        category="data",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="Data transformation modules work with any data source"
    ),

    "array": ConnectionRule(
        category="array",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="Array operations work with any data"
    ),

    "object": ConnectionRule(
        category="object",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="Object operations work with any data"
    ),

    "string": ConnectionRule(
        category="string",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="String operations work with any data"
    ),

    "math": ConnectionRule(
        category="math",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="Math operations work with numeric data"
    ),

    "datetime": ConnectionRule(
        category="datetime",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="DateTime operations work with any data"
    ),

    # -------------------------------------------------------------------------
    # File System
    # -------------------------------------------------------------------------
    "file": ConnectionRule(
        category="file",
        can_connect_to=[
            "file.*",       # Chain file operations
            "flow.*",       # Flow control
            "data.*",       # Process file content
            "document.*",   # Document processing
            "analysis.*",   # Analyze content
        ],
        can_receive_from=["*"],  # Any module can trigger file ops
        description="File operations can be triggered by any module"
    ),

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    "database": ConnectionRule(
        category="database",
        can_connect_to=[
            "database.*",   # Chain queries
            "flow.*",       # Flow control
            "data.*",       # Transform results
            "file.*",       # Export to file
            "api.*",        # Send to API
        ],
        can_receive_from=["*"],
        description="Database modules process and output structured data"
    ),

    # -------------------------------------------------------------------------
    # API / HTTP
    # -------------------------------------------------------------------------
    "api": ConnectionRule(
        category="api",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="API modules are universal data exchangers"
    ),

    "http": ConnectionRule(
        category="http",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="HTTP modules are universal data exchangers"
    ),

    # -------------------------------------------------------------------------
    # AI / Analysis
    # -------------------------------------------------------------------------
    "ai": ConnectionRule(
        category="ai",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="AI modules can process any data"
    ),

    "analysis": ConnectionRule(
        category="analysis",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="Analysis modules work with any data"
    ),

    # -------------------------------------------------------------------------
    # Document Processing
    # -------------------------------------------------------------------------
    "document": ConnectionRule(
        category="document",
        can_connect_to=[
            "document.*",
            "flow.*",
            "data.*",
            "file.*",
            "ai.*",
        ],
        can_receive_from=[
            "file.*",
            "flow.*",
            "browser.*",    # Download from browser
            "api.*",        # Receive from API
            "start",
        ],
        description="Document modules process files and output data"
    ),

    # -------------------------------------------------------------------------
    # Notification / Output
    # -------------------------------------------------------------------------
    "notification": ConnectionRule(
        category="notification",
        can_connect_to=[
            "flow.*",       # Continue after notification
            "end",          # End workflow
        ],
        can_receive_from=["*"],  # Any module can trigger notification
        description="Notification modules are typically endpoints"
    ),

    # -------------------------------------------------------------------------
    # Utility / Meta
    # -------------------------------------------------------------------------
    "utility": ConnectionRule(
        category="utility",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="Utility modules are universal"
    ),

    "meta": ConnectionRule(
        category="meta",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="Meta modules are universal"
    ),

    # -------------------------------------------------------------------------
    # Composite modules follow their internal category
    # -------------------------------------------------------------------------
    "composite": ConnectionRule(
        category="composite",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="Composite modules depend on their internal implementation"
    ),
}
