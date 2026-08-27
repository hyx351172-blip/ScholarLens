"""Strict OpenAI-compatible embedding API client utilities."""

from __future__ import annotations

import math
from typing import Any, Dict, List

import requests


class EmbeddingAPIError(RuntimeError):
    """Raised when embeddings cannot be generated safely."""


def _parse_embeddings(payload: Dict[str, Any], expected_count: int) -> List[List[float]]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise EmbeddingAPIError("Embedding API response is missing a data list")

    if len(data) != expected_count:
        raise EmbeddingAPIError(
            f"Embedding API returned {len(data)} vectors; expected {expected_count}"
        )

    # OpenAI-compatible providers may return batches out of order. Respect the
    # explicit index when every item provides one.
    if data and all(isinstance(item, dict) and isinstance(item.get("index"), int) for item in data):
        data = sorted(data, key=lambda item: item["index"])
        indexes = [item["index"] for item in data]
        if indexes != list(range(expected_count)):
            raise EmbeddingAPIError(f"Embedding API returned invalid indexes: {indexes}")

    embeddings: List[List[float]] = []
    dimension = None
    for position, item in enumerate(data):
        if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
            raise EmbeddingAPIError(f"Embedding #{position} is missing its vector")

        vector = item["embedding"]
        if not vector or not all(
            isinstance(value, (int, float)) and math.isfinite(value) for value in vector
        ):
            raise EmbeddingAPIError(f"Embedding #{position} contains invalid values")

        if dimension is None:
            dimension = len(vector)
        elif len(vector) != dimension:
            raise EmbeddingAPIError(
                f"Embedding #{position} has dimension {len(vector)}; expected {dimension}"
            )
        embeddings.append(vector)

    return embeddings


def request_embeddings(
    api_url: str,
    api_key: str,
    model_name: str,
    texts: List[str],
    timeout: int = 60,
) -> List[List[float]]:
    if not api_url or not api_key or not model_name:
        raise EmbeddingAPIError("Embedding API URL, key, and model name must be configured")
    if not texts:
        return []
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise EmbeddingAPIError("Embedding input contains empty or non-text content")

    try:
        response = requests.post(
            api_url,
            json={"model": model_name, "input": texts},
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise EmbeddingAPIError(f"Embedding API request failed: {exc}") from exc

    if response.status_code != 200:
        # Do not include the response body: providers sometimes echo request
        # details, and API errors must never leak credentials into logs.
        raise EmbeddingAPIError(f"Embedding API returned HTTP {response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise EmbeddingAPIError("Embedding API returned invalid JSON") from exc

    return _parse_embeddings(payload, expected_count=len(texts))
