import os

def required(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required configuration: {key}")
    return value

def service_token() -> str:
    token = required("BACKEND_TO_RUNTIME_TOKEN")
    reverse = required("RUNTIME_TO_BACKEND_TOKEN")
    if min(len(token), len(reverse)) < 32 or token == reverse:
        raise RuntimeError("Service tokens must be distinct and at least 32 characters")
    return token
