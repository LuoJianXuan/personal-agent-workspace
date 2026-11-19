import unittest
from langchain_core.messages import AIMessage
from app.model_tool_names import tool_aliases, canonicalize_calls


class ModelToolNamesTest(unittest.TestCase):
    def test_readable_unique_names_and_canonical_roundtrip(self):
        specs = [
            {'namespaced_tool_id': 'mcp_user_a_calendar', 'remote_name': 'campaign-calendar'},
            {'namespaced_tool_id': 'mcp_user_b_calendar', 'remote_name': 'campaign-calendar'},
            {'namespaced_tool_id': 'mcp_user_a_other', 'remote_name': 'query-meal-assistance'},
            {'namespaced_tool_id': 'builtin_python'},
        ]
        aliases = tool_aliases(specs)
        self.assertEqual(len(aliases), 3)
        for alias, canonical in aliases.items():
            self.assertLessEqual(len(alias), 64)
            self.assertRegex(alias, r'^mcp_[a-zA-Z0-9_-]+$')
            message = AIMessage(content='', tool_calls=[{'name': alias, 'args': {}, 'id': 'call1'}],
                                additional_kwargs={'tool_calls': [{'function': {'name': alias}}]})
            canonicalize_calls(message, aliases)
            self.assertEqual(message.tool_calls[0]['name'], canonical)
            self.assertEqual(message.additional_kwargs['tool_calls'][0]['function']['name'], canonical)
            self.assertEqual(message.tool_calls[0]['id'], 'call1')

    def test_unknown_name_is_not_remapped_or_authorized(self):
        message = AIMessage(content='', tool_calls=[{'name': 'untrusted', 'args': {}, 'id': 'call1'}])
        canonicalize_calls(message, {'known': 'mcp_canonical'})
        self.assertEqual(message.tool_calls[0]['name'], 'untrusted')


if __name__ == '__main__':
    unittest.main()
