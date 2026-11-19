"""Static-only contracts/source consistency; no service, test or model calls."""
import ast,json
from pathlib import Path
from jsonschema import Draft202012Validator,FormatChecker
ROOT=Path(__file__).resolve().parents[1]
schema=json.loads((ROOT/'schemas/jsonschema/contracts.json').read_text(encoding='utf-8'))
Draft202012Validator.check_schema(schema)
for area in ('services/backend/internal/contracts','services/runtime/contracts','apps/web/src/contracts'):
    assert json.loads((ROOT/area/'schema.json').read_text(encoding='utf-8'))==schema,area
for file,kind in {'portable-artifact.json':'Artifact','portable-revision.json':'ArtifactRevision','portable-download.json':'DownloadLocation','portable-candidate.json':'CandidateArtifact','portable-storage-error.json':'Error'}.items():
    definition={'$schema':schema['$schema'],'$defs':schema['$defs'],'$ref':'#/$defs/'+kind}
    Draft202012Validator(definition,format_checker=FormatChecker()).validate(json.loads((ROOT/'schemas/examples'/file).read_text(encoding='utf-8')))
for area in ('services/runtime/app','services/compute-runner','scripts'):
    for file in (ROOT/area).glob('*.py'):ast.parse(file.read_text(encoding='utf-8-sig'),filename=str(file))
api=json.loads((ROOT/'schemas/openapi.yaml').read_text(encoding='utf-8'))
for route in ('/api/artifacts/{id}/revisions','/api/files/{id}/download-location'):assert route in api['paths']
print('Static schema copies, examples, OpenAPI and Python AST consistent; this checker does not execute business tests')
