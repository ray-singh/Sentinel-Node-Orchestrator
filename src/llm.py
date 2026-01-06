"""LLM integration module with cost tracking."""

import logging
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

from .config import settings
from .state import LLMCallMetadata

logger = logging.getLogger(__name__)


# Pricing per 1M tokens (as of 2024)
PRICING = {
    "gpt-4-turbo-preview": {"input": 10.0, "output": 30.0},
    "gpt-4": {"input": 30.0, "output": 60.0},
    "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
    "gpt-4o": {"input": 5.0, "output": 15.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
}


class LLMClient:
    """
    LLM client with cost tracking and retry logic.
    
    Supports OpenAI API with automatic token counting and cost calculation.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "gpt-4o-mini",
        max_retries: int = 3,
    ):
        """
        Initialize LLM client.
        
        Args:
            api_key: OpenAI API key
            default_model: Default model to use
            max_retries: Maximum number of retries on failure
        """
        self.api_key = api_key or settings.openai_api_key
        self.default_model = default_model
        self.max_retries = max_retries
        
        # Lazy import to avoid requiring openai if not used
        self._client = None
    
    def _get_client(self):
        """Lazy initialize OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "openai package not installed. Install with: pip install openai"
                )
        return self._client
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> tuple[str, LLMCallMetadata]:
        """
        Call OpenAI chat completion API with cost tracking.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name (overrides default)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional API parameters
            
        Returns:
            Tuple of (response_text, metadata)
        """
        model = model or self.default_model
        client = self._get_client()
        
        start_time = time.time()
        
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            
            latency_ms = (time.time() - start_time) * 1000
            
            # Extract response
            content = response.choices[0].message.content
            
            # Get token usage
            usage = response.usage
            prompt_tokens = usage.prompt_tokens
            completion_tokens = usage.completion_tokens
            total_tokens = usage.total_tokens
            
            # Calculate cost
            cost_usd = self._calculate_cost(
                model,
                prompt_tokens,
                completion_tokens
            )
            
            # Create metadata
            metadata = LLMCallMetadata(
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
            )
            
            logger.info(
                f"LLM call: {model}, tokens={total_tokens}, "
                f"cost=${cost_usd:.4f}, latency={latency_ms:.0f}ms"
            )
            
            return content, metadata
        
        except Exception as e:
            logger.error(f"LLM call failed: {e}", exc_info=True)
            raise
    
    async def simple_prompt(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> tuple[str, LLMCallMetadata]:
        """
        Simple single-turn prompt helper.
        
        Args:
            prompt: User prompt
            system: Optional system message
            model: Model name
            **kwargs: Additional parameters
            
        Returns:
            Tuple of (response_text, metadata)
        """
        messages = []
        
        if system:
            messages.append({"role": "system", "content": system})
        
        messages.append({"role": "user", "content": prompt})
        
        return await self.chat_completion(messages, model=model, **kwargs)
    
    def _calculate_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int
    ) -> float:
        """
        Calculate cost for a model based on token usage.
        
        Args:
            model: Model name
            prompt_tokens: Number of input tokens
            completion_tokens: Number of output tokens
            
        Returns:
            Cost in USD
        """
        # Get pricing for this model
        pricing = PRICING.get(model)
        
        if not pricing:
            logger.warning(f"No pricing info for model {model}, using gpt-4o-mini pricing")
            pricing = PRICING["gpt-4o-mini"]
        
        # Calculate cost per million tokens
        input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]
        
        return input_cost + output_cost
    
    async def embeddings(
        self,
        texts: List[str],
        model: str = "text-embedding-3-small",
    ) -> tuple[List[List[float]], LLMCallMetadata]:
        """
        Generate embeddings for text.
        
        Args:
            texts: List of texts to embed
            model: Embedding model name
            
        Returns:
            Tuple of (embeddings, metadata)
        """
        client = self._get_client()
        
        start_time = time.time()
        
        try:
            response = await client.embeddings.create(
                model=model,
                input=texts,
            )
            
            latency_ms = (time.time() - start_time) * 1000
            
            embeddings = [item.embedding for item in response.data]
            
            # Embeddings use different pricing
            total_tokens = response.usage.total_tokens
            cost_usd = (total_tokens / 1_000_000) * 0.02  # $0.02 per 1M tokens
            
            metadata = LLMCallMetadata(
                model=model,
                prompt_tokens=total_tokens,
                completion_tokens=0,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
            )
            
            logger.info(
                f"Embeddings: {model}, {len(texts)} texts, "
                f"tokens={total_tokens}, cost=${cost_usd:.4f}"
            )
            
            return embeddings, metadata
        
        except Exception as e:
            logger.error(f"Embeddings call failed: {e}", exc_info=True)
            raise


# Global LLM client instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create global LLM client instance."""
    global _llm_client
    
    if _llm_client is None:
        _llm_client = LLMClient()
    
    return _llm_client
