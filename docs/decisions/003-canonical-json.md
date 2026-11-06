# 003 — Canonical argument digests
Use RFC 8785 JSON Canonicalization Scheme (JCS), then SHA-256 of UTF-8 bytes, lower-case hex. Recursively sort object keys by UTF-16 code units; retain array order. No whitespace or BOM. Strings retain original Unicode (no NFC normalization); escape control characters per JCS, reject lone surrogates. Duplicate object keys are rejected before canonicalization.

Numbers use finite IEEE-754 binary64 and ECMAScript shortest serialization: 1.0 → 1, -0 → 0, 1e-7 stays 1e-7. Reject NaN/Infinity and integer inputs outside ±(2^53−1). Exact decimal quantities use schema-defined decimal strings rather than floating-point coercion. Null stays null; a missing property differs from an explicit null.

Do not substitute Go map marshaling, Python sort_keys, or default JSON.stringify for a JCS implementation. Integrate a vetted RFC 8785 library in each hashing producer in S03/S04; the browser only sends its stable idempotency key. `schemas/examples/canonical-args.json` is the shared known-answer fixture. D1 defines the rule and fixture, does not claim cross-language execution has been tested.

Start digest covers the frozen request excluding request_hash itself; volatile transport request IDs must not be regenerated during retries. Public submission digest covers thread_id/input/model selection/skills/files/scenario. Stable execution identity and full approval binding are specified in CONTRACTS §7–9.
