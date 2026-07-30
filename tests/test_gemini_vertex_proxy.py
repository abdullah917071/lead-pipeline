import unittest

from app.services.gemini_vertex_proxy import openai_request_to_vertex, vertex_response_to_openai


class GeminiVertexProxyTests(unittest.TestCase):
    def test_converts_openai_messages_and_function_tools_to_vertex_payload(self):
        payload = openai_request_to_vertex({
            "model": "gemini-2.5-flash-lite",
            "messages": [
                {"role": "system", "content": "Speak only Hindi."},
                {"role": "user", "content": "Customer said yes."},
            ],
            "tools": [{"type": "function", "function": {
                "name": "mark_interested",
                "description": "Mark interest.",
                "parameters": {"type": "object", "properties": {}}
            }}],
            "tool_choice": "required",
        })
        self.assertEqual(payload["systemInstruction"]["parts"][0]["text"], "Speak only Hindi.")
        self.assertEqual(payload["contents"][0]["role"], "user")
        self.assertEqual(payload["contents"][0]["parts"][0]["text"], "Customer said yes.")
        self.assertEqual(payload["tools"][0]["functionDeclarations"][0]["name"], "mark_interested")
        self.assertEqual(payload["toolConfig"]["functionCallingConfig"]["mode"], "ANY")

    def test_converts_vertex_function_call_to_openai_tool_call(self):
        response = vertex_response_to_openai({
            "candidates": [{"content": {"parts": [
                {"functionCall": {"name": "mark_interested", "args": {"lead_id": "abc"}}}
            ]}}]
        }, "gemini-2.5-flash-lite")
        tool_call = response["choices"][0]["message"]["tool_calls"][0]
        self.assertEqual(tool_call["function"]["name"], "mark_interested")
        self.assertEqual(tool_call["function"]["arguments"], '{"lead_id":"abc"}')


if __name__ == "__main__":
    unittest.main()
