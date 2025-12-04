"""
Quality Filter for Knowledge Base
Filters out low-quality, redundant, or unimportant content before archiving

Prevents knowledge base pollution with:
- Trivial conversations
- Debugging output
- Temporary files
- Low-information content
"""
from typing import Dict, Any, Optional, List
import re
from datetime import datetime


class QualityFilter:
    """
    Filters content before storing in knowledge base
    """

    # Patterns to exclude (noise)
    EXCLUDE_PATTERNS = [
        r'print\(',  # Debug prints
        r'console\.log',  # Debug logs
        r'TODO:',  # Temporary notes
        r'FIXME:',  # Temporary notes
        r'test_\w+',  # Test artifacts
        r'\.pyc$',  # Compiled files
        r'__pycache__',  # Cache directories
        r'node_modules',  # Dependencies
        r'\.git/',  # Git internals
        r'\.DS_Store',  # Mac artifacts
        r'Thumbs\.db',  # Windows artifacts
    ]

    # Minimum quality thresholds
    MIN_CONTENT_LENGTH = 50  # Characters
    MIN_WORDS = 5
    MIN_IMPORTANCE_SCORE = 0.3  # 0-1 scale

    # Important keywords (boost score)
    IMPORTANT_KEYWORDS = [
        'module', 'function', 'class', 'error', 'solution',
        'implement', 'feature', 'bug', 'fix', 'optimize',
        'architecture', 'design', 'pattern', 'api', 'database',
        'performance', 'security', 'test', 'documentation'
    ]

    # Trivial conversation patterns
    TRIVIAL_PATTERNS = [
        r'^(ok|yes|no|sure|thanks|got it)$',
        r'^(hi|hello|hey)$',
        r'^\w{1,3}$',  # Very short responses
        r'^[^a-zA-Z]+$',  # Only symbols/numbers
    ]

    def __init__(self):
        """Initialize quality filter"""
        self.filtered_count = 0
        self.passed_count = 0

    def should_archive(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> tuple[bool, float, str]:
        """
        Determine if content should be archived

        Args:
            content: Content to evaluate
            metadata: Optional metadata

        Returns:
            (should_archive, quality_score, reason)
        """
        # Check content exists
        if not content or not content.strip():
            self.filtered_count += 1
            return False, 0.0, "empty_content"

        # Check minimum length
        if len(content) < self.MIN_CONTENT_LENGTH:
            self.filtered_count += 1
            return False, 0.1, "too_short"

        # Check minimum words
        word_count = len(content.split())
        if word_count < self.MIN_WORDS:
            self.filtered_count += 1
            return False, 0.1, "too_few_words"

        # Check for exclude patterns
        for pattern in self.EXCLUDE_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                self.filtered_count += 1
                return False, 0.2, f"excluded_pattern:{pattern}"

        # Check for trivial patterns
        content_lower = content.lower().strip()
        for pattern in self.TRIVIAL_PATTERNS:
            if re.match(pattern, content_lower, re.IGNORECASE):
                self.filtered_count += 1
                return False, 0.2, "trivial_content"

        # Calculate importance score
        score = self.calculate_importance(content, metadata)

        if score < self.MIN_IMPORTANCE_SCORE:
            self.filtered_count += 1
            return False, score, "low_importance"

        # Passed all filters
        self.passed_count += 1
        return True, score, "passed"

    def calculate_importance(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Calculate importance score (0-1)

        Args:
            content: Content text
            metadata: Optional metadata

        Returns:
            Importance score
        """
        score = 0.5  # Base score

        content_lower = content.lower()

        # Keyword matching
        keyword_matches = sum(
            1 for keyword in self.IMPORTANT_KEYWORDS
            if keyword in content_lower
        )
        score += min(keyword_matches * 0.05, 0.3)

        # Length bonus (longer = more substantial)
        if len(content) > 200:
            score += 0.1
        if len(content) > 500:
            score += 0.1

        # Metadata boost
        if metadata:
            # Source importance
            source = metadata.get('source', '')
            if 'documentation' in source or 'feature' in source:
                score += 0.2

            # Category importance
            category = metadata.get('category', '')
            important_categories = ['error', 'solution', 'architecture', 'feature']
            if category in important_categories:
                score += 0.15

            # Priority boost
            priority = metadata.get('priority', '')
            if priority in ['critical', 'high']:
                score += 0.2

        # Code/technical content boost
        if self.has_code_indicators(content):
            score += 0.15

        return min(score, 1.0)  # Cap at 1.0

    def has_code_indicators(self, content: str) -> bool:
        """Check if content contains code"""
        code_indicators = [
            'def ', 'class ', 'import ', 'function ', 'const ',
            'async ', 'await ', 'return ', '=>', '()', '{}',
            'try:', 'except:', 'if __name__'
        ]

        return any(indicator in content for indicator in code_indicators)

    def filter_batch(
        self,
        entries: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Filter a batch of entries

        Args:
            entries: List of entry dicts with 'content' and 'metadata'

        Returns:
            Filtered entries with quality scores
        """
        filtered = []

        for entry in entries:
            content = entry.get('content', '')
            metadata = entry.get('metadata', {})

            should_archive, score, reason = self.should_archive(content, metadata)

            if should_archive:
                # Add quality score to metadata
                metadata['quality_score'] = score
                metadata['filter_reason'] = reason
                entry['metadata'] = metadata
                filtered.append(entry)

        return filtered

    def get_stats(self) -> Dict[str, Any]:
        """Get filtering statistics"""
        total = self.filtered_count + self.passed_count

        return {
            'total_evaluated': total,
            'passed': self.passed_count,
            'filtered': self.filtered_count,
            'pass_rate': self.passed_count / total if total > 0 else 0
        }


class ConversationFilter(QualityFilter):
    """
    Specialized filter for conversations
    """

    # Conversation-specific patterns to exclude
    CONVERSATION_NOISE = [
        r'^(continue|cont|go on)$',  # Simple continuation requests
        r'^ok$',
        r'^(okay|alright|fine|good)$',  # Simple acknowledgments
        r'^(thank you|thanks|thx|ty)$',  # Simple thanks
        r'^(understood|got it|i see)$',  # Understanding confirmations
        r'^\.\.\.$',  # Just ellipsis
        r'^[:;][-]?[)(\[\]{}|/\\]',  # Emoticons only
    ]

    def __init__(self):
        """Initialize conversation filter"""
        super().__init__()
        self.TRIVIAL_PATTERNS.extend(self.CONVERSATION_NOISE)

    def should_archive_message(
        self,
        message: str,
        role: str,
        turn_number: int
    ) -> tuple[bool, float, str]:
        """
        Filter conversation message

        Args:
            message: Message content
            role: 'user' or 'assistant'
            turn_number: Message number in conversation

        Returns:
            (should_archive, quality_score, reason)
        """
        # Exclude very early trivial exchanges
        if turn_number < 3 and len(message) < 20:
            return False, 0.1, "early_trivial"

        # Check base quality
        should_archive, score, reason = self.should_archive(message)

        if not should_archive:
            return False, score, reason

        # Conversation-specific scoring
        if role == 'assistant':
            # Assistant responses with code/solutions are important
            if self.has_code_indicators(message) or 'implement' in message.lower():
                score = min(score + 0.2, 1.0)

        elif role == 'user':
            # User questions with technical terms are important
            if any(kw in message.lower() for kw in ['how', 'why', 'implement', 'error', 'bug']):
                score = min(score + 0.15, 1.0)

        # Re-check threshold
        if score < self.MIN_IMPORTANCE_SCORE:
            return False, score, "conversation_low_importance"

        return True, score, "conversation_passed"


class FileChangeFilter(QualityFilter):
    """
    Specialized filter for file changes
    """

    # File patterns to always exclude
    EXCLUDED_FILES = [
        r'\.log$',  # Log files
        r'\.tmp$',  # Temp files
        r'\.cache$',  # Cache files
        r'\.lock$',  # Lock files
        r'package-lock\.json$',  # Dependency locks
        r'yarn\.lock$',
        r'\.pyc$',
        r'__pycache__/',
        r'node_modules/',
        r'\.git/',
        r'\.idea/',
        r'\.vscode/',
    ]

    # Important file patterns
    IMPORTANT_FILES = [
        r'\.md$',  # Documentation
        r'\.py$',  # Python source
        r'\.js$',  # JavaScript
        r'\.ts$',  # TypeScript
        r'\.yaml$',  # Config/workflows
        r'\.json$',  # Config
        r'requirements\.txt$',
        r'package\.json$',
        r'README',
        r'CHANGELOG',
    ]

    def should_archive_file_change(
        self,
        file_path: str,
        change_type: str
    ) -> tuple[bool, float, str]:
        """
        Filter file changes

        Args:
            file_path: Path to changed file
            change_type: 'added', 'modified', 'deleted'

        Returns:
            (should_archive, quality_score, reason)
        """
        # Exclude certain files
        for pattern in self.EXCLUDED_FILES:
            if re.search(pattern, file_path):
                return False, 0.0, f"excluded_file:{pattern}"

        # Score important files higher
        score = 0.5

        for pattern in self.IMPORTANT_FILES:
            if re.search(pattern, file_path):
                score += 0.3
                break

        # Deletion is less important
        if change_type == 'deleted':
            score -= 0.2

        # New files are more important
        if change_type == 'added':
            score += 0.1

        score = max(0.0, min(score, 1.0))

        if score < self.MIN_IMPORTANCE_SCORE:
            return False, score, "unimportant_file"

        return True, score, "important_file"


def create_filter(filter_type: str = "default") -> QualityFilter:
    """
    Factory function for creating filters

    Args:
        filter_type: Type of filter (default, conversation, file)

    Returns:
        QualityFilter instance
    """
    if filter_type == "conversation":
        return ConversationFilter()
    elif filter_type == "file":
        return FileChangeFilter()
    else:
        return QualityFilter()
