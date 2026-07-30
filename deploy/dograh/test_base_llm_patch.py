import unittest

from pipecat.services.openai.base_llm import parse_function_arguments


class ParseFunctionArgumentsTests(unittest.TestCase):
    def test_accepts_duplicate_empty_json_objects_from_sarvam_tool_stream(self):
        self.assertEqual(parse_function_arguments("{}{}"), {})

    def test_preserves_regular_json_arguments(self):
        self.assertEqual(parse_function_arguments('{"amount":500}'), {"amount": 500})


if __name__ == "__main__":
    unittest.main()
