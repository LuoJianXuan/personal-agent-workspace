# 004 — 本机 PostgreSQL 部署选择

2026-11-02 经 Docker 实际检查：现有 `langfuse-postgres-1` 使用 PostgreSQL 16-alpine，属于 `C:/MyWorkSpace/kefu` 的 `langfuse` Compose 项目，数据卷为 `langfuse_langfuse_pg_data`，检查时处于 exited 状态。没有读取其密码或业务表，没有修改或启动这个 PG 容器。

本次采用独立 `agent-workspace` Compose 项目、PostgreSQL 17、`agent-workspace_pg-data` 数据卷和私有网络。只有 Web 绑定 localhost；不新增主机 5432 端口。项目的 workspace 数据库内：

| schema | 登录角色 | 权限 |
| --- | --- | --- |
| backend | workspace_backend | 仅自己的控制面与工作区表 |
| runtime | workspace_runtime | 仅自己的运行事实与 checkpoint 表 |

两个业务角色不授予 superuser/createdb/createrole。workspace_admin 只用于独立库 bootstrap；应用使用各自业务角色。search_path 指向自己的 schema，同时撤销 PUBLIC 的创建与私有 schema 权限。

理由：现有 PG 为 Langfuse 专属，复用将绑定到另一个项目的启停、维护和恢复周期。独立实例多占一个数据库进程的内存，但故障、版本升级和数据卷生命周期更清楚。仍共用 Docker 主机资源，不宣称硬件级隔离。

若未来明确建立个人共享基础设施：统一维护一个 PG 实例，各项目独立数据库，例如 agent_workspace / langfuse；数据库内再按服务分 schema 和角色。角色名是实例级的，需要项目前缀；撤销默认 CONNECT/TEMP 并按项目授予。不要只在现有 Langfuse 数据库增加 schema；schema 本身是命名空间，隔离要由角色权限共同落实。共享实例仍共享资源、停机窗口和管理员权限。

依据：https://www.postgresql.org/docs/17/ddl-schemas.html

本机 Docker Hub 元信息拉取出现 EOF；通过本项目 DOCKER_REGISTRY 使用 docker.m.daocloud.io 重试，不改变 Docker 全局配置。默认示例仍用 docker.io。
