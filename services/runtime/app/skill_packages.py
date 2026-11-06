"""Freeze project-owned skill packages per Run and expose only read-only files."""
import hashlib
import json
from pathlib import Path

from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1] / "skills" / "documents"
VERSION = "documents-1"


def source_package() -> dict:
    files = {}
    for path in sorted(ROOT.rglob("*")):
        if path.is_file():
            relative = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            if len(text) > 30000:
                raise RuntimeError("SKILL_PACKAGE_TOO_LARGE")
            files[relative] = text
    canonical = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "skill_id": "documents",
        "name": "文档工作",
        "description": "按需读取附件、比较差异并生成带来源的报告",
        "version": VERSION,
        "sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "files": files,
    }


async def frozen_document_skill(engine, run_id: str) -> dict:
    package = source_package()
    async with engine.pool.connection() as connection:
        async with connection.transaction():
            await connection.execute(
                "INSERT INTO runtime.run_skill_bindings(run_id,skill_id,data) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                (run_id, package["skill_id"], Jsonb(package)),
            )
            row = await (await connection.execute(
                "SELECT data FROM runtime.run_skill_bindings WHERE run_id=%s AND skill_id=%s",
                (run_id, package["skill_id"]),
            )).fetchone()
    return row["data"]
