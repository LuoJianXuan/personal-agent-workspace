"""Tool directory contracts and publication acceptance on isolated stack only."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('day2', ROOT / 'scripts/accept-day2.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


def main():
    admin = d.login('ADMIN')['access_token']
    user = d.login('USER_A')['access_token']
    path = '/admin/connector-definitions'
    d.request(path, token=user, expect=403)
    original = d.request(path, token=admin)['items'][0]
    item_path = path + '/' + original['connector_id']
    current = original
    results = []
    try:
        presentation = {'description': '目录验收：个人连接与平台服务分开授权', 'category': '验收分类',
                        'icon': 'plug', 'token_help_url': 'https://example.com/token'}
        payload = {'name': original['name'], 'enabled': original['enabled'], 'revision': current['revision'], 'presentation': presentation}
        current = d.request(item_path, 'PATCH', payload, admin)
        assert current['presentation'] == presentation
        d.request(item_path, 'PATCH', payload, admin, 409)
        d.request(item_path, 'PATCH', {**payload, 'revision': current['revision']}, user, 403)
        current = d.request(item_path, 'PATCH', {'name': current['name'], 'enabled': True, 'revision': current['revision']}, admin)
        assert current['presentation'] == presentation
        for link in ('http://example.com', 'https://user:pass@example.com', 'javascript:alert(1)'):
            d.request(item_path, 'PATCH', {**payload, 'revision': current['revision'], 'presentation': {**presentation, 'token_help_url': link}}, admin, 400)
        public = d.request('/catalog/connectors', token=user)['items']
        row = next(x for x in public if x['connector_id'] == original['connector_id'])
        assert row['presentation'] == presentation
        assert not {'endpoint', 'token', 'credential_ref', 'headers'}.intersection(row)
        results += ['metadata roundtrip and legacy omission preserves fields', 'revision conflict and ordinary-user denial', 'unsafe help URLs rejected', 'public catalog metadata without connection secrets']
        platform = d.request('/catalog/mcp-services', token=user)['items']
        for row in platform:
            assert set(row).issubset({'id', 'name', 'availability', 'reason', 'tools'})
            assert (row['availability'] == 'configured') == bool(row['tools'])
        results.append('platform service safe projection and availability')
    finally:
        latest = next(x for x in d.request(path, token=admin)['items'] if x['connector_id'] == original['connector_id'])
        d.request(item_path, 'PATCH', {'name': original['name'], 'enabled': original['enabled'], 'revision': latest['revision'], 'presentation': original['presentation']}, admin)
    report = {'status': 'passed', 'checks': results, 'real_model_calls': 0, 'real_mcp_calls': 0}
    (ROOT / 'docs/evidence/tool-directory-api-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
