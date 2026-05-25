"""Load LLM configuration from YAML (Section 6.2)."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None


@dataclass
class LLMConfig:
    provider: str  # "openai" | "anthropic"
    api_key: str
    model: str
    temperature: float = 0.2
    max_output_tokens: int = 4096

    @property
    def openai(self) -> dict[str, Any]:
        return {"api_key": self.api_key, "model": self.model}

    @property
    def anthropic(self) -> dict[str, Any]:
        return {"api_key": self.api_key, "model": self.model}


def load_config(path: str | Path) -> LLMConfig:
    """Load config from YAML file (Figure 6 format)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    if yaml is None:
        raise ImportError("PyYAML is required; install with: pip install pyyaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    provider = (data.get("provider") or "openai").lower()
    if provider == "openai":
        section = data.get("openai") or {}
        api_key = section.get("api_key", "")
        model = section.get("model", "gpt-4o-mini")
    else:
        section = data.get("anthropic") or {}
        api_key = section.get("api_key", "")
        model = section.get("model", "claude-haiku-4-5")
    gen = data.get("generation") or {}
    return LLMConfig(
        provider=provider,
        api_key=api_key,
        model=model,
        temperature=float(gen.get("temperature", 0.2)),
        max_output_tokens=int(gen.get("max_output_tokens", 4096)),
    )
