import importlib.util
import pathlib
import unittest
from unittest.mock import Mock, patch


MODULE_PATH = (
    pathlib.Path(__file__).parents[1]
    / "backend"
    / "Database"
    / "milvus_server"
    / "embedding_client.py"
)
SPEC = importlib.util.spec_from_file_location("embedding_client", MODULE_PATH)
embedding_client = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(embedding_client)


class EmbeddingClientTests(unittest.TestCase):
    def test_http_error_fails_instead_of_generating_random_vectors(self):
        response = Mock(status_code=429)
        with patch.object(embedding_client.requests, "post", return_value=response):
            with self.assertRaisesRegex(embedding_client.EmbeddingAPIError, "HTTP 429"):
                embedding_client.request_embeddings("https://example.test", "secret", "model", ["text"])

    def test_batch_is_sorted_by_provider_index(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "data": [
                {"index": 1, "embedding": [0.0, 1.0]},
                {"index": 0, "embedding": [1.0, 0.0]},
            ]
        }
        with patch.object(embedding_client.requests, "post", return_value=response):
            result = embedding_client.request_embeddings(
                "https://example.test", "secret", "model", ["first", "second"]
            )
        self.assertEqual(result, [[1.0, 0.0], [0.0, 1.0]])

    def test_wrong_vector_count_is_rejected(self):
        response = Mock(status_code=200)
        response.json.return_value = {"data": [{"index": 0, "embedding": [1.0, 0.0]}]}
        with patch.object(embedding_client.requests, "post", return_value=response):
            with self.assertRaisesRegex(embedding_client.EmbeddingAPIError, "expected 2"):
                embedding_client.request_embeddings(
                    "https://example.test", "secret", "model", ["first", "second"]
                )

    def test_inconsistent_dimensions_are_rejected(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "data": [
                {"index": 0, "embedding": [1.0, 0.0]},
                {"index": 1, "embedding": [1.0]},
            ]
        }
        with patch.object(embedding_client.requests, "post", return_value=response):
            with self.assertRaisesRegex(embedding_client.EmbeddingAPIError, "dimension"):
                embedding_client.request_embeddings(
                    "https://example.test", "secret", "model", ["first", "second"]
                )


if __name__ == "__main__":
    unittest.main()
