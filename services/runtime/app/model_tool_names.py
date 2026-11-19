"""Readable model-facing names; canonical IDs remain the execution authority."""
import hashlib
import re


def tool_aliases(specs):
    aliases = {}
    for spec in specs:
        canonical = spec['namespaced_tool_id']
        if not canonical.startswith('mcp_'):
            continue
        stem = re.sub(r'[^a-zA-Z0-9_-]', '_', spec['remote_name'])[:42]
        alias = 'mcp_' + stem + '_' + hashlib.sha256(canonical.encode()).hexdigest()[:16]
        if alias in aliases and aliases[alias] != canonical:
            raise ValueError('Model tool alias collision')
        aliases[alias] = canonical
    return aliases


def canonicalize_calls(message, aliases):
    for call in message.tool_calls:
        call['name'] = aliases.get(call['name'], call['name'])
    # Keep the provider representation consistent with LangChain's tool_calls.
    for call in message.additional_kwargs.get('tool_calls', []):
        function = call.get('function', {})
        if function.get('name') in aliases:
            function['name'] = aliases[function['name']]
