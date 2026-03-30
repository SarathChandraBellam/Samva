"""Core configuration for Samva voice agent."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

from .audio import AudioConfig
from .models import ModelConfig

load_dotenv()


@dataclass
class Config:
    """
    Top-level configuration for Samva.

    Flat fields remain for direct access and mutation (CLI, env overrides).
    Compose ModelConfig / AudioConfig via ``from_parts`` for structured setup.

    Environment variables
    ---------------------
    GEMINI_API_KEY          Required. Gemini API key.
    SAMVA_LIVE_MODEL        Live streaming model (default: gemini-3.1-flash-live-preview)
    SAMVA_SEARCH_MODEL      RAG search model (default: gemini-3-flash-preview)
    SAMVA_KB_STORE_NAME     Knowledge base store name (default: samva-knowledge-base)
    SAMVA_VOICE             Agent voice name (default: Kore)
    SAMVA_SYSTEM_PROMPT     Full system prompt override
    SAMVA_PROMPT_TEMPLATE   Prompt template name from prompts/ folder
    SAMVA_INPUT_SAMPLE_RATE PCM input rate (default: 16000)
    SAMVA_OUTPUT_SAMPLE_RATE PCM output rate (default: 24000)
    SAMVA_CHUNK_SIZE        PyAudio frames per buffer (default: 1024)
    """

    # --- Auth ---
    api_key: str = field(
        default_factory=lambda: os.environ.get("GEMINI_API_KEY", "")
    )

    # --- Models ---
    live_model: str = field(
        default_factory=lambda: os.environ.get(
            "SAMVA_LIVE_MODEL", "gemini-3.1-flash-live-preview"
        )
    )
    search_model: str = field(
        default_factory=lambda: os.environ.get(
            "SAMVA_SEARCH_MODEL", "gemini-1.5-flash"
        )
    )

    # --- Knowledge base ---
    kb_store_name: str = field(
        default_factory=lambda: os.environ.get(
            "SAMVA_KB_STORE_NAME", "samva-knowledge-base"
        )
    )
    enable_kb: bool = field(
        default_factory=lambda: os.environ.get("SAMVA_ENABLE_KB", "true").lower()
        not in ("false", "0", "no")
    )

    # --- Voice ---
    voice_name: str = field(
        default_factory=lambda: os.environ.get("SAMVA_VOICE", "Kore")
    )

    # --- Audio ---
    input_sample_rate: int = field(
        default_factory=lambda: int(os.environ.get("SAMVA_INPUT_SAMPLE_RATE", "16000"))
    )
    output_sample_rate: int = field(
        default_factory=lambda: int(os.environ.get("SAMVA_OUTPUT_SAMPLE_RATE", "24000"))
    )
    channels: int = 1
    chunk_size: int = field(
        default_factory=lambda: int(os.environ.get("SAMVA_CHUNK_SIZE", "1024"))
    )

    # --- Prompt ---
    system_prompt: str = field(
        default_factory=lambda: os.environ.get("SAMVA_SYSTEM_PROMPT", "")
    )
    # Name of a .txt template in samva/prompts/ (used when system_prompt is empty)
    prompt_template: str = field(
        default_factory=lambda: os.environ.get("SAMVA_PROMPT_TEMPLATE", "default")
    )

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_parts(
        cls,
        models: ModelConfig,
        audio: AudioConfig,
        api_key: str = "",
        kb_store_name: str = "samva-knowledge-base",
        system_prompt: str = "",
        prompt_template: str = "default",
    ) -> "Config":
        """Construct Config from sub-config objects."""
        return cls(
            api_key=api_key or os.environ.get("GEMINI_API_KEY", ""),
            live_model=models.live_model,
            search_model=models.search_model,
            voice_name=models.voice_name,
            input_sample_rate=audio.input_sample_rate,
            output_sample_rate=audio.output_sample_rate,
            channels=audio.channels,
            chunk_size=audio.chunk_size,
            kb_store_name=kb_store_name,
            system_prompt=system_prompt,
            prompt_template=prompt_template,
        )

    def to_model_config(self) -> ModelConfig:
        """Return a ModelConfig view of the current settings."""
        return ModelConfig(
            live_model=self.live_model,
            search_model=self.search_model,
            voice_name=self.voice_name,
        )

    def to_audio_config(self) -> AudioConfig:
        """Return an AudioConfig view of the current settings."""
        return AudioConfig(
            input_sample_rate=self.input_sample_rate,
            output_sample_rate=self.output_sample_rate,
            channels=self.channels,
            chunk_size=self.chunk_size,
        )

    # ------------------------------------------------------------------
    # Prompt resolution
    # ------------------------------------------------------------------

    def resolve_prompt(self) -> str:
        """Return the effective system prompt, loading from template if needed."""
        if self.system_prompt:
            return self.system_prompt
        from ..prompts import load_prompt
        return load_prompt(self.prompt_template)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> None:
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. "
                "Add it to your .env file or export it as an environment variable."
            )
