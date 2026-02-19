# Flyto2 Core - Source Available License
# Copyright (c) 2025 Flyto2. All Rights Reserved.
#
# This source code is licensed under the Flyto2 Source Available License v1.0.
# Commercial use requires a license. See LICENSE for details.

"""
Connection Rules Definitions

Default connection rules by category.
These are STRICT defaults - individual modules can override with more permissive rules if needed.
"""

from typing import Dict

from .models import ConnectionRule


# Special nodes
SPECIAL_NODES = {"start", "end", "trigger"}


# Default rules by category
# Pattern format: "category.*" or "category.specific" or "*" for any

CONNECTION_RULES: Dict[str, ConnectionRule] = {
    # =========================================================================
    # Browser Automation - STRICT: Must stay in browser context chain
    # =========================================================================
    "browser": ConnectionRule(
        category="browser",
        can_connect_to=[
            "browser.*",    # Chain browser actions
            "element.*",    # Element operations
            "flow.*",       # Flow control
        ],
        can_receive_from=[
            "browser.*",    # Chain browser actions
            "flow.*",       # From flow control
            "start",        # Can be first node
        ],
        description="Browser modules must stay in browser context - NO direct connection to AI/API"
    ),

    # =========================================================================
    # Element Operations - STRICT: Requires browser context
    # =========================================================================
    "element": ConnectionRule(
        category="element",
        can_connect_to=[
            "element.*",    # Chain element actions
            "browser.*",    # Back to browser
            "data.*",       # Extract data
            "string.*",     # String operations
            "flow.*",       # Flow control
            "file.*",       # Save data
        ],
        can_receive_from=[
            "browser.*",    # From browser (find, goto, etc.)
            "element.*",    # Chain elements
            "flow.*",       # From flow control
        ],
        description="Element modules require browser context - can only receive from browser/element"
    ),

    # =========================================================================
    # Flow Control - RESTRICTED: Different rules for different flow modules
    # Category default is restrictive; specific modules override in their definition
    # =========================================================================
    "flow": ConnectionRule(
        category="flow",
        can_connect_to=["*"],  # Flow outputs can go anywhere
        can_receive_from=[
            # Flow control should receive from data-producing modules
            "data.*",
            "http.*",
            "string.*",
            "array.*",
            "object.*",
            "math.*",
            "file.*",
            "database.*",
            "ai.*",
            "flow.*",       # Chain flow controls
            "element.*",    # Element data
            "start",
        ],
        description="Flow control receives from data-producing modules"
    ),

    # =========================================================================
    # Data Transformation - Universal but NO browser output
    # =========================================================================
    "data": ConnectionRule(
        category="data",
        can_connect_to=[
            "data.*",
            "array.*",
            "object.*",
            "string.*",
            "math.*",
            "file.*",
            "database.*",
            "http.*",
            "ai.*",
            "notify.*",
            "flow.*",
            # NO browser.* - data can't control browser
        ],
        can_receive_from=["*"],  # Can receive from anything
        description="Data modules transform data - cannot output to browser"
    ),

    "array": ConnectionRule(
        category="array",
        can_connect_to=[
            "data.*",
            "array.*",
            "object.*",
            "string.*",
            "file.*",
            "database.*",
            "http.*",
            "ai.*",
            "notify.*",
            "flow.*",
        ],
        can_receive_from=["*"],
        description="Array operations - cannot output to browser"
    ),

    "object": ConnectionRule(
        category="object",
        can_connect_to=[
            "data.*",
            "array.*",
            "object.*",
            "string.*",
            "file.*",
            "database.*",
            "http.*",
            "ai.*",
            "notify.*",
            "flow.*",
        ],
        can_receive_from=["*"],
        description="Object operations - cannot output to browser"
    ),

    "string": ConnectionRule(
        category="string",
        can_connect_to=[
            "data.*",
            "array.*",
            "object.*",
            "string.*",
            "file.*",
            "database.*",
            "http.*",
            "ai.*",
            "notify.*",
            "flow.*",
        ],
        can_receive_from=["*"],
        description="String operations - cannot output to browser"
    ),

    "math": ConnectionRule(
        category="math",
        can_connect_to=[
            "data.*",
            "array.*",
            "object.*",
            "string.*",
            "math.*",
            "file.*",
            "database.*",
            "http.*",
            "notify.*",
            "flow.*",
        ],
        can_receive_from=["*"],
        description="Math operations - cannot output to browser"
    ),

    "datetime": ConnectionRule(
        category="datetime",
        can_connect_to=[
            "data.*",
            "string.*",
            "file.*",
            "database.*",
            "http.*",
            "notify.*",
            "flow.*",
        ],
        can_receive_from=["*"],
        description="DateTime operations - cannot output to browser"
    ),

    # =========================================================================
    # File System - Can receive from anywhere, limited output
    # =========================================================================
    "file": ConnectionRule(
        category="file",
        can_connect_to=[
            "file.*",       # Chain file operations
            "data.*",       # Process file content
            "pdf.*",        # PDF processing
            "image.*",      # Image processing
            "ai.*",         # AI analysis
            "notify.*",     # Send file
            "flow.*",       # Flow control
        ],
        can_receive_from=["*"],  # Any module can trigger file ops
        description="File operations - wide input, structured output"
    ),

    # =========================================================================
    # Image Processing - Similar to file
    # =========================================================================
    "image": ConnectionRule(
        category="image",
        can_connect_to=[
            "image.*",
            "file.*",
            "ai.*",
            "data.*",
            "notify.*",
            "flow.*",
        ],
        can_receive_from=[
            "file.*",
            "image.*",
            "browser.*",  # Download image
            "http.*",
            "flow.*",
            "start",
        ],
        description="Image processing modules"
    ),

    # =========================================================================
    # Database - Structured data in/out
    # =========================================================================
    "database": ConnectionRule(
        category="database",
        can_connect_to=[
            "database.*",   # Chain queries
            "data.*",       # Transform results
            "array.*",      # Array operations
            "object.*",     # Object operations
            "file.*",       # Export to file
            "http.*",       # Send to API
            "notify.*",     # Notify
            "flow.*",       # Flow control
        ],
        can_receive_from=[
            "data.*",
            "array.*",
            "object.*",
            "file.*",
            "http.*",
            "flow.*",
            "start",
        ],
        description="Database modules - structured data only, no browser"
    ),

    # =========================================================================
    # API / HTTP - Data exchange, NO browser
    # =========================================================================
    "api": ConnectionRule(
        category="api",
        can_connect_to=[
            "data.*",
            "array.*",
            "object.*",
            "string.*",
            "file.*",
            "database.*",
            "http.*",
            "ai.*",
            "notify.*",
            "flow.*",
            # NO browser.* - API responses don't control browser
        ],
        can_receive_from=["*"],
        description="API modules - data exchange, cannot output to browser"
    ),

    "http": ConnectionRule(
        category="http",
        can_connect_to=[
            "data.*",
            "array.*",
            "object.*",
            "string.*",
            "file.*",
            "database.*",
            "http.*",
            "ai.*",
            "notify.*",
            "flow.*",
        ],
        can_receive_from=["*"],
        description="HTTP modules - data exchange, cannot output to browser"
    ),

    # =========================================================================
    # AI / ML - STRICT: Cannot output to browser
    # =========================================================================
    "ai": ConnectionRule(
        category="ai",
        can_connect_to=[
            "data.*",
            "string.*",
            "array.*",
            "object.*",
            "file.*",
            "database.*",
            "http.*",
            "notify.*",
            "flow.*",
            "ai.*",
            # NO browser.* - AI cannot control browser
        ],
        can_receive_from=[
            "data.*",
            "string.*",
            "array.*",
            "object.*",
            "file.*",
            "image.*",
            "http.*",
            "database.*",
            "ai.*",
            "flow.*",
            "start",
            # Can receive browser data via element.get_* but not browser control
        ],
        description="AI modules process data - CANNOT output to browser"
    ),

    "llm": ConnectionRule(
        category="llm",
        can_connect_to=[
            "data.*",
            "string.*",
            "file.*",
            "http.*",
            "notify.*",
            "flow.*",
        ],
        can_receive_from=["*"],
        description="LLM modules - text in, text out"
    ),

    # =========================================================================
    # Analysis - Can receive from browser, cannot output to browser
    # =========================================================================
    "analysis": ConnectionRule(
        category="analysis",
        can_connect_to=[
            "data.*",
            "array.*",
            "object.*",
            "string.*",
            "file.*",
            "database.*",
            "ai.*",
            "notify.*",
            "flow.*",
            # NO browser.* - analysis results don't control browser
        ],
        can_receive_from=[
            "browser.*",    # Analyze page
            "element.*",    # Analyze element
            "file.*",       # Analyze file
            "data.*",       # Analyze data
            "http.*",       # Analyze response
            "flow.*",
            "start",
        ],
        description="Analysis modules - can receive from browser, cannot output to browser"
    ),

    # =========================================================================
    # Document Processing - File-based
    # =========================================================================
    "document": ConnectionRule(
        category="document",
        can_connect_to=[
            "pdf.*",
            "data.*",
            "string.*",
            "file.*",
            "ai.*",
            "notify.*",
            "flow.*",
        ],
        can_receive_from=[
            "file.*",
            "browser.*",    # Download from browser
            "http.*",       # Receive from API
            "pdf.*",
            "flow.*",
            "start",
        ],
        description="Document modules - file processing"
    ),

    # =========================================================================
    # Notify - Notification output endpoint
    # =========================================================================
    "notify": ConnectionRule(
        category="notify",
        can_connect_to=["notify.*", "data.*", "flow.*", "end"],
        can_receive_from=["*"],
        description="Notification modules - output endpoint"
    ),

    # =========================================================================
    # Notification / Output - End point, can receive from anywhere
    # =========================================================================
    "notification": ConnectionRule(
        category="notification",
        can_connect_to=[
            "notify.*",       # Chain notifications
            "data.*",          # Log response
            "flow.*",          # Continue after
            "end",             # End workflow
        ],
        can_receive_from=["*"],  # Any module can trigger notification
        description="Notification modules - output endpoint"
    ),

    "communication": ConnectionRule(
        category="communication",
        can_connect_to=[
            "notify.*",
            "email.*",
            "slack.*",
            "webhook.*",
            "data.*",
            "flow.*",
            "end",
        ],
        can_receive_from=["*"],
        description="Communication modules - output endpoint"
    ),

    # =========================================================================
    # Testing - Can connect to flow control
    # =========================================================================
    "test": ConnectionRule(
        category="test",
        can_connect_to=[
            "test.*",
            "flow.*",
            "notify.*",
            "data.*",
        ],
        can_receive_from=["*"],
        description="Test modules - assertion and validation"
    ),

    "testing": ConnectionRule(
        category="testing",
        can_connect_to=[
            "testing.*",
            "test.*",
            "flow.*",
            "notify.*",
            "data.*",
        ],
        can_receive_from=["*"],
        description="Testing modules - assertion and validation"
    ),

    # =========================================================================
    # Utility / Meta - Mostly universal but no browser output
    # =========================================================================
    "utility": ConnectionRule(
        category="utility",
        can_connect_to=[
            "data.*",
            "string.*",
            "file.*",
            "http.*",
            "notify.*",
            "flow.*",
            "utility.*",
        ],
        can_receive_from=["*"],
        description="Utility modules - helpers"
    ),

    "meta": ConnectionRule(
        category="meta",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="Meta modules are universal (logging, debug, etc.)"
    ),

    # =========================================================================
    # HuggingFace - AI models, no browser output
    # =========================================================================
    "huggingface": ConnectionRule(
        category="huggingface",
        can_connect_to=[
            "data.*",
            "string.*",
            "array.*",
            "object.*",
            "file.*",
            "ai.*",
            "huggingface.*",
            "notify.*",
            "flow.*",
        ],
        can_receive_from=[
            "data.*",
            "string.*",
            "file.*",
            "image.*",
            "http.*",
            "huggingface.*",
            "flow.*",
            "start",
        ],
        description="HuggingFace AI models - no browser interaction"
    ),

    # =========================================================================
    # Composite modules - Depend on their internal implementation
    # =========================================================================
    "composite": ConnectionRule(
        category="composite",
        can_connect_to=["*"],
        can_receive_from=["*"],
        description="Composite modules depend on their internal implementation"
    ),

    # =========================================================================
    # Shell/Process - System operations, restricted
    # =========================================================================
    "shell": ConnectionRule(
        category="shell",
        can_connect_to=[
            "data.*",
            "string.*",
            "file.*",
            "flow.*",
            "test.*",
        ],
        can_receive_from=[
            "data.*",
            "string.*",
            "file.*",
            "flow.*",
            "start",
        ],
        description="Shell operations - system commands"
    ),

    "process": ConnectionRule(
        category="process",
        can_connect_to=[
            "process.*",
            "port.*",
            "data.*",
            "flow.*",
            "test.*",
        ],
        can_receive_from=[
            "process.*",
            "flow.*",
            "start",
        ],
        description="Process management"
    ),

    "port": ConnectionRule(
        category="port",
        can_connect_to=[
            "browser.*",  # Port ready, launch browser
            "http.*",
            "flow.*",
            "test.*",
        ],
        can_receive_from=[
            "process.*",
            "flow.*",
            "start",
        ],
        description="Port operations - typically before browser/http"
    ),
}
