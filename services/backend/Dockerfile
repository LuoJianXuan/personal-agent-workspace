ARG DOCKER_REGISTRY=docker.io
FROM ${DOCKER_REGISTRY}/library/golang:1.25 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /server ./cmd/server
FROM ${DOCKER_REGISTRY}/library/debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates wget && rm -rf /var/lib/apt/lists/* && useradd -u 10001 -m workspace && mkdir -p /data/files && chown workspace /data/files
COPY --from=build /server /usr/local/bin/server
USER workspace
ENTRYPOINT ["server"]
