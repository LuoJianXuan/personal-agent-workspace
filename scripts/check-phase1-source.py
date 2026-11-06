"""Static source/contract checks only; no services, model, tool or test invocation."""
import ast
import json
from datetime import datetime, timezone
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))

schema = read('schemas/jsonschema/contracts.json')
Draft202012Validator.check_schema(schema)
copies = ['services/runtime/contracts/schema.json', 'services/backend/internal/contracts/schema.json', 'apps/web/src/contracts/schema.json']
for path in copies:
    if read(path) != schema:
        raise ValueError('Generated schema drift: ' + path)
for path in ['services/backend/internal/control/builtin-tools.json', 'services/runtime/contracts/builtin-tools.json']:
    if read(path) != read('schemas/builtin-tools.json'):
        raise ValueError('Generated tool drift: ' + path)
examples = {
    'phase1-source.json': 'SourceRecord', 'phase1-document.json': 'ParsedDocument',
    'phase1-work-file.json': 'WorkFileWrite', 'phase1-artifact.json': 'BinaryArtifactMetadata',
    'phase1-task-event.json': 'Event',
}
for name, kind in examples.items():
    target = {'$schema': schema['$schema'], '$defs': schema['$defs'], '$ref': '#/$defs/' + kind}
    Draft202012Validator(target, format_checker=FormatChecker()).validate(read('schemas/examples/' + name))

files = []
for area in ['services/runtime/app', 'services/runtime/tests', 'services/compute-runner', 'scripts']:
    for path in sorted((ROOT / area).rglob('*.py')):
        if '__pycache__' in path.parts:
            continue
        ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
        files.append(path.relative_to(ROOT).as_posix())
openapi = read('schemas/openapi.yaml')
schemes = openapi['components']['securitySchemes']
for route in openapi['paths'].values():
    for operation in route.values():
        if not isinstance(operation, dict):
            continue
        for security in operation.get('security', []):
            for name in security:
                if name not in schemes:
                    raise ValueError('Undefined security scheme: ' + name)
engine = (ROOT / 'services/runtime/app/engine.py').read_text(encoding='utf-8')
models = (ROOT / 'services/runtime/app/models.py').read_text(encoding='utf-8')
for removed in ['StateGraph(', 'add_node(', 'add_edge(']:
    if removed in engine:
        raise ValueError('Legacy engine mechanism remains: ' + removed)
for removed in ['ProviderStream', 'aiter_lines(', 'data: [DONE]']:
    if removed in models:
        raise ValueError('Legacy provider parser remains: ' + removed)
result = {
    'checked_at': datetime.now(timezone.utc).isoformat(), 'kind': 'static_source_only',
    'python_ast_files': len(files), 'schema_copies': len(copies),
    'schema_examples': examples, 'openapi_security_references': 'declared',
    'legacy_loop_and_sse_parser': 'removed',
    'business_tests': 'not_run_by_this_static_command', 'browser_tests': 'not_run_by_this_static_command',
    'real_model_calls': 0, 'real_search_calls': 0,
}
(ROOT / 'docs/evidence/phase1-source-checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
