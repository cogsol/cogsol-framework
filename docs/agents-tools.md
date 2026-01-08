# Agents and Tools Reference

This document provides comprehensive reference documentation for building agents and tools in CogSol.

## Table of Contents

- [Agents](#agents)
  - [BaseAgent](#baseagent)
  - [Agent Attributes](#agent-attributes)
  - [Meta Class](#meta-class)
  - [Generation Configurations](#generation-configurations)
  - [Optimizations](#optimizations)
- [Tools](#tools)
  - [BaseTool](#basetool)
  - [Tool Parameters](#tool-parameters)
  - [Tool Implementation](#tool-implementation)
- [Related Content](#related-content)
  - [BaseFAQ](#basefaq)
  - [BaseFixedResponse](#basefixedresponse)
  - [BaseLesson](#baselesson)
- [Prompts](#prompts)
- [Best Practices](#best-practices)
- [Examples](#examples)

---

## Agents

Agents are the core abstraction in CogSol. They define AI assistants with specific behaviors, tools, and configurations.

### BaseAgent

The base class for all CogSol agents.

**Location:** `cogsol/agents/__init__.py`

```python
from cogsol.agents import BaseAgent

class MyAgent(BaseAgent):
    # Agent configuration here
    pass
```

### Agent Attributes

#### Prompt Configuration

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `system_prompt` | `Prompt` | `None` | Main system instructions |
| `initial_message` | `str` | `None` | First message sent to user |
| `forced_termination_message` | `str` | `None` | Message when conversation ends |
| `no_information_message` | `str` | `None` | Response when agent lacks information |

```python
from cogsol.agents import BaseAgent
from cogsol.prompts import Prompts

class SupportAgent(BaseAgent):
    system_prompt = Prompts.load("support.md")
    initial_message = "Hello! How can I help you today?"
    forced_termination_message = "Thank you for contacting support. Goodbye!"
    no_information_message = "I don't have information on that topic."
```

#### Generation Configuration

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `generation_config` | `genconfigs.*` | `None` | Main generation strategy |
| `pregeneration_config` | `genconfigs.*` | `None` | Pre-tool generation strategy |
| `temperature` | `float` | `None` | LLM temperature (0.0 - 1.0) |

```python
from cogsol.agents import BaseAgent, genconfigs

class QAAgent(BaseAgent):
    generation_config = genconfigs.QA()
    pregeneration_config = genconfigs.FastRetrieval()
    temperature = 0.3
```

#### Tools

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `tools` | `list[BaseTool]` | `[]` | Main tools available to agent |
| `pretools` | `list[BaseTool]` | `[]` | Pre-processing tools |

```python
from cogsol.agents import BaseAgent
from .tools import SearchTool, CalculatorTool

class AssistantAgent(BaseAgent):
    tools = [SearchTool(), CalculatorTool()]
    pretools = [ContextLoader()]
```

#### Limits

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_interactions` | `int` | `None` | Max conversation turns |
| `user_message_length` | `int` | `None` | Max user message characters |
| `consecutive_tool_calls_limit` | `int` | `None` | Max tool calls in sequence |
| `user_interactions_window` | `int` | `None` | Context window for interactions |

```python
class LimitedAgent(BaseAgent):
    max_interactions = 10
    user_message_length = 2048
    consecutive_tool_calls_limit = 5
```

#### Features

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `streaming` | `bool` | `False` | Enable response streaming |
| `realtime` | `bool` | `False` | Enable real-time mode |
| `self_improvement_mode` | `bool` | `False` | Enable self-improvement |
| `token_optimization` | `Any` | `None` | Token optimization strategy |

```python
class StreamingAgent(BaseAgent):
    streaming = True
    realtime = False
```

#### Related Content

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `faqs` | `list[BaseFAQ]` | `[]` | Frequently asked questions |
| `fixed_responses` | `list[BaseFixedResponse]` | `[]` | Predefined responses |
| `lessons` | `list[BaseLesson]` | `[]` | Contextual lessons |

```python
from cogsol.agents import BaseAgent
from .faqs import PricingFAQ, HoursFAQ
from .fixed import GoodbyeFixed
from .lessons import ToneLesson

class ServiceAgent(BaseAgent):
    faqs = [PricingFAQ(), HoursFAQ()]
    fixed_responses = [GoodbyeFixed()]
    lessons = [ToneLesson()]
```

> **Note:** FAQs, fixed responses, and lessons are typically auto-loaded from separate files (`faqs.py`, `fixed.py`, `lessons.py`) in the agent package.

### Meta Class

The `Meta` inner class defines display and styling options.

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Internal agent name |
| `chat_name` | `str` | Display name in chat UI |
| `logo_url` | `str` | URL to agent logo/avatar |
| `assistant_name_color` | `str` | Color for agent name (hex) |
| `primary_color` | `str` | Primary UI color (hex) |
| `secondary_color` | `str` | Secondary UI color (hex) |
| `border_color` | `str` | Border color (hex) |

```python
class BrandedAgent(BaseAgent):
    system_prompt = Prompts.load("branded.md")
    
    class Meta:
        name = "BrandedAgent"
        chat_name = "Acme Support"
        logo_url = "https://example.com/logo.png"
        primary_color = "#007bff"
        secondary_color = "#6c757d"
        border_color = "#dee2e6"
        assistant_name_color = "#ffffff"
```

### Generation Configurations

Available generation strategies in `cogsol.agents.genconfigs`:

#### genconfigs.QA

Optimized for question-answering tasks.

```python
from cogsol.agents import genconfigs

generation_config = genconfigs.QA()
```

#### genconfigs.FastRetrieval

Optimized for quick information retrieval pretools.

```python
generation_config = genconfigs.FastRetrieval()
```

### Optimizations

Token optimization strategies in `cogsol.agents.optimizations`:

```python
from cogsol.agents import optimizations

class OptimizedAgent(BaseAgent):
    token_optimization = optimizations.DescriptionOnly()
```

### Agent Definition Method

The `definition()` classmethod extracts agent configuration for migrations:

```python
@classmethod
def definition(cls) -> dict[str, Any]:
    """Helper used by migration tooling to capture class attributes."""
    return {
        "fields": {...},  # All class attributes
        "meta": {...}     # Meta class attributes
    }
```

---

## Tools

Tools extend agent capabilities with custom functionality.

### BaseTool

The base class for all CogSol tools.

**Location:** `cogsol/tools/__init__.py`

```python
from cogsol.tools import BaseTool

class MyTool(BaseTool):
    description = "My custom tool"
    
    def run(self, chat=None, data=None, secrets=None, log=None, **kwargs):
        # Tool implementation
        return response
```

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | Class name (minus "Tool" suffix) | Tool identifier |
| `description` | `str` | `None` | Tool description for LLM |
| `parameters` | `dict` | `{}` | Parameter definitions |

#### Constructor

```python
def __init__(self, name: Optional[str] = None, description: Optional[str] = None):
    if name:
        self.name = name
    if description:
        self.description = description
    if not getattr(self, "name", None):
        # Derive from class name
        cls_name = self.__class__.__name__
        self.name = cls_name[:-4] if cls_name.endswith("Tool") else cls_name
```

### Tool Parameters

Define parameters using the `@tool_params` decorator:

```python
from cogsol.tools import BaseTool, tool_params

class SearchTool(BaseTool):
    description = "Search the knowledge base"
    
    @tool_params(
        query={
            "description": "Search query string",
            "type": "string",
            "required": True
        },
        limit={
            "description": "Maximum results to return",
            "type": "integer",
            "required": False
        },
        include_metadata={
            "description": "Include metadata in results",
            "type": "boolean",
            "required": False
        }
    )
    def run(self, chat=None, data=None, secrets=None, log=None,
            query: str = "", limit: int = 10, include_metadata: bool = False):
        # Implementation
        pass
```

#### Parameter Schema

```python
{
    "param_name": {
        "description": str,    # Human-readable description
        "type": str,           # "string", "integer", "boolean", "number"
        "required": bool       # True if parameter is required
    }
}
```

#### Alternative: Docstring Parameters

Parameters can also be defined in the docstring:

```python
class SearchTool(BaseTool):
    def run(self, chat=None, data=None, secrets=None, log=None,
            query: str = "", limit: int = 10):
        """
        query: The search query to execute.
        limit: Maximum number of results to return.
        """
        pass
```

### Tool Implementation

#### Run Method Signature

```python
def run(
    self,
    chat=None,      # Chat context object
    data=None,      # LLM call data
    secrets=None,   # Secret configuration
    log=None,       # Logging function
    **kwargs        # Tool-specific parameters
) -> Any:
```

#### Runtime Arguments

| Argument | Type | Description |
|----------|------|-------------|
| `chat` | `object` | Current chat session context |
| `data` | `dict` | dict containing LLM call data |
| `secrets` | `dict` | Secret configuration (API keys, etc.) |
| `log` | `callable` | Logging function |
| `**kwargs` | `Any` | Tool-specific parameters |

#### Return Value

The `run()` method should return the tool's response:

```python
def run(self, chat=None, data=None, secrets=None, log=None, query: str = ""):
    results = self._search(query)
    response = self._format_results(results)
    return response  # String or structured data
```

#### Complete Example

```python
from cogsol.tools import BaseTool, tool_params

class WeatherTool(BaseTool):
    name = "weather"
    description = "Get current weather for a city"
    
    @tool_params(
        city={"description": "City name", "type": "string", "required": True},
        units={"description": "Temperature units", "type": "string", "required": False}
    )
    def run(self, chat=None, data=None, secrets=None, log=None,
            city: str = "", units: str = "celsius"):
        """
        city: Name of the city to get weather for.
        units: Temperature units (celsius or fahrenheit).
        """
        if log:
            log(f"Getting weather for {city}")
        
        # Access secrets if needed
        api_key = secrets.get("WEATHER_API_KEY") if secrets else None
        
        # Tool logic
        weather_data = self._fetch_weather(city, api_key)
        
        if units == "fahrenheit":
            weather_data["temp"] = weather_data["temp"] * 9/5 + 32
        
        response = f"The weather in {city} is {weather_data['temp']}° and {weather_data['condition']}"
        return response
    
    def _fetch_weather(self, city: str, api_key: str) -> dict:
        # Implementation
        return {"temp": 20, "condition": "sunny"}
```

---

## Related Content

### BaseFAQ

Frequently asked questions for agent context.

```python
from cogsol.tools import BaseFAQ

class PricingFAQ(BaseFAQ):
    question = "What are your pricing plans?"
    answer = """We offer three tiers:
    - Basic: $10/month
    - Pro: $25/month  
    - Enterprise: Custom pricing"""
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `question` | `str` | The question text |
| `answer` | `str` | The answer content |

### BaseFixedResponse

Predefined responses for specific triggers.

```python
from cogsol.tools import BaseFixedResponse

class GoodbyeFixed(BaseFixedResponse):
    key = "farewell"
    response = "Thank you for chatting! Have a great day!"

class OutOfScopeFixed(BaseFixedResponse):
    key = "off_topic"
    response = "I specialize in customer support. Let me help you with that instead."
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `key` | `str` | Trigger identifier/topic |
| `response` | `str` | Response content |

### BaseLesson

Contextual lessons that provide guidance.

```python
from cogsol.tools import BaseLesson

class ToneLesson(BaseLesson):
    name = "Professional Tone"
    content = """Always maintain a professional yet friendly tone. 
    Avoid jargon and explain technical terms when necessary."""
    context_of_application = "all_responses"

class EscalationLesson(BaseLesson):
    name = "Escalation Protocol"
    content = "If the user expresses frustration, offer to connect with a human agent."
    context_of_application = "negative_sentiment"
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Lesson identifier |
| `content` | `str` | Lesson content/instructions |
| `context_of_application` | `str` | When to apply (e.g., "general", "negative_sentiment") |

---

## Prompts

The `Prompts` class provides utilities for loading system prompts.

**Location:** `cogsol/prompts.py`

### Prompts.load()

Load a prompt file relative to the agent package.

```python
from cogsol.prompts import Prompts

class MyAgent(BaseAgent):
    system_prompt = Prompts.load("my_prompt.md")
```

#### Resolution Order

1. `<agent_package>/prompts/<filename>`
2. `<app>/prompts/<filename>`
3. Relative to caller's directory

### Prompt Class

The `Prompt` object stores path information:

```python
@dataclass
class Prompt:
    path: str              # Filename or relative path
    base_dir: str | None   # Base directory for resolution
```

### Prompt File Format

Prompts are typically Markdown files:

```markdown
# System Instructions

You are a customer support agent for Acme Corporation.

## Your Responsibilities

- Answer questions about our products
- Help resolve issues
- Escalate complex problems

## Guidelines

1. Always be professional and friendly
2. Provide accurate information
3. If unsure, acknowledge and offer alternatives

## Product Information

[Include relevant product details here]
```

---

## Best Practices

### Agent Design

1. **Single Responsibility**: Each agent should have a focused purpose
2. **Clear System Prompt**: Write detailed, unambiguous instructions
3. **Appropriate Temperature**: Lower for factual, higher for creative
4. **Tool Selection**: Include only necessary tools

```python
# Good: Focused agent
class OrderStatusAgent(BaseAgent):
    system_prompt = Prompts.load("order_status.md")
    tools = [OrderLookupTool(), TrackingTool()]
    temperature = 0.2  # Low for accuracy

# Avoid: Overly broad agent
class EverythingAgent(BaseAgent):
    tools = [Tool1(), Tool2(), Tool3(), ...]  # Too many tools
```

### Tool Design

1. **Clear Names**: Use descriptive, action-oriented names
2. **Detailed Descriptions**: Help the LLM understand when to use the tool
3. **Typed Parameters**: Always specify types and requirements
4. **Error Handling**: Return meaningful error messages

```python
# Good tool design
class CustomerLookupTool(BaseTool):
    description = "Look up a customer by their email address or customer ID to retrieve account details."
    
    @tool_params(
        identifier={"description": "Customer email or ID", "type": "string", "required": True}
    )
    def run(self, chat=None, data=None, secrets=None, log=None, identifier: str = ""):
        if not identifier:
            return "Error: Please provide a customer email or ID."
        
        customer = self._lookup(identifier)
        if not customer:
            return f"No customer found with identifier: {identifier}"
        
        return f"Customer: {customer['name']}, Status: {customer['status']}"
```

### File Organization

```
agents/
├── tools.py                    # Shared/reusable tools
└── customer_support/
    ├── __init__.py
    ├── agent.py                # Agent definition
    ├── faqs.py                 # Domain-specific FAQs
    ├── fixed.py                # Fixed responses
    ├── lessons.py              # Contextual lessons
    ├── tools.py                # Agent-specific tools (optional)
    └── prompts/
        └── customer_support.md # System prompt
```

---

## Examples

### Complete Agent Example

```python
# agents/sales/agent.py

from cogsol.agents import BaseAgent, genconfigs
from cogsol.prompts import Prompts
from ..tools import ProductSearchTool, PricingTool, ScheduleDemoTool

class SalesAgent(BaseAgent):
    # Prompt
    system_prompt = Prompts.load("sales.md")
    
    # Generation
    generation_config = genconfigs.QA()
    temperature = 0.4
    
    # Tools
    tools = [
        ProductSearchTool(),
        PricingTool(),
        ScheduleDemoTool()
    ]
    
    # Limits
    max_interactions = 20
    user_message_length = 1000
    consecutive_tool_calls_limit = 3
    
    # Features
    streaming = True
    
    # Messages
    initial_message = "Hi! I'm your sales assistant. How can I help you today?"
    no_information_message = "I don't have that specific information, but I can connect you with a sales representative."
    
    class Meta:
        name = "SalesAgent"
        chat_name = "Sales Assistant"
        logo_url = "https://example.com/sales-bot.png"
        primary_color = "#28a745"
```

### Complete Tool Example

```python
# agents/tools.py

from cogsol.tools import BaseTool, tool_params
import json

class ProductSearchTool(BaseTool):
    name = "product_search"
    description = "Search the product catalog by name, category, or keywords. Returns matching products with prices and availability."
    
    @tool_params(
        query={"description": "Search query (product name, category, or keywords)", "type": "string", "required": True},
        category={"description": "Filter by category", "type": "string", "required": False},
        max_results={"description": "Maximum results (1-20)", "type": "integer", "required": False}
    )
    def run(self, chat=None, data=None, secrets=None, log=None,
            query: str = "", category: str = None, max_results: int = 5):
        """
        query: Search query for products.
        category: Optional category filter.
        max_results: Max number of products to return.
        """
        if not query:
            return "Please provide a search query."
        
        # Validate max_results
        max_results = max(1, min(20, max_results or 5))
        
        if log:
            log(f"Searching products: query='{query}', category='{category}'")
        
        # Search logic (example)
        products = self._search_products(query, category, max_results)
        
        if not products:
            return f"No products found matching '{query}'."
        
        # Format response
        result = f"Found {len(products)} products:\n\n"
        for p in products:
            result += f"• **{p['name']}** - ${p['price']:.2f}\n"
            result += f"  {p['description']}\n"
            result += f"  Availability: {p['stock']} in stock\n\n"
        
        return result
    
    def _search_products(self, query: str, category: str, limit: int) -> list:
        # Database/API integration here
        return [
            {"name": "Widget Pro", "price": 99.99, "description": "Premium widget", "stock": 50},
            {"name": "Widget Basic", "price": 49.99, "description": "Standard widget", "stock": 100}
        ]
```

### Complete Related Content Example

```python
# agents/sales/faqs.py

from cogsol.tools import BaseFAQ

class ShippingFAQ(BaseFAQ):
    question = "What are your shipping options?"
    answer = """We offer several shipping options:
    
    - **Standard Shipping** (5-7 business days): Free for orders over $50
    - **Express Shipping** (2-3 business days): $9.99
    - **Next Day Delivery** (1 business day): $19.99
    
    International shipping is available to select countries."""

class ReturnsFAQ(BaseFAQ):
    question = "What is your return policy?"
    answer = """Our return policy:
    
    - 30-day money-back guarantee
    - Items must be unused and in original packaging
    - Free returns for defective products
    - Return shipping paid by customer for other reasons
    
    Contact support to initiate a return."""

class WarrantyFAQ(BaseFAQ):
    question = "Do your products have a warranty?"
    answer = """Yes! All our products include:
    
    - 1-year standard warranty on all items
    - Extended 3-year warranty available for purchase
    - Covers manufacturing defects
    - Does not cover physical damage or misuse"""
```

```python
# agents/sales/lessons.py

from cogsol.tools import BaseLesson

class UpsellLesson(BaseLesson):
    name = "Upselling Techniques"
    content = """When appropriate, suggest complementary products:
    - If customer buys a laptop, mention accessories (bag, mouse, stand)
    - Highlight bulk discounts for multiple items
    - Mention premium versions when budget seems flexible
    
    Never be pushy. Frame suggestions as helpful recommendations."""
    context_of_application = "product_discussion"

class ObjectionHandlingLesson(BaseLesson):
    name = "Handling Objections"
    content = """When customer expresses concern about price:
    1. Acknowledge their concern
    2. Emphasize value over cost
    3. Mention payment plans if available
    4. Offer to find alternatives in their budget
    
    Never dismiss concerns or pressure the customer."""
    context_of_application = "pricing_objection"
```
