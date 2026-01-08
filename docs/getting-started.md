# Getting Started with CogSol

This guide walks you through creating your first CogSol project, from installation to deploying your first AI agent.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Creating Your First Project](#creating-your-first-project)
- [Understanding the Project Structure](#understanding-the-project-structure)
- [Creating Your First Agent](#creating-your-first-agent)
- [Customizing the Agent](#customizing-the-agent)
- [Adding Tools](#adding-tools)
- [Creating Migrations](#creating-migrations)
- [Deploying to CogSol API](#deploying-to-cogsol-api)
- [Testing Your Agent](#testing-your-agent)
- [Next Steps](#next-steps)

---

## Prerequisites

Before you begin, ensure you have:

- **Python 3.9 or higher**
- **pip** (Python package installer)
- **A CogSol API account** (for deployment)
- **Git** (recommended for version control)

### Check Python Version

```bash
python --version
# Should output: Python 3.9.x or higher
```

---

## Installation

### Step 1: Clone or Install the Framework

```bash
# Option A: Install from source
git clone <repository-url> cogsol-framework
cd cogsol-framework/framework
pip install -e .

# Option B: Install from PyPI (when available)
pip install cogsol
```

### Step 2: Verify Installation

```bash
cogsol-admin
```

You should see:
```
A command is required. Available commands: chat, importagent, makemigrations, migrate, startagent, startproject
```

---

## Creating Your First Project

### Step 1: Create the Project

```bash
cogsol-admin startproject my_assistant
cd my_assistant
```

### Step 2: Set Up Environment

```bash
# Copy the example environment file
copy .env.example .env

# Edit .env with your settings (use your preferred editor)
notepad .env
```

Update `.env` with your CogSol API credentials:

```env
COGSOL_ENV=development
COGSOL_API_BASE=https://api.cogsol.ai/cognitive/
COGSOL_API_TOKEN=your-api-token-here
```

### Step 3: Verify Project Setup

```bash
python manage.py
```

You should see available commands listed.

---

## Understanding the Project Structure

Your new project has this structure:

```
my_assistant/
├── manage.py           # CLI entry point (like Django's manage.py)
├── settings.py         # Project configuration
├── .env               # Environment variables (don't commit!)
├── .env.example       # Environment template
├── README.md          # Project documentation
└── agents/            # Agents application
    ├── __init__.py
    ├── tools.py       # Shared tool definitions
    └── migrations/    # Migration files
        └── __init__.py
```

### Key Files Explained

| File | Purpose |
|------|---------|
| `manage.py` | Run commands for this project |
| `settings.py` | Project name and base configuration |
| `.env` | API credentials (keep secret!) |
| `agents/tools.py` | Define tools used by your agents |
| `agents/migrations/` | Track changes to your agents |

---

## Creating Your First Agent

### Step 1: Generate Agent Scaffold

```bash
python manage.py startagent CustomerSupport
```

This creates a complete agent package:

```
agents/
└── customersupport/
    ├── __init__.py        # Exports the agent class
    ├── agent.py           # Main agent definition
    ├── faqs.py            # Frequently asked questions
    ├── fixed.py           # Fixed responses
    ├── lessons.py         # Contextual lessons
    └── prompts/
        └── customersupport.md  # System prompt
```

### Step 2: Review the Generated Agent

Open `agents/customersupport/agent.py`:

```python
from cogsol.agents import BaseAgent, genconfigs
from cogsol.prompts import Prompts
from ..tools import ExampleTool


class CustomerSupportAgent(BaseAgent):
    system_prompt = Prompts.load("customersupport.md")
    generation_config = genconfigs.QA()
    tools = [ExampleTool()]
    max_responses = 5
    max_msg_length = 2048
    max_consecutive_tool_calls = 3
    temperature = 0.3

    class Meta:
        name = "CustomerSupportAgent"
        chat_name = "CustomerSupportAgent Chat"
```

---

## Customizing the Agent

### Step 1: Edit the System Prompt

Open `agents/customersupport/prompts/customersupport.md`:

```markdown
# Customer Support Agent

You are a friendly and helpful customer support agent for Acme Corporation.

## Your Role
- Answer questions about our products and services
- Help resolve customer issues
- Provide accurate information

## Guidelines
1. Always be polite and professional
2. If you don't know something, say so honestly
3. Offer to escalate to a human agent when needed
4. Keep responses concise but helpful

## Products
- Acme Widget Pro: Our flagship product ($99.99)
- Acme Widget Basic: Entry-level option ($49.99)
- Acme Widget Enterprise: For businesses (custom pricing)

## Policies
- 30-day money-back guarantee
- Free shipping on orders over $50
- 1-year warranty on all products
```

### Step 2: Update Agent Configuration

Edit `agents/customersupport/agent.py`:

```python
from cogsol.agents import BaseAgent, genconfigs
from cogsol.prompts import Prompts
from ..tools import ExampleTool


class CustomerSupportAgent(BaseAgent):
    # Load the system prompt
    system_prompt = Prompts.load("customersupport.md")
    
    # Use QA generation config for factual responses
    generation_config = genconfigs.QA()
    
    # Available tools
    tools = [ExampleTool()]
    
    # Set reasonable limits
    max_responses = 10          # Allow longer conversations
    max_msg_length = 2048       # Max user message length
    max_consecutive_tool_calls = 3
    temperature = 0.3           # Lower = more consistent
    
    # Welcome message
    initial_message = "Hello! Welcome to Acme Support. How can I help you today?"
    
    # Message when ending conversation
    forced_termination_message = "Thank you for contacting Acme Support. Have a great day!"

    class Meta:
        name = "CustomerSupportAgent"
        chat_name = "Acme Customer Support"
        logo_url = None  # Add your logo URL if available
        primary_color = "#007bff"
```

### Step 3: Add FAQs

Edit `agents/customersupport/faqs.py`:

```python
from cogsol.tools import BaseFAQ


class ShippingFAQ(BaseFAQ):
    question = "How long does shipping take?"
    answer = """Shipping times depend on your location:
    - Standard (5-7 business days): Free for orders over $50
    - Express (2-3 business days): $9.99
    - Next Day: $19.99
    
    International shipping is available to select countries."""


class ReturnFAQ(BaseFAQ):
    question = "What is your return policy?"
    answer = """We offer a 30-day money-back guarantee:
    - Items must be unused and in original packaging
    - Free returns for defective products
    - Contact support to initiate a return"""


class WarrantyFAQ(BaseFAQ):
    question = "Do products have a warranty?"
    answer = """Yes! All products include a 1-year warranty covering:
    - Manufacturing defects
    - Component failures
    - Does not cover physical damage from misuse"""
```

### Step 4: Add Lessons

Edit `agents/customersupport/lessons.py`:

```python
from cogsol.tools import BaseLesson


class EmpathyLesson(BaseLesson):
    name = "Empathy First"
    content = """When customers express frustration:
    1. Acknowledge their feelings first
    2. Apologize for any inconvenience
    3. Focus on solutions
    4. Offer alternatives when possible
    
    Example: "I understand how frustrating that must be. Let me help fix this for you." """
    context_of_application = "customer_frustration"


class EscalationLesson(BaseLesson):
    name = "When to Escalate"
    content = """Escalate to a human agent when:
    - Customer explicitly requests it
    - Issue requires account-level changes
    - Customer remains unsatisfied after 2 solution attempts
    - Legal or sensitive matters arise
    
    Say: "I'd like to connect you with a specialist who can better assist you." """
    context_of_application = "complex_issues"
```

---

## Adding Tools

### Step 1: Create a Custom Tool

Edit `agents/tools.py` to add a useful tool:

```python
from cogsol.tools import BaseTool, tool_params


class ExampleTool(BaseTool):
    """The default example tool - you can remove this."""
    description = "Demo tool that echoes the provided text."

    @tool_params(
        text={"description": "Text to echo", "type": "string", "required": True},
        count={"description": "Times to repeat", "type": "integer", "required": False},
    )
    def run(self, chat=None, data=None, secrets=None, log=None, text: str = "", count: int = 1):
        message = " ".join([text] * max(1, int(count)))
        response = message
        return response


class OrderLookupTool(BaseTool):
    """Look up order status by order ID."""
    description = "Look up the status of a customer order using their order ID."

    @tool_params(
        order_id={
            "description": "The order ID to look up (e.g., ORD-12345)",
            "type": "string",
            "required": True
        }
    )
    def run(self, chat=None, data=None, secrets=None, log=None, order_id: str = ""):
        if not order_id:
            return "Please provide an order ID."
        
        # In a real implementation, you would query your order system
        # This is a mock response for demonstration
        
        if log:
            log(f"Looking up order: {order_id}")
        
        # Mock order data
        mock_orders = {
            "ORD-12345": {
                "status": "Shipped",
                "tracking": "1Z999AA10123456784",
                "eta": "December 15, 2025"
            },
            "ORD-67890": {
                "status": "Processing",
                "tracking": None,
                "eta": "December 18, 2025"
            }
        }
        
        order = mock_orders.get(order_id.upper())
        
        if not order:
            return f"Order {order_id} not found. Please check the order ID and try again."
        
        response = f"**Order {order_id}**\n"
        response += f"- Status: {order['status']}\n"
        if order['tracking']:
            response += f"- Tracking: {order['tracking']}\n"
        response += f"- Estimated Arrival: {order['eta']}"
        
        return response


class ProductSearchTool(BaseTool):
    """Search the product catalog."""
    description = "Search for products in the Acme catalog by name or category."

    @tool_params(
        query={
            "description": "Search query (product name or keywords)",
            "type": "string",
            "required": True
        }
    )
    def run(self, chat=None, data=None, secrets=None, log=None, query: str = ""):
        if not query:
            return "Please provide a search query."
        
        # Mock product catalog
        products = [
            {"name": "Acme Widget Pro", "price": 99.99, "category": "Premium"},
            {"name": "Acme Widget Basic", "price": 49.99, "category": "Standard"},
            {"name": "Acme Widget Enterprise", "price": "Custom", "category": "Business"},
            {"name": "Widget Accessories Pack", "price": 24.99, "category": "Accessories"},
        ]
        
        # Simple search
        query_lower = query.lower()
        matches = [p for p in products if query_lower in p["name"].lower() 
                   or query_lower in p["category"].lower()]
        
        if not matches:
            return f"No products found matching '{query}'. Try 'widget' or 'accessories'."
        
        response = f"Found {len(matches)} products:\n\n"
        for p in matches:
            price = f"${p['price']}" if isinstance(p['price'], float) else p['price']
            response += f"• **{p['name']}** - {price} ({p['category']})\n"
        
        return response
```

### Step 2: Update Agent to Use New Tools

Edit `agents/customersupport/agent.py`:

```python
from cogsol.agents import BaseAgent, genconfigs
from cogsol.prompts import Prompts
from ..tools import OrderLookupTool, ProductSearchTool  # Updated import


class CustomerSupportAgent(BaseAgent):
    system_prompt = Prompts.load("customersupport.md")
    generation_config = genconfigs.QA()
    
    # Updated tools list
    tools = [
        OrderLookupTool(),
        ProductSearchTool(),
    ]
    
    max_responses = 10
    max_msg_length = 2048
    max_consecutive_tool_calls = 3
    temperature = 0.3
    
    initial_message = "Hello! Welcome to Acme Support. How can I help you today?"
    forced_termination_message = "Thank you for contacting Acme Support. Have a great day!"

    class Meta:
        name = "CustomerSupportAgent"
        chat_name = "Acme Customer Support"
        primary_color = "#007bff"
```

---

## Creating Migrations

Now that you've defined your agent and tools, create a migration:

```bash
python manage.py makemigrations
```

You should see:
```
Created migration 0001_initial for app 'agents'.
```

### Review the Migration

Check `agents/migrations/0001_initial.py`:

```python
# Generated by CogSol 0.1.0 on 2025-01-08 10:00
from cogsol.db import migrations


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateTool(name='OrderLookup', fields={...}),
        migrations.CreateTool(name='ProductSearch', fields={...}),
        migrations.CreateAgent(name='CustomerSupportAgent', fields={...}, meta={...}),
    ]
```

---

## Deploying to CogSol API

### Step 1: Ensure API Credentials

Verify your `.env` file has valid credentials:

```env
COGSOL_API_BASE=https://api.cogsol.ai/cognitive/
COGSOL_API_TOKEN=sk-your-valid-token
```

### Step 2: Apply Migrations

```bash
python manage.py migrate
```

You should see:
```
Applying agents.0001_initial...
  Recorded.
Applied 1 migration(s) and synced with CogSol API.
```

### Step 3: Verify Deployment

Check `agents/migrations/.state.json` to see remote IDs:

```json
{
    "state": {...},
    "remote": {
        "agents": {
            "CustomerSupportAgent": 42
        },
        "tools": {
            "OrderLookup": 15,
            "ProductSearch": 16
        }
    }
}
```

---

## Testing Your Agent

### Using the CLI Chat

```bash
python manage.py chat --agent CustomerSupportAgent
```

This opens an interactive chat session:

```
    ██████╗ ██████╗  ██████╗ ███████╗ ██████╗ ██╗     
   ██╔════╝██╔═══██╗██╔════╝ ██╔════╝██╔═══██╗██║     
   ...
   
  🤖  Agent: CustomerSupportAgent #42
  📅  January 8, 2025 • 10:00

  ╭─ Message
  ╰─▶ Hello, can you check order ORD-12345?

  🤖
  ╭───────────────────────────────────────────╮
  │ I'd be happy to help! Let me look up      │
  │ that order for you.                       │
  │                                           │
  │ **Order ORD-12345**                       │
  │ - Status: Shipped                         │
  │ - Tracking: 1Z999AA10123456784            │
  │ - Estimated Arrival: December 15, 2025   │
  ╰───────────────────────────────────────────╯
```

### Chat Commands

- `/exit` or `Ctrl+C` - End the session
- `/new` - Start a fresh conversation

---

## Next Steps

Congratulations! You've created and deployed your first CogSol agent. Here's what to explore next:

### 1. Add More Agents

```bash
python manage.py startagent Sales
python manage.py startagent TechSupport
```

### 2. Create Advanced Tools

Connect tools to real databases, APIs, or services:

```python
class RealOrderLookupTool(BaseTool):
    def run(self, chat=None, data=None, secrets=None, log=None, order_id: str = ""):
        # Use secrets to get API key
        api_key = secrets.get("ORDER_API_KEY") if secrets else None
        
        # Make real API call
        response = requests.get(
            f"https://api.mycompany.com/orders/{order_id}",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        
        return response.json()
```

### 3. Import Existing Agents

If you have agents in the CogSol platform:

```bash
python manage.py importagent 123
```

### 4. Learn More

- [Architecture Documentation](docs/architecture.md) - Understand how CogSol framework works
- [CLI Commands Reference](docs/commands.md) - All available commands
- [API Client Reference](docs/api.md) - Direct API integration
- [Agents & Tools Reference](docs/agents-tools.md) - Advanced patterns

### 5. Version Control

Add your project to Git:

```bash
git init
git add .
git commit -m "Initial CogSol project"
```

**Important:** Add `.env` to `.gitignore`:

```bash
echo ".env" >> .gitignore
```

---

## Troubleshooting

### "COGSOL_API_BASE is required"

Create or update your `.env` file with your API credentials.

### "Could not resolve agent"

Run `migrate` first to sync your agents with the API.

### "Error while importing definitions"

Check for Python syntax errors:

```bash
python -c "from agents.customersupport.agent import *"
```

### "API error: 401 Unauthorized"

Verify your `COGSOL_API_TOKEN` is correct and not expired.

---

## Summary

In this guide, you learned to:

1. ✅ Install the CogSol framework
2. ✅ Create a new project
3. ✅ Generate an agent scaffold
4. ✅ Customize agents with prompts, FAQs, and lessons
5. ✅ Create custom tools
6. ✅ Generate and apply migrations
7. ✅ Deploy to the CogSol API
8. ✅ Test your agent via CLI chat

You're now ready to build sophisticated AI agents with CogSol!
