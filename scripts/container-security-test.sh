#!/usr/bin/env bash
set -euo pipefail

compose=(docker compose --profile security-tests)
cleanup() {
  "${compose[@]}" down >/dev/null 2>&1 || true
}
trap cleanup EXIT

"${compose[@]}" up -d --build

red_cid=$(docker compose ps -q red-workload)
blue_cid=$(docker compose ps -q blue-workload)

for container_id in "$red_cid" "$blue_cid"; do
  healthy=0
  for attempt in $(seq 1 20); do
    if [ "$(docker inspect --format '{{.State.Health.Status}}' "$container_id" 2>/dev/null || true)" = "healthy" ]; then
      healthy=1
      break
    fi
    sleep 1
  done
  if [ "$healthy" -ne 1 ]; then
    echo "workload container did not become healthy: $container_id" >&2
    exit 1
  fi
done

echo "Testing workload access through the Bayora gateway"
docker compose exec -T red-workload python3 -c 'import urllib.request; urllib.request.urlopen("http://bayora:8080/healthz", timeout=2).read()'
docker compose exec -T blue-workload python3 -c 'import urllib.request; urllib.request.urlopen("http://bayora:8080/healthz", timeout=2).read()'

echo "Testing RED -> BLUE network separation"
if docker compose exec -T red-workload python3 -c 'import socket; socket.getaddrinfo("blue-workload", 9090)' >/dev/null 2>&1; then
  echo "RED resolved BLUE across isolated networks" >&2
  exit 1
fi

echo "Testing BLUE -> RED network separation"
if docker compose exec -T blue-workload python3 -c 'import socket; socket.getaddrinfo("red-workload", 9090)' >/dev/null 2>&1; then
  echo "BLUE resolved RED across isolated networks" >&2
  exit 1
fi

echo "Testing provider network is not reachable from RED"
if docker compose exec -T red-workload python3 -c 'import socket; socket.getaddrinfo("ollama", 11434)' >/dev/null 2>&1; then
  echo "RED resolved the provider network" >&2
  exit 1
fi

for role in red blue; do
  container_id="${role}_cid"
  container_id=${!container_id}
  network_mode=$(docker inspect --format '{{.HostConfig.NetworkMode}}' "$container_id")
  mounts=$(docker inspect --format '{{json .Mounts}}' "$container_id")
  limits=$(docker inspect --format '{{.HostConfig.Memory}} {{.HostConfig.PidsLimit}}' "$container_id")
  readonly=$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$container_id")
  capabilities=$(docker inspect --format '{{json .HostConfig.CapDrop}}' "$container_id")
  security_options=$(docker inspect --format '{{json .HostConfig.SecurityOpt}}' "$container_id")
  if [ "$network_mode" = "host" ]; then
    echo "$role uses host networking" >&2
    exit 1
  fi
  case "$mounts" in
    *docker.sock*|*/var/run/docker.sock*) echo "$role exposes the Docker socket" >&2; exit 1 ;;
  esac
  case "$limits" in
    "0 "*|*" 0") echo "$role does not have explicit resource limits" >&2; exit 1 ;;
  esac
  if [ "$readonly" != "true" ]; then
    echo "$role workload root filesystem is writable" >&2
    exit 1
  fi
  case "$capabilities" in
    *ALL*) ;;
    *) echo "$role workload does not drop all capabilities" >&2; exit 1 ;;
  esac
  case "$security_options" in
    *no-new-privileges*) ;;
    *) echo "$role workload does not set no-new-privileges" >&2; exit 1 ;;
  esac
  if docker compose exec -T "${role}-workload" python3 -c 'import os; assert not os.path.exists("/var/run/docker.sock")' >/dev/null 2>&1; then
    echo "$role workload hardening: passed"
  else
    echo "$role workload exposes the Docker socket" >&2
    exit 1
  fi
done

echo "Docker network and workload hardening checks: passed"
