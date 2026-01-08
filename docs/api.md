# API Client Reference

This document provides detailed reference documentation for the CogSol API client module (`cogsol/core/api.py`).

## Table of Contents

- [Overview](#overview)
- [CogSolClient](#cogsolclient)
- [API Endpoints](#api-endpoints)
- [Error Handling](#error-handling)
- [Usage Examples](#usage-examples)
- [API Payloads](#api-payloads)

---

## Overview

The API client module provides a lightweight HTTP client for communicating with the CogSol REST API. It uses only Python's standard library (`urllib`) with no external dependencies.

### Features

- **No Dependencies**: Uses only `urllib.request`
- **JSON-Based**: Automatic JSON encoding/decoding
- **Token Authentication**: Supports `x-api-key` header
- **CRUD Operations**: Full create, read, update, delete support
- **Type-Safe**: Proper error handling and validation

---

## CogSolClient

The main client class for API communication.

### Class Definition

```python
from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class CogSolClient:
    base_url: str
    token: Optional[str] = None
```

### Constructor Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base_url` | `str` | Yes | Base URL for the CogSol API (e.g., `https://api.cogsol.ai/cognitive/`) |
| `token` | `str` | No | API authentication token |

### Basic Usage

```python
from cogsol.core.api import CogSolClient

# Without authentication
client = CogSolClient(base_url="https://api.cogsol.ai/cognitive/")

# With authentication
client = CogSolClient(
    base_url="https://api.cogsol.ai/cognitive/",
    token="sk-your-api-key"
)
```

---

## Core Methods

### request()

Low-level HTTP request method.

```python
def request(
    self,
    method: str,
    path: str,
    payload: Optional[dict[str, Any]] = None
) -> Any
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `method` | `str` | HTTP method (`GET`, `POST`, `PUT`, `DELETE`) |
| `path` | `str` | API path (e.g., `/assistants/`) or full URL |
| `payload` | `dict` | Request body (JSON-encoded) |

#### Returns

Parsed JSON response or `None` for empty responses.

#### Example

```python
# GET request
assistants = client.request("GET", "/assistants/")

# POST request
new_assistant = client.request("POST", "/assistants/", {
    "description": "My Assistant",
    "system_prompt": "You are helpful."
})

# PUT request
client.request("PUT", "/assistants/42/", {"temperature": 0.5})

# DELETE request
client.request("DELETE", "/assistants/42/")
```

---

## Assistant Operations

### upsert_assistant()

Create or update an assistant.

```python
def upsert_assistant(
    self,
    *,
    remote_id: Optional[int],
    payload: dict[str, Any]
) -> int
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `remote_id` | `int` | Existing assistant ID (for update) or `None` (for create) |
| `payload` | `dict` | Assistant configuration |

#### Returns

The assistant ID (created or updated).

#### Example

```python
# Create new assistant
assistant_id = client.upsert_assistant(
    remote_id=None,
    payload={
        "description": "Sales Assistant",
        "system_prompt": "You are a sales expert.",
        "temperature": 0.3,
    }
)

# Update existing assistant
client.upsert_assistant(
    remote_id=42,
    payload={"temperature": 0.5}
)
```

### get_assistant()

Retrieve an assistant by ID.

```python
def get_assistant(self, assistant_id: int) -> Any
```

#### Example

```python
assistant = client.get_assistant(42)
print(assistant["description"])
print(assistant["system_prompt"])
```

### delete_assistant()

Delete an assistant.

```python
def delete_assistant(self, assistant_id: int) -> None
```

#### Example

```python
client.delete_assistant(42)
```

---

## Tool/Script Operations

### upsert_script()

Create or update a script tool.

```python
def upsert_script(
    self,
    *,
    remote_id: Optional[int],
    payload: dict[str, Any]
) -> int
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `remote_id` | `int` | Existing script ID (for update) or `None` (for create) |
| `payload` | `dict` | Script configuration |

#### Returns

The script ID (created or updated).

#### Example

```python
script_id = client.upsert_script(
    remote_id=None,
    payload={
        "name": "SearchTool",
        "description": "Search the knowledge base",
        "parameters": [
            {"name": "query", "type": "string", "required": True}
        ],
        "code": "response = search(params.get('query'))"
    }
)
```

### get_script()

Retrieve a script by ID.

```python
def get_script(self, script_id: int) -> Any
```

### delete_script()

Delete a script.

```python
def delete_script(self, script_id: int) -> None
```

---

## FAQ Operations

### upsert_common_question()

Create or update a FAQ (common question).

```python
def upsert_common_question(
    self,
    *,
    assistant_id: int,
    remote_id: Optional[int],
    payload: dict[str, Any]
) -> int
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `assistant_id` | `int` | Parent assistant ID |
| `remote_id` | `int` | Existing FAQ ID or `None` |
| `payload` | `dict` | FAQ data |

#### Example

```python
faq_id = client.upsert_common_question(
    assistant_id=42,
    remote_id=None,
    payload={
        "name": "Pricing Question",
        "content": "We offer three tiers: Basic, Pro, Enterprise."
    }
)
```

### list_common_questions()

List all FAQs for an assistant.

```python
def list_common_questions(self, assistant_id: int) -> Any
```

### delete_common_question()

Delete a FAQ.

```python
def delete_common_question(self, assistant_id: int, faq_id: int) -> None
```

---

## Fixed Response Operations

### upsert_fixed_response()

Create or update a fixed response.

```python
def upsert_fixed_response(
    self,
    *,
    assistant_id: int,
    remote_id: Optional[int],
    payload: dict[str, Any]
) -> int
```

#### Example

```python
fixed_id = client.upsert_fixed_response(
    assistant_id=42,
    remote_id=None,
    payload={
        "name": "Goodbye",
        "topic": "farewell",
        "content": "Thank you for chatting!"
    }
)
```

### list_fixed_responses()

List all fixed responses for an assistant.

```python
def list_fixed_responses(self, assistant_id: int) -> Any
```

### delete_fixed_response()

Delete a fixed response.

```python
def delete_fixed_response(self, assistant_id: int, fixed_id: int) -> None
```

---

## Lesson Operations

### upsert_lesson()

Create or update a lesson.

```python
def upsert_lesson(
    self,
    *,
    assistant_id: int,
    remote_id: Optional[int],
    payload: dict[str, Any]
) -> int
```

#### Example

```python
lesson_id = client.upsert_lesson(
    assistant_id=42,
    remote_id=None,
    payload={
        "name": "Tone Guide",
        "content": "Always be professional but friendly.",
        "context_of_application": "general"
    }
)
```

### list_lessons()

List all lessons for an assistant.

```python
def list_lessons(self, assistant_id: int) -> Any
```

### delete_lesson()

Delete a lesson.

```python
def delete_lesson(self, assistant_id: int, lesson_id: int) -> None
```

---

## Chat Operations

### create_chat()

Create a new chat session with an assistant.

```python
def create_chat(
    self,
    assistant_id: int,
    message: Optional[str] = None
) -> Any
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `assistant_id` | `int` | Assistant to chat with |
| `message` | `str` | Optional initial message |

#### Returns

Chat object including `id` and `messages`.

#### Example

```python
# Create chat without initial message
chat = client.create_chat(42)
chat_id = chat["id"]

# Create chat with initial message
chat = client.create_chat(42, message="Hello, I need help!")
```

### send_message()

Send a message to an existing chat.

```python
def send_message(self, chat_id: int, message: str) -> Any
```

#### Returns

Updated chat object with new messages.

#### Example

```python
response = client.send_message(chat_id=123, message="What are your hours?")
messages = response.get("messages", [])
```

### get_chat()

Retrieve a chat by ID.

```python
def get_chat(self, chat_id: int) -> Any
```

#### Example

```python
chat = client.get_chat(123)
for msg in chat.get("messages", []):
    print(f"{msg['role']}: {msg['content']}")
```

---

## Error Handling

### CogSolAPIError

Custom exception for API errors.

```python
class CogSolAPIError(RuntimeError):
    pass
```

### Error Types

| HTTP Code | Meaning | Common Causes |
|-----------|---------|---------------|
| 400 | Bad Request | Invalid payload data |
| 401 | Unauthorized | Missing or invalid token |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource doesn't exist |
| 500 | Server Error | API internal error |

### Handling Errors

```python
from cogsol.core.api import CogSolClient, CogSolAPIError

client = CogSolClient(base_url="https://api.cogsol.ai/cognitive/", token="...")

try:
    assistant = client.get_assistant(9999)
except CogSolAPIError as e:
    print(f"API Error: {e}")
    # Output: API Error: 404 Not Found: {"detail": "Not found."}
```

### Connection Errors

```python
try:
    client = CogSolClient(base_url="https://invalid.example.com")
    client.get_assistant(1)
except CogSolAPIError as e:
    print(f"Connection Error: {e}")
    # Output: Connection Error: Connection error: [Errno ...]
```

---

## Usage Examples

### Complete Workflow

```python
from cogsol.core.api import CogSolClient

# Initialize client
client = CogSolClient(
    base_url="https://api.cogsol.ai/cognitive/",
    token="sk-your-token"
)

# Create a tool
tool_id = client.upsert_script(
    remote_id=None,
    payload={
        "name": "WeatherTool",
        "description": "Get weather information",
        "parameters": [
            {"name": "city", "type": "string", "required": True}
        ],
        "code": "response = get_weather(params.get('city'))"
    }
)
print(f"Created tool: {tool_id}")

# Create an assistant using the tool
assistant_id = client.upsert_assistant(
    remote_id=None,
    payload={
        "description": "Weather Assistant",
        "system_prompt": "You help users check the weather.",
        "temperature": 0.3,
        "tools": [tool_id]
    }
)
print(f"Created assistant: {assistant_id}")

# Add a FAQ
faq_id = client.upsert_common_question(
    assistant_id=assistant_id,
    remote_id=None,
    payload={
        "name": "Supported Cities",
        "content": "I can check weather for any major city worldwide."
    }
)

# Start a chat
chat = client.create_chat(assistant_id, "What's the weather in Paris?")
chat_id = chat["id"]

# Get response
chat = client.get_chat(chat_id)
for msg in chat.get("messages", []):
    if msg["role"] == "assistant":
        print(f"Assistant: {msg['content']}")

# Continue conversation
response = client.send_message(chat_id, "And in London?")
```

### Batch Operations

```python
# Create multiple tools
tool_names = ["SearchTool", "CalculatorTool", "TranslateTool"]
tool_ids = {}

for name in tool_names:
    tool_id = client.upsert_script(
        remote_id=None,
        payload={
            "name": name,
            "description": f"{name} description",
            "code": f"response = '{name} result'"
        }
    )
    tool_ids[name] = tool_id

# Create assistant with all tools
assistant_id = client.upsert_assistant(
    remote_id=None,
    payload={
        "description": "Multi-Tool Assistant",
        "tools": list(tool_ids.values())
    }
)
```

---

## API Payloads

### Assistant Payload

```python
{
    # Required
    "description": str,              # Display name
    
    # Optional
    "system_prompt": str,            # System instructions
    "temperature": float,            # 0.0 - 1.0
    "max_responses": int,            # Max conversation turns
    "max_msg_length": int,           # Max user message length
    "max_consecutive_tool_calls": int,
    "initial_message": str,          # First message to user
    "end_message": str,              # Termination message
    "not_info_message": str,         # No-information response
    
    # Features
    "streaming_available": bool,
    "realtime_available": bool,
    "faq_available": bool,
    "fixed_available": bool,
    "lessons_available": bool,
    
    # Generation config
    "generation_config": str,        # "QA", "default", etc.
    "generation_config_pretools": str,
    
    # Appearance
    "logo": str,                     # URL
    "colors": {
        "assistant_name_color": str,
        "primary_color": str,
        "secondary_color": str,
        "border_color": str
    },
    
    # Tools (by ID)
    "tools": list[int],
    "pretools": list[int]
}
```

### Script (Tool) Payload

```python
{
    "name": str,                     # Tool name
    "description": str,              # Tool description
    "parameters": [                  # Parameter definitions
        {
            "name": str,
            "description": str,
            "type": str,             # "string", "integer", "boolean"
            "required": bool
        }
    ],
    "code": str,                     # Python code (API style)
    "show_tool_message": bool,       # Show tool execution to user
    "show_assistant_message": bool,
    "edit_available": bool
}
```

### FAQ Payload

```python
{
    "name": str,                     # Question/identifier
    "content": str,                  # Answer content
    "additional_metadata": dict      # Extra data
}
```

### Fixed Response Payload

```python
{
    "name": str,                     # Identifier
    "topic": str,                    # Topic key
    "content": str,                  # Response content
    "additional_metadata": dict      # Extra data
}
```

### Lesson Payload

```python
{
    "name": str,                     # Lesson name
    "content": str,                  # Lesson content
    "context_of_application": str,   # When to apply
    "additional_metadata": dict      # Extra data
}
```

---

## Internal Methods

### _url()

Build full URL from path.

```python
def _url(self, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
```

### _headers()

Build request headers.

```python
def _headers(self) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if self.token:
        headers["x-api-key"] = f"{self.token}"
    return headers
```

### _ensure_id()

Validate and extract ID from response.

```python
def _ensure_id(self, data: Any, label: str) -> int:
    if not data or "id" not in data:
        raise CogSolAPIError(f"{label} response did not include an id: {data}")
    return int(data["id"])
```
