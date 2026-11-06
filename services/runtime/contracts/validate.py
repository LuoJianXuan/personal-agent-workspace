import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
SCHEMA = json.loads(Path(__file__).with_name("schema.json").read_text(encoding="utf-8"))
def validate(name: str, value: object) -> None:
    Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": SCHEMA["$defs"]}, format_checker=FormatChecker()).validate(value)
