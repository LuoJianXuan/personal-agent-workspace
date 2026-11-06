import os
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.observability import MAX_OBS_TEXT, _safe_llm_result


class ObservabilityTests(unittest.TestCase):
    def test_model_output_is_redacted_and_bounded_without_mutating_original(self):
        secret = "sk-observability-secret-value"
        content = secret + ("x" * (MAX_OBS_TEXT + 100))
        source = LLMResult(generations=[[ChatGeneration(message=AIMessage(content=content))]])
        with patch.dict(os.environ, {"TEST_API_KEY": secret}):
            safe = _safe_llm_result(source)
        observed = safe.generations[0][0].message.content
        self.assertNotIn(secret, observed)
        self.assertIn("[REDACTED]", observed)
        self.assertLessEqual(len(observed), MAX_OBS_TEXT + len("…[TRUNCATED]"))
        self.assertIn(secret, source.generations[0][0].message.content)


if __name__ == "__main__":
    unittest.main()
