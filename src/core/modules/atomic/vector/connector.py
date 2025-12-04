"""
Vector Database Connector
Manages connection to Qdrant vector database (local or cloud)
"""
from typing import Optional, Dict, Any, List
from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class VectorDBConnector:
    """
    Manages connection to Qdrant vector database
    Supports both local and cloud instances
    """

    def __init__(
        self,
        mode: Optional[str] = None,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        path: Optional[str] = None
    ):
        """
        Initialize vector database connector
        Automatically reads from environment variables if not provided

        Args:
            mode: 'local' or 'cloud' (reads from QDRANT_MODE env var if not provided)
            url: Cloud Qdrant URL (reads from QDRANT_URL env var if not provided)
            api_key: Cloud Qdrant API key (reads from QDRANT_API_KEY env var if not provided)
            path: Local storage path (for local mode)
        """
        # Read from environment variables if not provided
        self.mode = mode or os.getenv("QDRANT_MODE", "cloud")  # Default to cloud, not local
        self.url = url or os.getenv("QDRANT_URL")
        self.api_key = api_key or os.getenv("QDRANT_API_KEY")
        self.path = path or os.getenv("QDRANT_PATH", "./qdrant_storage")
        self.client = None
        self._connected = False

    def connect(self) -> bool:
        """
        Connect to vector database (cloud only - local Qdrant is NOT supported)

        Returns:
            True if connected successfully
        """
        try:
            from qdrant_client import QdrantClient

            # Local mode is NOT supported - force cloud mode
            if self.mode == "local":
                raise ValueError(
                    "Local Qdrant is NOT supported! "
                    "Please use cloud mode with QDRANT_URL and QDRANT_API_KEY environment variables."
                )

            if not self.url or not self.api_key:
                raise ValueError(
                    "Cloud Qdrant requires url and api_key. "
                    "Set QDRANT_URL and QDRANT_API_KEY environment variables."
                )

            # Validate URL is not localhost
            if "localhost" in self.url or "127.0.0.1" in self.url:
                raise ValueError(
                    "Local Qdrant (localhost) is NOT supported! "
                    "Please use Qdrant Cloud or a remote server."
                )

            self.client = QdrantClient(
                url=self.url,
                api_key=self.api_key
            )

            # Test connection
            self.client.get_collections()
            self._connected = True
            return True

        except Exception as e:
            self._connected = False
            raise ConnectionError(f"Failed to connect to Qdrant: {str(e)}")

    def disconnect(self):
        """Disconnect from vector database"""
        if self.client:
            self.client.close()
            self.client = None
            self._connected = False

    def is_connected(self) -> bool:
        """Check if connected"""
        return self._connected and self.client is not None

    def create_collection(
        self,
        collection_name: str,
        vector_size: int = 1536,
        distance: str = "Cosine"
    ) -> bool:
        """
        Create a new collection

        Args:
            collection_name: Name of collection
            vector_size: Dimension of vectors (default 1536 for OpenAI)
            distance: Distance metric (Cosine, Euclid, Dot)

        Returns:
            True if created successfully
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to database")

        from qdrant_client.models import Distance, VectorParams

        distance_map = {
            "Cosine": Distance.COSINE,
            "Euclid": Distance.EUCLID,
            "Dot": Distance.DOT
        }

        try:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=distance_map.get(distance, Distance.COSINE)
                )
            )
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to create collection: {str(e)}")

    def collection_exists(self, collection_name: str) -> bool:
        """Check if collection exists"""
        if not self.is_connected():
            raise ConnectionError("Not connected to database")

        try:
            collections = self.client.get_collections().collections
            return any(c.name == collection_name for c in collections)
        except Exception:
            return False

    def delete_collection(self, collection_name: str) -> bool:
        """Delete a collection"""
        if not self.is_connected():
            raise ConnectionError("Not connected to database")

        try:
            self.client.delete_collection(collection_name)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to delete collection: {str(e)}")

    def get_collections(self) -> List[str]:
        """Get list of all collections"""
        if not self.is_connected():
            raise ConnectionError("Not connected to database")

        try:
            collections = self.client.get_collections().collections
            return [c.name for c in collections]
        except Exception as e:
            raise RuntimeError(f"Failed to get collections: {str(e)}")

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        if not self.is_connected():
            return {
                "connected": False,
                "mode": self.mode
            }

        try:
            collections = self.get_collections()
            return {
                "connected": True,
                "mode": self.mode,
                "url": self.url if self.mode == "cloud" else self.path,
                "collections_count": len(collections),
                "collections": collections
            }
        except Exception as e:
            return {
                "connected": False,
                "mode": self.mode,
                "error": str(e)
            }


# Global connector instance
_global_connector: Optional[VectorDBConnector] = None


def get_connector(
    mode: Optional[str] = None,
    url: Optional[str] = None,
    api_key: Optional[str] = None
) -> VectorDBConnector:
    """
    Get or create global connector instance

    Args:
        mode: Connection mode (local or cloud)
        url: Cloud URL (optional)
        api_key: Cloud API key (optional)

    Returns:
        VectorDBConnector instance
    """
    global _global_connector

    if _global_connector is None:
        # Try environment variables first
        env_url = os.getenv("QDRANT_URL")
        env_api_key = os.getenv("QDRANT_API_KEY")

        mode = mode or ("cloud" if env_url else "local")
        url = url or env_url
        api_key = api_key or env_api_key

        _global_connector = VectorDBConnector(
            mode=mode,
            url=url,
            api_key=api_key
        )
        _global_connector.connect()

    return _global_connector


def close_global_connector():
    """Close global connector"""
    global _global_connector
    if _global_connector:
        _global_connector.disconnect()
        _global_connector = None
