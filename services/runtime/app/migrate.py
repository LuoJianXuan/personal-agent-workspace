import asyncio
from pathlib import Path
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from .config import required

async def main():
    async with await AsyncConnection.connect(required("RUNTIME_DATABASE_URL"), autocommit=True,
        row_factory=dict_row, options="-c search_path=runtime") as conn:
        await conn.execute("SELECT pg_advisory_lock(210002)")
        try:
            async with conn.transaction():
                await conn.execute("CREATE TABLE IF NOT EXISTS runtime.schema_migrations(version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
                await conn.execute("INSERT INTO runtime.schema_migrations(version) VALUES(1) ON CONFLICT DO NOTHING")
            # Explicit setup command only: not in lifespan or a request handler.
            exists=await (await conn.execute("SELECT to_regclass('runtime.runs') AS t")).fetchone()
            active=await (await conn.execute("SELECT count(*) AS n FROM runtime.runs r WHERE status IN ('QUEUED','RUNNING','WAITING_APPROVAL') AND COALESCE(to_jsonb(r)->>'engine_version','legacy')<>'deepagents-v1'")).fetchone() if exists['t'] else None
            if active and active['n']:raise RuntimeError('MIGRATION_PENDING_RUNS: drain old runs before migration')
            await conn.execute(Path(__file__).with_name("runtime_schema.sql").read_text())
            await conn.execute(Path(__file__).with_name('phase1_schema.sql').read_text())
            await conn.execute('SET search_path=runtime_harness_v2')
            await AsyncPostgresSaver(conn).setup()
        finally:
            await conn.execute("SELECT pg_advisory_unlock(210002)")

if __name__ == "__main__":
    asyncio.run(main())
