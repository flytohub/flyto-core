"""
Workflow Automation Engine
A powerful automation platform for web scraping and workflow orchestration
"""
from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="workflow-engine",
    version="1.0.0",
    author="Workflow Engine Team",
    author_email="team@workflow-engine.dev",
    description="A powerful automation engine for web scraping and workflow orchestration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/flytohub/flyto2",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "pyyaml>=6.0",
        "playwright>=1.40.0",
        "fastapi>=0.104.0",
        "uvicorn>=0.24.0",
        "pydantic>=2.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "pylint>=3.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "workflow-engine=cli.main:main",
            "wfe=cli.main:main",  # Short alias
        ],
    },
    include_package_data=True,
    package_data={
        "": ["i18n/*.json", "workflows/*.yaml"],
    },
)
