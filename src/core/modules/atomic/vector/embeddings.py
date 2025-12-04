"""
Embedding Generation Module
Converts text to vector embeddings using various providers
"""
import logging
import os
from typing import List, Optional, Dict, Any

from ....constants import (
    OLLAMA_EMBEDDINGS_ENDPOINT,
    EnvVars,
    DEFAULT_TIMEOUT_SECONDS,
)


logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """
    Generates embeddings from text using different providers
    Supports: OpenAI, Ollama, Local (sentence-transformers)
    """

    def __init__(self, provider: str = "local", model: Optional[str] = None):
        """
        Initialize embedding generator

        Args:
            provider: 'openai', 'ollama', or 'local'
            model: Model name (provider-specific)
        """
        self.provider = provider
        self.model = model or self._get_default_model()
        self._client = None

    def _get_default_model(self) -> str:
        """Get default model for provider"""
        defaults = {
            "openai": "text-embedding-3-small",
            "ollama": "nomic-embed-text",
            "local": "all-MiniLM-L6-v2"
        }
        return defaults.get(self.provider, "all-MiniLM-L6-v2")

    def generate(self, text: str) -> List[float]:
        """
        Generate embedding for single text

        Args:
            text: Input text

        Returns:
            Embedding vector as list of floats
        """
        if self.provider == "openai":
            return self._generate_openai(text)
        elif self.provider == "ollama":
            return self._generate_ollama(text)
        else:
            return self._generate_local(text)

    def generate_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        if self.provider == "openai":
            return self._generate_openai_batch(texts)
        elif self.provider == "ollama":
            return [self._generate_ollama(text) for text in texts]
        else:
            return self._generate_local_batch(texts)

    def _generate_openai(self, text: str) -> List[float]:
        """Generate embedding using OpenAI API"""
        try:
            import openai

            api_key = os.getenv(EnvVars.OPENAI_API_KEY)
            if not api_key:
                raise ValueError(f"{EnvVars.OPENAI_API_KEY} not set")

            client = openai.OpenAI(api_key=api_key)
            response = client.embeddings.create(
                input=text,
                model=self.model
            )
            return response.data[0].embedding

        except ImportError:
            raise ImportError("OpenAI package not installed. Run: pip install openai") from None
        except Exception as e:
            logger.exception("OpenAI embedding failed")
            raise RuntimeError(f"OpenAI embedding failed: {str(e)}") from e

    def _generate_openai_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using OpenAI API (batch)"""
        try:
            import openai

            api_key = os.getenv(EnvVars.OPENAI_API_KEY)
            if not api_key:
                raise ValueError(f"{EnvVars.OPENAI_API_KEY} not set")

            client = openai.OpenAI(api_key=api_key)
            response = client.embeddings.create(
                input=texts,
                model=self.model
            )
            return [item.embedding for item in response.data]

        except ImportError:
            raise ImportError("OpenAI package not installed. Run: pip install openai")
        except Exception as e:
            raise RuntimeError(f"OpenAI batch embedding failed: {str(e)}")

    def _generate_ollama(self, text: str) -> List[float]:
        """Generate embedding using Ollama"""
        try:
            import requests

            ollama_url = os.getenv(EnvVars.OLLAMA_API_URL, OLLAMA_EMBEDDINGS_ENDPOINT)
            response = requests.post(
                ollama_url,
                json={
                    "model": self.model,
                    "prompt": text
                },
                timeout=DEFAULT_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            return response.json()["embedding"]

        except requests.exceptions.ConnectionError:
            raise ConnectionError("Ollama not running. Start with: ollama serve")
        except Exception as e:
            raise RuntimeError(f"Ollama embedding failed: {str(e)}")

    def _generate_local(self, text: str) -> List[float]:
        """Generate embedding using local sentence-transformers"""
        try:
            from sentence_transformers import SentenceTransformer

            if self._client is None:
                self._client = SentenceTransformer(self.model)

            embedding = self._client.encode(text)
            return embedding.tolist()

        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )
        except Exception as e:
            raise RuntimeError(f"Local embedding failed: {str(e)}")

    def _generate_local_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using local model (batch)"""
        try:
            from sentence_transformers import SentenceTransformer

            if self._client is None:
                self._client = SentenceTransformer(self.model)

            embeddings = self._client.encode(texts)
            return [emb.tolist() for emb in embeddings]

        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )
        except Exception as e:
            raise RuntimeError(f"Local batch embedding failed: {str(e)}")

    def get_dimension(self) -> int:
        """Get embedding dimension for current model"""
        dimensions = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "nomic-embed-text": 768,
            "all-MiniLM-L6-v2": 384
        }
        return dimensions.get(self.model, 384)

    def get_stats(self) -> Dict[str, Any]:
        """Get generator statistics"""
        return {
            "provider": self.provider,
            "model": self.model,
            "dimension": self.get_dimension(),
            "supports_batch": True
        }


# Convenience functions
def embed_text(
    text: str,
    provider: str = "local",
    model: Optional[str] = None
) -> List[float]:
    """
    Quick function to embed single text

    Args:
        text: Input text
        provider: Embedding provider
        model: Model name

    Returns:
        Embedding vector
    """
    generator = EmbeddingGenerator(provider=provider, model=model)
    return generator.generate(text)


def embed_texts(
    texts: List[str],
    provider: str = "local",
    model: Optional[str] = None
) -> List[List[float]]:
    """
    Quick function to embed multiple texts

    Args:
        texts: List of input texts
        provider: Embedding provider
        model: Model name

    Returns:
        List of embedding vectors
    """
    generator = EmbeddingGenerator(provider=provider, model=model)
    return generator.generate_batch(texts)
