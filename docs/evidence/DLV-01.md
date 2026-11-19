# DLV-01：私有下载

日期：2026-11-07。实现：代码齐备。验证：运行通过。

## 改动与契约

download-location先鉴权，S3返回短签名、LocalFS保留同源返回；兼容download可302；中文文件名由mime.FormatMediaType处理。Web按次请求定位，不缓存签名。

涉及：Backend files.go/main.go、Web api.ts、OpenAPI。

## 一条请求

浏览器JWT → Backend owner/READY校验 → Head → public endpoint签名 → 浏览器下载。

## 失败边界

越权不生成URL；对象丢失/损坏返回错误；签名有效期内持有者可访问，非一次性凭证。跨域直链失败由浏览器展示，用户重试获取新签名。

## 已执行证据

LocalFS 同源下载与 MinIO `download-location` 短签名下载均通过；越权返回 404、未签名桶访问 403、下载后 SHA 匹配。验收客户端按前端真实路径直连签名 URL，不跨源转发 Backend Bearer。

## 验收边界

未执行浏览器视觉操作；生产构建、HTTP 5173 和两种 provider 的下载业务链路已验证。
