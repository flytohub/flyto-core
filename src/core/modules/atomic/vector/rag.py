"""
RAG (Retrieval-Augmented Generation)
Intelligent memory retrieval for AI decision making
"""
from typing import List, Dict, Any, Optional
from .knowledge_store import KnowledgeStore


class RAGRetriever:
    """
    Retrieves relevant memories for AI context augmentation
    """

    def __init__(self, knowledge_store: KnowledgeStore):
        """
        Initialize RAG retriever

        Args:
            knowledge_store: KnowledgeStore instance
        """
        self.store = knowledge_store

    def retrieve_for_module_proposal(
        self,
        proposed_module: str,
        description: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant memories when proposing new module

        Args:
            proposed_module: Proposed module ID
            description: Module description
            top_k: Number of memories to retrieve

        Returns:
            List of relevant memories
        """
        query = f"Module {proposed_module}: {description}"

        # Search for similar modules and experiences
        results = self.store.search(
            query=query,
            top_k=top_k,
            filters={"category": "module"}
        )

        return results

    def retrieve_for_error_analysis(
        self,
        module_id: str,
        error_message: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant memories for error analysis

        Args:
            module_id: Module that encountered error
            error_message: Error message
            top_k: Number of memories to retrieve

        Returns:
            List of relevant error cases and solutions
        """
        query = f"Error in {module_id}: {error_message}"

        # Search for similar errors
        results = self.store.search(
            query=query,
            top_k=top_k,
            filters={"category": "error"}
        )

        return results

    def retrieve_for_optimization(
        self,
        optimization_target: str,
        context: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant memories for performance optimization

        Args:
            optimization_target: What to optimize
            context: Context description
            top_k: Number of memories to retrieve

        Returns:
            List of successful optimization patterns
        """
        query = f"Optimize {optimization_target}: {context}"

        # Search for success patterns and performance data
        results = self.store.search(
            query=query,
            top_k=top_k
        )

        # Filter for success and performance categories
        filtered = [
            r for r in results
            if r.get("metadata", {}).get("category") in ["success", "performance"]
        ]

        return filtered[:top_k]

    def retrieve_for_website_practice(
        self,
        website: str,
        task: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant memories for website practice

        Args:
            website: Target website
            task: Task description
            top_k: Number of memories to retrieve

        Returns:
            List of relevant practice experiences
        """
        query = f"Practice on {website}: {task}"

        # Search for practice experiences
        results = self.store.search(
            query=query,
            top_k=top_k
        )

        # Prioritize same website
        same_site = [r for r in results if website in r.get("content", "")]
        other_site = [r for r in results if website not in r.get("content", "")]

        return (same_site + other_site)[:top_k]

    def retrieve_multi_category(
        self,
        query: str,
        categories: List[str],
        top_k_per_category: int = 3
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Retrieve memories from multiple categories

        Args:
            query: Search query
            categories: List of categories to search
            top_k_per_category: Results per category

        Returns:
            Dict mapping category to results
        """
        results_by_category = {}

        for category in categories:
            results = self.store.search(
                query=query,
                top_k=top_k_per_category * 2,  # Get more, then filter
                filters={"category": category}
            )
            results_by_category[category] = results[:top_k_per_category]

        return results_by_category


class RAGFormatter:
    """
    Formats retrieved memories for AI prompts
    """

    @staticmethod
    def format_for_prompt(
        memories: List[Dict[str, Any]],
        format_style: str = "markdown"
    ) -> str:
        """
        Format memories for AI prompt injection

        Args:
            memories: Retrieved memories
            format_style: Format style (markdown, json, text)

        Returns:
            Formatted string
        """
        if not memories:
            return "No relevant memories found."

        if format_style == "markdown":
            return RAGFormatter._format_markdown(memories)
        elif format_style == "json":
            import json
            return json.dumps(memories, indent=2)
        else:
            return RAGFormatter._format_text(memories)

    @staticmethod
    def _format_markdown(memories: List[Dict[str, Any]]) -> str:
        """Format as markdown"""
        lines = ["## Relevant Past Experiences\n"]

        for i, memory in enumerate(memories, 1):
            content = memory.get("content", "")
            score = memory.get("score", 0)
            metadata = memory.get("metadata", {})

            lines.append(f"### {i}. {metadata.get('category', 'unknown').title()}")
            lines.append(f"**Similarity**: {score:.2%}")
            lines.append(f"\n{content}\n")

            if metadata.get("source"):
                lines.append(f"*Source: {metadata['source']}*\n")

        return "\n".join(lines)

    @staticmethod
    def _format_text(memories: List[Dict[str, Any]]) -> str:
        """Format as plain text"""
        lines = ["Relevant Past Experiences:\n"]

        for i, memory in enumerate(memories, 1):
            content = memory.get("content", "")
            score = memory.get("score", 0)

            lines.append(f"{i}. {content} (similarity: {score:.1%})")

        return "\n".join(lines)

    @staticmethod
    def format_by_category(
        memories_by_category: Dict[str, List[Dict[str, Any]]]
    ) -> str:
        """
        Format multi-category results

        Args:
            memories_by_category: Results grouped by category

        Returns:
            Formatted string
        """
        lines = ["## Retrieved Memories by Category\n"]

        for category, memories in memories_by_category.items():
            if not memories:
                continue

            lines.append(f"### {category.title()}\n")

            for memory in memories:
                content = memory.get("content", "")
                score = memory.get("score", 0)
                lines.append(f"- {content[:100]}... (score: {score:.2%})")

            lines.append("")

        return "\n".join(lines)


class RAGPipeline:
    """
    Complete RAG pipeline for AI context augmentation
    """

    def __init__(self, knowledge_store: KnowledgeStore):
        """
        Initialize RAG pipeline

        Args:
            knowledge_store: KnowledgeStore instance
        """
        self.retriever = RAGRetriever(knowledge_store)
        self.formatter = RAGFormatter()

    def augment_context(
        self,
        query: str,
        context_type: str,
        top_k: int = 5,
        format_style: str = "markdown"
    ) -> str:
        """
        Complete RAG pipeline: retrieve + format

        Args:
            query: Search query
            context_type: Type of context (proposal, error, optimization, practice)
            top_k: Number of results
            format_style: Output format

        Returns:
            Formatted context string
        """
        # Retrieve based on context type
        if context_type == "proposal":
            memories = self.retriever.retrieve_for_module_proposal(
                proposed_module=query.split(":")[0] if ":" in query else query,
                description=query,
                top_k=top_k
            )
        elif context_type == "error":
            memories = self.retriever.retrieve_for_error_analysis(
                module_id=query.split(":")[0] if ":" in query else "unknown",
                error_message=query,
                top_k=top_k
            )
        elif context_type == "optimization":
            memories = self.retriever.retrieve_for_optimization(
                optimization_target=query,
                context="",
                top_k=top_k
            )
        else:
            # Generic search
            memories = self.retriever.store.search(query, top_k=top_k)

        # Format for prompt
        return self.formatter.format_for_prompt(memories, format_style)

    def build_augmented_prompt(
        self,
        base_prompt: str,
        query: str,
        context_type: str = "generic",
        top_k: int = 3
    ) -> str:
        """
        Build complete prompt with RAG context

        Args:
            base_prompt: Original prompt
            query: Query for memory retrieval
            context_type: Type of context
            top_k: Number of memories

        Returns:
            Augmented prompt
        """
        context = self.augment_context(
            query=query,
            context_type=context_type,
            top_k=top_k
        )

        augmented = f"""{base_prompt}

{context}

Based on the above past experiences, please provide your response:
"""

        return augmented
