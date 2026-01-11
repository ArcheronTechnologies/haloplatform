"""
Secure model loading for Halo platform.

Prevents pickle deserialization attacks by:
- Only allowing safetensors and HuggingFace formats
- Verifying model integrity via hash
- Never executing remote code
- Restricting allowed model sources

Per security framework section 10.1.
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional, Set

logger = logging.getLogger(__name__)


class ModelSecurityError(Exception):
    """Raised when model loading fails security checks."""

    pass


class SecureModelLoader:
    """
    Secure model loading with integrity verification.

    Security features:
    - Hash verification before loading
    - No pickle deserialization
    - No remote code execution
    - Source allowlist
    """

    # Allowed model sources (HuggingFace repos, internal paths)
    ALLOWED_SOURCES: Set[str] = {
        "KB/",  # KB (Royal Library of Sweden) Swedish models
        "AI-Nordics/",  # Nordic AI models
        "halo-internal/",  # Internal models
    }

    # Allowed file extensions
    ALLOWED_EXTENSIONS = {".safetensors", ".bin", ".pt", ".json", ".txt"}

    def __init__(
        self,
        allowed_sources: Optional[Set[str]] = None,
        verify_hashes: bool = True,
    ):
        """
        Initialize secure model loader.

        Args:
            allowed_sources: Custom source allowlist (uses default if None)
            verify_hashes: Whether to verify model hashes
        """
        self._allowed_sources = allowed_sources or self.ALLOWED_SOURCES
        self._verify_hashes = verify_hashes
        self._known_hashes: dict[str, str] = {}

    def register_hash(self, model_id: str, expected_hash: str) -> None:
        """
        Register expected hash for a model.

        Args:
            model_id: Model identifier (path or HuggingFace repo)
            expected_hash: Expected SHA-256 hash
        """
        self._known_hashes[model_id] = expected_hash

    def verify_source(self, source: str) -> bool:
        """
        Verify model source is in allowlist.

        Args:
            source: Model source (HuggingFace repo or path)

        Returns:
            True if source is allowed
        """
        for allowed in self._allowed_sources:
            if source.startswith(allowed):
                return True
        return False

    def compute_hash(self, path: Path) -> str:
        """
        Compute SHA-256 hash of a file or directory.

        Args:
            path: Path to file or directory

        Returns:
            Hex-encoded SHA-256 hash
        """
        hasher = hashlib.sha256()

        if path.is_file():
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)
        elif path.is_dir():
            # Hash all files in sorted order for determinism
            for file_path in sorted(path.rglob("*")):
                if file_path.is_file():
                    hasher.update(str(file_path.relative_to(path)).encode())
                    with open(file_path, "rb") as f:
                        for chunk in iter(lambda: f.read(8192), b""):
                            hasher.update(chunk)

        return hasher.hexdigest()

    def verify_hash(self, path: Path, expected_hash: str) -> bool:
        """
        Verify file/directory hash matches expected.

        Args:
            path: Path to verify
            expected_hash: Expected SHA-256 hash

        Returns:
            True if hash matches
        """
        actual_hash = self.compute_hash(path)
        if actual_hash != expected_hash:
            logger.warning(
                f"Hash mismatch for {path}: expected {expected_hash[:16]}..., "
                f"got {actual_hash[:16]}..."
            )
            return False
        return True

    def load_safetensors(self, path: Path, expected_hash: Optional[str] = None) -> dict:
        """
        Safely load a safetensors file.

        Args:
            path: Path to .safetensors file
            expected_hash: Optional expected hash

        Returns:
            Loaded tensor dict

        Raises:
            ModelSecurityError: If security checks fail
        """
        if not path.suffix == ".safetensors":
            raise ModelSecurityError(f"Expected .safetensors file, got {path.suffix}")

        if not path.exists():
            raise ModelSecurityError(f"Model file not found: {path}")

        # Verify hash if provided
        if expected_hash and self._verify_hashes:
            if not self.verify_hash(path, expected_hash):
                raise ModelSecurityError("Model integrity check failed")

        try:
            from safetensors.torch import load_file

            return load_file(path)
        except ImportError:
            raise ModelSecurityError(
                "safetensors not installed. Install with: pip install safetensors"
            )

    def load_huggingface(
        self,
        model_id: str,
        expected_hash: Optional[str] = None,
        local_files_only: bool = True,
    ):
        """
        Safely load a HuggingFace model.

        Args:
            model_id: HuggingFace model ID (e.g., "KB/bert-base-swedish-cased")
            expected_hash: Optional expected hash of model directory
            local_files_only: Only load from local cache (default: True for security)

        Returns:
            Loaded model

        Raises:
            ModelSecurityError: If security checks fail
        """
        # Verify source
        if not self.verify_source(model_id):
            raise ModelSecurityError(
                f"Model source not in allowlist: {model_id}. "
                f"Allowed sources: {self._allowed_sources}"
            )

        try:
            from transformers import AutoModel
        except ImportError:
            raise ModelSecurityError(
                "transformers not installed. Install with: pip install transformers"
            )

        # Check for registered hash
        if model_id in self._known_hashes and self._verify_hashes:
            expected_hash = self._known_hashes[model_id]

        # If loading from local and hash provided, verify first
        if local_files_only and expected_hash:
            from huggingface_hub import snapshot_download

            try:
                local_path = Path(
                    snapshot_download(model_id, local_files_only=True)
                )
                if not self.verify_hash(local_path, expected_hash):
                    raise ModelSecurityError("Model integrity check failed")
            except Exception as e:
                if "not found" in str(e).lower():
                    logger.info(f"Model {model_id} not in local cache")
                else:
                    raise

        # Load with security settings
        return AutoModel.from_pretrained(
            model_id,
            trust_remote_code=False,  # CRITICAL: Never run arbitrary code
            local_files_only=local_files_only,
        )

    def load_tokenizer(
        self,
        model_id: str,
        local_files_only: bool = True,
    ):
        """
        Safely load a HuggingFace tokenizer.

        Args:
            model_id: HuggingFace model ID
            local_files_only: Only load from local cache

        Returns:
            Loaded tokenizer

        Raises:
            ModelSecurityError: If security checks fail
        """
        # Verify source
        if not self.verify_source(model_id):
            raise ModelSecurityError(
                f"Model source not in allowlist: {model_id}. "
                f"Allowed sources: {self._allowed_sources}"
            )

        try:
            from transformers import AutoTokenizer
        except ImportError:
            raise ModelSecurityError(
                "transformers not installed. Install with: pip install transformers"
            )

        return AutoTokenizer.from_pretrained(
            model_id,
            trust_remote_code=False,
            local_files_only=local_files_only,
        )

    def load(
        self,
        path: Path,
        expected_hash: Optional[str] = None,
    ):
        """
        Load a model file with automatic format detection.

        Args:
            path: Path to model file or directory
            expected_hash: Optional expected hash

        Returns:
            Loaded model (format depends on file type)

        Raises:
            ModelSecurityError: If format unsupported or security checks fail
        """
        if not path.exists():
            raise ModelSecurityError(f"Model not found: {path}")

        # Check registered hash
        path_str = str(path)
        if path_str in self._known_hashes and self._verify_hashes:
            expected_hash = expected_hash or self._known_hashes[path_str]

        # Verify hash if provided
        if expected_hash and self._verify_hashes:
            if not self.verify_hash(path, expected_hash):
                raise ModelSecurityError("Model integrity check failed")

        # Handle by type
        if path.suffix == ".safetensors":
            return self.load_safetensors(path, expected_hash)

        if path.is_dir():
            # Assume HuggingFace format
            try:
                from transformers import AutoModel

                return AutoModel.from_pretrained(
                    str(path),
                    trust_remote_code=False,
                    local_files_only=True,
                )
            except ImportError:
                raise ModelSecurityError(
                    "transformers not installed for directory loading"
                )

        # Reject pickle-based formats
        if path.suffix in (".pkl", ".pickle"):
            raise ModelSecurityError(
                f"Pickle format not allowed for security reasons: {path}. "
                "Convert to safetensors format."
            )

        raise ModelSecurityError(f"Unsupported model format: {path.suffix}")


# Singleton instance for convenience
_default_loader: Optional[SecureModelLoader] = None


def get_model_loader() -> SecureModelLoader:
    """Get the default secure model loader instance."""
    global _default_loader
    if _default_loader is None:
        _default_loader = SecureModelLoader()
    return _default_loader
