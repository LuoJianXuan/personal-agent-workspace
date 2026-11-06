"""Optional Agent/model/tool tracing. Missing or broken Langfuse never fails a Run."""
import asyncio
import os
from contextlib import nullcontext

from .errors import safe_text

MAX_OBS_TEXT = 2000


def enabled() -> bool:
    return all(os.getenv(name) for name in (
        "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL", "LANGFUSE_PROJECT_ID"
    )) and os.getenv("LANGFUSE_TRACING_ENABLED", "true").lower() == "true"


def _bounded(value, depth=0):
    if depth > 5:
        return "[TRUNCATED]"
    if isinstance(value, str):
        cleaned = safe_text(value)
        return cleaned[:MAX_OBS_TEXT] + ("…[TRUNCATED]" if len(cleaned) > MAX_OBS_TEXT else "")
    if isinstance(value, dict):
        return {safe_text(str(k))[:120]: _bounded(v, depth + 1) for k, v in list(value.items())[:30]}
    if isinstance(value, (list, tuple)):
        return [_bounded(v, depth + 1) for v in list(value)[:30]]
    return value if value is None or isinstance(value, (bool, int, float)) else _bounded(str(value), depth + 1)


def _safe_messages(groups):
    safe_groups = []
    for group in groups[:20]:
        safe_group = []
        for message in group[:50]:
            try:
                safe_group.append(message.model_copy(update={"content": _bounded(message.content)}))
            except Exception:
                safe_group.append(_bounded(message))
        safe_groups.append(safe_group)
    return safe_groups


def _callback_kwargs(kwargs):
    result = dict(kwargs)
    for key in ("metadata", "inputs", "invocation_params"):
        if key in result:
            result[key] = _bounded(result[key])
    return result


def _safe_output(output):
    try:
        return output.model_copy(update={"content": _bounded(output.content)})
    except Exception:
        return _bounded(output)


def _safe_llm_result(response):
    try:
        groups = []
        for group in response.generations[:20]:
            safe_group = []
            for generation in group[:20]:
                update = {}
                if hasattr(generation, "message"):
                    update["message"] = _safe_output(generation.message)
                if hasattr(generation, "text"):
                    update["text"] = _bounded(generation.text)
                safe_group.append(generation.model_copy(update=update, deep=True))
            groups.append(safe_group)
        return response.model_copy(update={
            "generations": groups,
            "llm_output": _bounded(getattr(response, "llm_output", None)),
        }, deep=True)
    except Exception:
        return response


def trace_id(run_id: str) -> str:
    if not enabled():
        return ""
    try:
        from langfuse import Langfuse
        return Langfuse.create_trace_id(seed=run_id)
    except Exception:
        return ""


def trace_url(run_id: str) -> str:
    identity = trace_id(run_id)
    if not identity:
        return ""
    base = os.getenv("LANGFUSE_PUBLIC_URL", os.environ["LANGFUSE_BASE_URL"]).rstrip("/")
    project = os.environ["LANGFUSE_PROJECT_ID"]
    return f"{base}/project/{project}/traces/{identity}"


def callback(run_id: str):
    if not enabled():
        return None
    try:
        from langfuse.langchain import CallbackHandler

        class SanitizedCallback(CallbackHandler):
            def on_chain_start(self, serialized, inputs, **kwargs):
                return super().on_chain_start(serialized, _bounded(inputs), **_callback_kwargs(kwargs))
            def on_chain_end(self, outputs, **kwargs):
                return super().on_chain_end(_bounded(outputs), **_callback_kwargs(kwargs))
            def on_llm_start(self, serialized, prompts, **kwargs):
                return super().on_llm_start(serialized, _bounded(prompts), **_callback_kwargs(kwargs))
            def on_chat_model_start(self, serialized, messages, **kwargs):
                return super().on_chat_model_start(serialized, _safe_messages(messages), **_callback_kwargs(kwargs))
            def on_llm_end(self, response, **kwargs):
                return super().on_llm_end(_safe_llm_result(response), **_callback_kwargs(kwargs))
            def on_tool_start(self, serialized, input_str, **kwargs):
                return super().on_tool_start(serialized, _bounded(input_str), **_callback_kwargs(kwargs))
            def on_tool_end(self, output, **kwargs):
                return super().on_tool_end(_safe_output(output), **_callback_kwargs(kwargs))

        return SanitizedCallback(trace_context={"trace_id": trace_id(run_id)})
    except Exception:
        return None


def attributes(start: dict):
    if not enabled():
        return nullcontext()
    try:
        from langfuse import propagate_attributes
        context = start["context"]
        return propagate_attributes(
            trace_name="personal-agent-run",
            user_id=context["user_id"],
            session_id=start["thread_id"],
            tags=["personal-agent", start["mode"]],
            metadata={
                "run_id": start["run_id"],
                "tenant_id": context["tenant_id"],
                "project_id": context["project_id"],
            },
        )
    except Exception:
        return nullcontext()


async def flush(timeout: float = 3.0) -> None:
    if not enabled():
        return
    try:
        from langfuse import get_client
        await asyncio.wait_for(asyncio.to_thread(get_client().flush), timeout)
    except Exception:
        pass
