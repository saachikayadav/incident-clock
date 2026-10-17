#!/usr/bin/env bash
# Start/stop/restart a local service instance for tests and the persistence check.
# Requires API_KEY and DATABASE_URL in the environment. Usage: serve_local.sh start|stop|restart
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8000}"
PIDFILE=".run/uvicorn.pid"
mkdir -p .run reports

stop() {
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    kill "$(cat "$PIDFILE")"
    while kill -0 "$(cat "$PIDFILE")" 2>/dev/null; do sleep 0.2; done
  fi
  rm -f "$PIDFILE"
}

start() {
  : "${API_KEY:?API_KEY is required}" "${DATABASE_URL:?DATABASE_URL is required}"
  # Refuse to start if something else already answers on the port: otherwise the health
  # check below would pass against a stale process and tests would hit the wrong server.
  if curl -s -o /dev/null "http://127.0.0.1:$PORT/health"; then
    echo "port $PORT is already serving; stop that process first" >&2
    exit 1
  fi
  nohup python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" >> reports/service.log 2>&1 &
  echo $! > "$PIDFILE"
  for _ in $(seq 1 60); do
    if ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "service process exited during startup; see reports/service.log" >&2
      exit 1
    fi
    if curl -sf "http://127.0.0.1:$PORT/health" > /dev/null; then return 0; fi
    sleep 0.5
  done
  echo "service failed to start; see reports/service.log" >&2
  exit 1
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  *) echo "usage: $0 start|stop|restart" >&2; exit 2 ;;
esac
