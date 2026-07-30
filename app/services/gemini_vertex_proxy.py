"""OpenAI-chat to Vertex Gemini request/response translation."""

import json
import time
import uuid
from typing import Any

import httpx


def _vertex_schema(value: Any) -> Any:
    """Convert OpenAI's lowercase JSON schema type names for Vertex."""
    if isinstance(value, list):
        return [_vertex_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    converted = {}
    for key, item in value.items():
        if key == "type" and isinstance(item, str):
            converted[key] = item.upper()
        else:
            converted[key] = _vertex_schema(item)
    return converted


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            part.get("text", "") for part in content
            if isinstance(part, dict) and part.get("type", "text") == "text"
        )
    return ""


def openai_request_to_vertex(request: dict[str, Any]) -> dict[str, Any]:
    """Translate the subset of OpenAI Chat Completions Dograh uses."""
    system_parts: list[dict[str, str]] = []
    contents: list[dict[str, Any]] = []
    for message in request.get("messages", []):
        role = message.get("role")
        text = _content_text(message.get("content"))
        if role == "system":
            if text:
                system_parts.append({"text": text})
            continue
        if role == "assistant":
            parts: list[dict[str, Any]] = []
            if text:
                parts.append({"text": text})
            for call in message.get("tool_calls") or []:
                function = call.get("function", {})
                try:
                    args = json.loads(function.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                parts.append({"functionCall": {"name": function.get("name", ""), "args": args}})
            if parts:
                contents.append({"role": "model", "parts": parts})
            continue
        if role == "tool":
            try:
                response = json.loads(text) if text else {"result": "ok"}
            except json.JSONDecodeError:
                response = {"result": text}
            contents.append({"role": "user", "parts": [{"functionResponse": {
                "name": message.get("name", "tool"), "response": response
            }}]})
            continue
        if text:
            contents.append({"role": "user", "parts": [{"text": text}]})

    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": request.get("temperature", 0.1),
            "maxOutputTokens": request.get("max_tokens", request.get("max_completion_tokens", 512)),
        },
    }
    if system_parts:
        payload["systemInstruction"] = {"parts": system_parts}

    declarations = []
    for tool in request.get("tools") or []:
        function = tool.get("function", {})
        if function.get("name"):
            declarations.append({
                "name": function["name"],
                "description": function.get("description", ""),
                "parameters": _vertex_schema(function.get("parameters", {"type": "object", "properties": {}})),
            })
    if declarations:
        payload["tools"] = [{"functionDeclarations": declarations}]
        choice = request.get("tool_choice")
        if choice == "required":
            payload["toolConfig"] = {"functionCallingConfig": {"mode": "ANY"}}
        elif isinstance(choice, dict):
            name = choice.get("function", {}).get("name")
            if name:
                payload["toolConfig"] = {"functionCallingConfig": {
                    "mode": "ANY", "allowedFunctionNames": [name]
                }}
    return payload


def vertex_response_to_openai(response: dict[str, Any], model: str) -> dict[str, Any]:
    """Translate a Vertex Gemini response into an OpenAI chat completion."""
    candidate = (response.get("candidates") or [{}])[0]
    parts = candidate.get("content", {}).get("parts", [])
    content = "".join(part.get("text", "") for part in parts if "text" in part) or None
    tool_calls = []
    for index, part in enumerate(parts):
        call = part.get("functionCall")
        if call:
            tool_calls.append({
                "id": f"call_{uuid.uuid4().hex[:24]}",
                "type": "function",
                "function": {
                    "name": call.get("name", ""),
                    "arguments": json.dumps(call.get("args", {}), separators=(",", ":")),
                },
            })
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": "tool_calls" if tool_calls else "stop",
        }],
        "usage": response.get("usageMetadata", {}),
    }


async def complete_via_vertex(
    request: dict[str, Any], *, api_key: str, project_id: str, location: str
) -> dict[str, Any]:
    """Call Gemini through the Vertex endpoint that accepts Agent Platform API keys."""
    model = request.get("model") or "gemini-2.5-flash-lite"
    url = (
        f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/"
        f"locations/{location}/publishers/google/models/{model}:generateContent"
    )
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            url,
            params={"key": api_key},
            json=openai_request_to_vertex(request),
        )
    response.raise_for_status()
    return vertex_response_to_openai(response.json(), model)
