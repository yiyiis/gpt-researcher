"""Configuration management for GPT Researcher.

This module provides the Config class that manages all configuration
settings for GPT Researcher including LLM providers, embeddings,
retrievers, and various operational parameters.
"""

import json
import os
import sys
import warnings
from typing import Any, Dict, List, Type, Union, get_args, get_origin

from gpt_researcher.llm_provider.generic.base import ReasoningEfforts

from .variables.base import BaseConfig
from .variables.default import DEFAULT_CONFIG


def _get_base_path() -> str:
    """Get the base path for finding config files.

    Handles three scenarios:
    1. PyInstaller bundle: uses sys._MEIPASS (temp extraction dir) or exe dir
    2. Nuitka / compiled: uses the executable's directory
    3. Normal Python: uses the project root (3 levels up from this file)
    """
    # PyInstaller: sys.frozen is set, _MEIPASS is the temp extraction dir
    if getattr(sys, 'frozen', False):
        # First try the directory containing the executable (where config.json likely lives)
        exe_dir = os.path.dirname(sys.executable)
        if os.path.exists(os.path.join(exe_dir, "config.json")):
            return exe_dir
        # Fallback to PyInstaller's temp dir (bundled files are here)
        return getattr(sys, '_MEIPASS', exe_dir)

    # Normal Python execution: walk up from this file to project root
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Config:
    """Configuration manager for GPT Researcher.

    Handles loading, parsing, and managing all configuration settings
    from files, environment variables, and defaults.

    Attributes:
        CONFIG_DIR: Directory containing configuration files.
        config_path: Path to the configuration file.
        llm_kwargs: Additional keyword arguments for LLM.
        embedding_kwargs: Additional keyword arguments for embeddings.
    """

    CONFIG_DIR = os.path.join(os.path.dirname(__file__), "variables")

    def __init__(self, config_path: str | None = None):
        """Initialize the config class.

        Args:
            config_path: Optional path to a JSON configuration file.
        """
        self.config_path = config_path
        self.llm_kwargs: Dict[str, Any] = {}
        self.embedding_kwargs: Dict[str, Any] = {}

        config_to_use = self.load_config(config_path)
        self._set_attributes(config_to_use)
        self._set_embedding_attributes()
        self._set_llm_attributes()
        self._handle_deprecated_attributes()
        if config_to_use['REPORT_SOURCE'] != 'web':
          self._set_doc_path(config_to_use)

        # MCP support configuration
        self.mcp_servers = []  # List of MCP server configurations
        self.mcp_allowed_root_paths = []  # Allowed root paths for MCP servers

        # Read from config
        if hasattr(self, 'mcp_servers'):
            self.mcp_servers = self.mcp_servers
        if hasattr(self, 'mcp_allowed_root_paths'):
            self.mcp_allowed_root_paths = self.mcp_allowed_root_paths

    def _set_attributes(self, config: Dict[str, Any]) -> None:
        """Set configuration attributes from config dictionary.

        Merges environment variables with config file values, with
        environment variables taking precedence.

        Args:
            config: Dictionary of configuration key-value pairs.
        """
        for key, value in config.items():
            env_value = os.getenv(key)
            if env_value is not None:
                value = self.convert_env_value(key, env_value, BaseConfig.__annotations__[key])
            setattr(self, key.lower(), value)

        # Handle RETRIEVER with default value
        retriever_env = os.environ.get("RETRIEVER", config.get("RETRIEVER", "tavily"))
        try:
            self.retrievers = self.parse_retrievers(retriever_env)
        except ValueError as e:
            print(f"Warning: {str(e)}. Defaulting to 'tavily' retriever.")
            self.retrievers = ["tavily"]

    def _set_embedding_attributes(self) -> None:
        """Parse and set embedding provider and model attributes."""
        self.embedding_provider, self.embedding_model = self.parse_embedding(
            self.embedding
        )

    def _set_llm_attributes(self) -> None:
        """Parse and set LLM provider and model attributes for all LLM types."""
        self.fast_llm_provider, self.fast_llm_model = self.parse_llm(self.fast_llm)
        self.smart_llm_provider, self.smart_llm_model = self.parse_llm(self.smart_llm)
        self.strategic_llm_provider, self.strategic_llm_model = self.parse_llm(self.strategic_llm)
        self.reasoning_effort = self.parse_reasoning_effort(os.getenv("REASONING_EFFORT"))

    def _handle_deprecated_attributes(self) -> None:
        """Handle deprecated configuration attributes with warnings."""
        if os.getenv("EMBEDDING_PROVIDER") is not None:
            warnings.warn(
                "EMBEDDING_PROVIDER is deprecated and will be removed soon. Use EMBEDDING instead.",
                FutureWarning,
                stacklevel=2,
            )
            self.embedding_provider = (
                os.environ["EMBEDDING_PROVIDER"] or self.embedding_provider
            )

            embedding_provider = os.environ["EMBEDDING_PROVIDER"]
            if embedding_provider == "ollama":
                self.embedding_model = os.environ["OLLAMA_EMBEDDING_MODEL"]
            elif embedding_provider == "custom":
                self.embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "custom")
            elif embedding_provider == "openai":
                self.embedding_model = "text-embedding-3-large"
            elif embedding_provider == "azure_openai":
                self.embedding_model = "text-embedding-3-large"
            elif embedding_provider == "huggingface":
                self.embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
            elif embedding_provider == "gigachat":
                self.embedding_model = "Embeddings"
            elif embedding_provider == "google_genai":
                self.embedding_model = "text-embedding-004"
            else:
                raise Exception("Embedding provider not found.")

        _deprecation_warning = (
            "LLM_PROVIDER, FAST_LLM_MODEL and SMART_LLM_MODEL are deprecated and "
            "will be removed soon. Use FAST_LLM and SMART_LLM instead."
        )
        if os.getenv("LLM_PROVIDER") is not None:
            warnings.warn(_deprecation_warning, FutureWarning, stacklevel=2)
            self.fast_llm_provider = (
                os.environ["LLM_PROVIDER"] or self.fast_llm_provider
            )
            self.smart_llm_provider = (
                os.environ["LLM_PROVIDER"] or self.smart_llm_provider
            )
        if os.getenv("FAST_LLM_MODEL") is not None:
            warnings.warn(_deprecation_warning, FutureWarning, stacklevel=2)
            self.fast_llm_model = os.environ["FAST_LLM_MODEL"] or self.fast_llm_model
        if os.getenv("SMART_LLM_MODEL") is not None:
            warnings.warn(_deprecation_warning, FutureWarning, stacklevel=2)
            self.smart_llm_model = os.environ["SMART_LLM_MODEL"] or self.smart_llm_model

    def _set_doc_path(self, config: Dict[str, Any]) -> None:
        self.doc_path = config['DOC_PATH']
        if self.doc_path:
            try:
                self.validate_doc_path()
            except Exception as e:
                print(f"Warning: Error validating doc_path: {str(e)}. Using default doc_path.")
                self.doc_path = DEFAULT_CONFIG['DOC_PATH']

    @classmethod
    def load_config(cls, config_path: str | None) -> Dict[str, Any]:
        """Load a configuration by name.

        Resolution order:
        1. Explicit config_path argument (if it exists as a file)
        2. CONFIG_PATH environment variable (if set and file exists)
        3. config.json auto-discovered near the executable or project root
        4. DEFAULT_CONFIG as final fallback

        Works in normal Python, PyInstaller, and Nuitka compiled environments.
        """
        def _merge_with_defaults(path: str) -> Dict[str, Any]:
            with open(path, "r") as f:
                custom_config = json.load(f)
            merged = DEFAULT_CONFIG.copy()
            merged.update(custom_config)
            return merged

        # Step 1: Try explicit config_path argument
        if config_path and config_path != "default":
            if os.path.exists(config_path):
                return _merge_with_defaults(config_path)
            else:
                print(f"Warning: Configuration not found at '{config_path}'.")
                if not config_path.endswith(".json"):
                    print(f"Do you mean '{config_path}.json'?")

        # Step 2: Try CONFIG_PATH environment variable
        env_config_path = os.environ.get("CONFIG_PATH")
        if env_config_path and os.path.exists(env_config_path):
            return _merge_with_defaults(env_config_path)

        # Step 3: Auto-discover config.json
        # Uses _get_base_path() which handles compiled executables correctly
        base_path = _get_base_path()
        auto_config_path = os.path.join(base_path, "config.json")
        if os.path.exists(auto_config_path):
            return _merge_with_defaults(auto_config_path)

        # Step 4: Fallback to defaults
        return DEFAULT_CONFIG

    @classmethod
    def list_available_configs(cls) -> List[str]:
        """List all available configuration names."""
        configs = ["default"]
        for file in os.listdir(cls.CONFIG_DIR):
            if file.endswith(".json"):
                configs.append(file[:-5])  # Remove .json extension
        return configs

    def parse_retrievers(self, retriever_str: str) -> List[str]:
        """Parse the retriever string into a list of retrievers and validate them."""
        from ..retrievers.utils import get_all_retriever_names
        
        retrievers = [retriever.strip()
                      for retriever in retriever_str.split(",")]
        valid_retrievers = get_all_retriever_names() or []
        invalid_retrievers = [r for r in retrievers if r not in valid_retrievers]
        if invalid_retrievers:
            raise ValueError(
                f"Invalid retriever(s) found: {', '.join(invalid_retrievers)}. "
                f"Valid options are: {', '.join(valid_retrievers)}."
            )
        return retrievers

    @staticmethod
    def parse_llm(llm_str: str | None) -> tuple[str | None, str | None]:
        """Parse llm string into (llm_provider, llm_model)."""
        from gpt_researcher.llm_provider.generic.base import _SUPPORTED_PROVIDERS

        if llm_str is None:
            return None, None
        try:
            llm_provider, llm_model = llm_str.split(":", 1)
            assert llm_provider in _SUPPORTED_PROVIDERS, (
                f"Unsupported {llm_provider}.\nSupported llm providers are: "
                + ", ".join(_SUPPORTED_PROVIDERS)
            )
            return llm_provider, llm_model
        except ValueError:
            raise ValueError(
                "Set SMART_LLM or FAST_LLM = '<llm_provider>:<llm_model>' "
                "Eg 'openai:gpt-4o-mini'"
            )

    @staticmethod
    def parse_reasoning_effort(reasoning_effort_str: str | None) -> str | None:
        """Parse reasoning effort string into (reasoning_effort)."""
        if reasoning_effort_str is None:
            return ReasoningEfforts.Medium.value
        if reasoning_effort_str not in [effort.value for effort in ReasoningEfforts]:
            raise ValueError(f"Invalid reasoning effort: {reasoning_effort_str}. Valid options are: {', '.join([effort.value for effort in ReasoningEfforts])}")
        return reasoning_effort_str

    @staticmethod
    def parse_embedding(embedding_str: str | None) -> tuple[str | None, str | None]:
        """Parse embedding string into (embedding_provider, embedding_model)."""
        from gpt_researcher.memory.embeddings import _SUPPORTED_PROVIDERS

        if embedding_str is None:
            return None, None
        try:
            embedding_provider, embedding_model = embedding_str.split(":", 1)
            assert embedding_provider in _SUPPORTED_PROVIDERS, (
                f"Unsupported {embedding_provider}.\nSupported embedding providers are: "
                + ", ".join(_SUPPORTED_PROVIDERS)
            )
            return embedding_provider, embedding_model
        except ValueError:
            raise ValueError(
                "Set EMBEDDING = '<embedding_provider>:<embedding_model>' "
                "Eg 'openai:text-embedding-3-large'"
            )

    def validate_doc_path(self):
        """Ensure that the folder exists at the doc path"""
        os.makedirs(self.doc_path, exist_ok=True)

    @staticmethod
    def convert_env_value(key: str, env_value: str, type_hint: Type) -> Any:
        """Convert environment variable to the appropriate type based on the type hint."""
        origin = get_origin(type_hint)
        args = get_args(type_hint)

        if origin is Union:
            # Handle Union types (e.g., Union[str, None])
            for arg in args:
                if arg is type(None):
                    if env_value.lower() in ("none", "null", ""):
                        return None
                else:
                    try:
                        return Config.convert_env_value(key, env_value, arg)
                    except ValueError:
                        continue
            raise ValueError(f"Cannot convert {env_value} to any of {args}")

        if type_hint is bool:
            return env_value.lower() in ("true", "1", "yes", "on")
        elif type_hint is int:
            return int(env_value)
        elif type_hint is float:
            return float(env_value)
        elif type_hint in (str, Any):
            return env_value
        elif origin is list or origin is List:
            return json.loads(env_value)
        elif type_hint is dict:
            return json.loads(env_value)
        else:
            raise ValueError(f"Unsupported type {type_hint} for key {key}")


    def set_verbose(self, verbose: bool) -> None:
        """Set the verbosity level."""
        self.llm_kwargs["verbose"] = verbose

    def get_mcp_server_config(self, name: str) -> dict:
        """
        Get the configuration for an MCP server.
        
        Args:
            name (str): The name of the MCP server to get the config for.
                
        Returns:
            dict: The server configuration, or an empty dict if the server is not found.
        """
        if not name or not self.mcp_servers:
            return {}
        
        for server in self.mcp_servers:
            if isinstance(server, dict) and server.get("name") == name:
                return server
            
        return {}
