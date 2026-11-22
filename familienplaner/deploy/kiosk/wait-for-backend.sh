#!/usr/bin/env bash
# Wartet, bis das Backend erreichbar ist (max. 60 s)
for _ in $(seq 1 60); do
  curl -fs http://localhost:8000/api/health >/dev/null && exit 0
  sleep 1
done
exit 1
