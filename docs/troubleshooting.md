# Troubleshooting

### "A command is required"

```bash
# Wrong
cogsol-admin

# Right
cogsol-admin startproject myproject
```

### "Must be run from inside a CogSol project"

Ensure you're in a directory with `manage.py`:

```bash
cd myproject
python manage.py makemigrations
```

### "Credentials are not configured. Run cogsol-admin credentials-setup first."

Configure credentials with:

```bash
cogsol-admin credentials-setup
```

### "Could not resolve agent"

1. Run `migrate` first to sync your agents with the API and get remote IDs
2. Check `.state.json` for the correct agent name
3. Use the numeric ID directly: `--agent 42`

### "Error while importing definitions"

Check for Python syntax errors in your agent/tool code:

```bash
python -c "from agents.<youragent>.agent import *"
```

### "API error: 401 Unauthorized"

Verify that your configured credentials are correct, not expired, and belong to the tenant you are targeting. Project `.env` values override user-level credentials.

```bash
cogsol-admin credentials-setup
```

## Debug Tips

1. **Check state files**: Look at `agents/migrations/.state.json` for current mappings
2. **Review migrations**: Open `agents/migrations/*.py` to see generated operations
3. **Test imports**: Verify your code imports correctly before making migrations
4. **Credential source order**: process environment variables → project `.env` → user-level credential file
