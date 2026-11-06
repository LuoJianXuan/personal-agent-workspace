"""On-demand document extraction shared by Agent tools and explicit preview."""
import hashlib
import json

from contracts.validate import validate
from .errors import RunError
from .execution import FixedProcessPool

PARSER_REVISION = "phase1-2"
ACCEPTED_REVISIONS = {"phase1-1", PARSER_REVISION}


class DocumentExtractor:
    def __init__(self):
        self.processes = FixedProcessPool()

    async def extract(self, data: bytes, metadata: dict) -> dict:
        validate("DocumentExtractMetadata", metadata)
        if hashlib.sha256(data).hexdigest() != metadata["sha256"]:
            raise RunError("FILE_INTEGRITY_ERROR")
        raw = await self.processes.run_document(
            data, metadata["media_type"], metadata["file_id"], metadata["sha256"]
        )
        try:
            document = json.loads(raw)
            validate("ParsedDocument", document)
        except Exception:
            raise RunError("PARSE_FAILED") from None
        if document["file_id"] != metadata["file_id"] or document["sha256"] != metadata["sha256"]:
            raise RunError("FILE_INTEGRITY_ERROR")
        return document


class OnDemandDocuments:
    def __init__(self, engine, start):
        self.engine = engine
        self.start = start

    def _ref(self, file_id: str) -> dict:
        for item in self.start["file_refs"]:
            if item["id"] == file_id:
                return item
        raise RunError("FILE_NOT_AUTHORIZED")

    async def get(self, file_id: str) -> dict:
        ref = self._ref(file_id)
        run_id = self.start["run_id"]
        await self.engine.authorize(self.start)
        cached = await self.engine.backend.get(
            f"/internal/files/{file_id}/parsed", params={"run_id": run_id}
        )
        if cached.status_code == 200:
            document = cached.json()
            validate("ParsedDocument", document)
            if document["sha256"] != ref["sha256"]:
                raise RunError("FILE_CHANGED")
            if document["parser_revision"] in ACCEPTED_REVISIONS and document["status"] in {"ready", "unsupported"}:
                return document
        blob = await self.engine.backend.get(
            f"/internal/files/{file_id}/blob", params={"run_id": run_id}
        )
        if blob.status_code != 200:
            raise RunError("FILE_UNAVAILABLE")
        metadata_response = await self.engine.backend.get(
            f"/internal/files/{file_id}/content",
            params={"run_id": run_id, "metadata_only": "1"},
        )
        if metadata_response.status_code != 200:
            raise RunError("FILE_UNAVAILABLE")
        file = metadata_response.json()["file"]
        if file["sha256"] != ref["sha256"] or hashlib.sha256(blob.content).hexdigest() != ref["sha256"]:
            raise RunError("FILE_CHANGED")
        document = await self.engine.documents.extract(blob.content, {
            "file_id": file_id,
            "sha256": ref["sha256"],
            "media_type": file["media_type"],
        })
        if document["status"] == "failed":
            raise RunError(document["error"] or "PARSE_FAILED")
        committed = await self.engine.backend.put(
            f"/internal/files/{file_id}/parsed",
            params={"run_id": run_id},
            json=document,
        )
        if committed.status_code != 200:
            raise RunError("DOCUMENT_CACHE_FAILED")
        saved = committed.json()
        validate("ParsedDocument", saved)
        return saved
