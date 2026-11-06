# 002 — Combined entry for the first release
Web calls Backend only. Backend/control owns config/authorization; Backend/workspace owns business transactions; Backend/agententry composes their application interfaces and RuntimeClient. It must not access their business tables, call models or execute tools. No module handler calls another handler. Infrastructure/contracts do not depend on business modules.

One Backend process reduces deployment and authentication work for the 5–7 day scope. Configuration and SSE share CPU, memory, failures and releases. Separate RPC/stream connection pools and capacity limits reduce contention but do not provide process isolation. Backend failure also removes access to Runtime events.

Extract agententry into a Business Gateway only when stream connections need independent scaling, multiple clients need substantial shared orchestration, or release schedules diverge. The new process uses Backend APIs rather than tables; ownership and Runtime contracts remain stable. Extraction requires deployment, auth, timeout and failure redesign, not simply moving a folder. D1 does not add a gateway service.
