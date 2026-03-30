#!/usr/bin/env bash
# Collect useful diagnostics for AnnaSEO production troubleshooting.
# Run this on the production host and upload the generated archive from /tmp.

OUT_DIR="/tmp/annaseo_diagnostics_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT_DIR"
echo "Collecting diagnostics into $OUT_DIR"

echo "=== System info ===" > "$OUT_DIR/system.txt"
uname -a >> "$OUT_DIR/system.txt" 2>&1 || true
if command -v lsb_release >/dev/null 2>&1; then lsb_release -a >> "$OUT_DIR/system.txt" 2>&1 || true; fi
date >> "$OUT_DIR/system.txt" 2>&1 || true

echo "=== Processes (uvicorn/gunicorn/python) ===" > "$OUT_DIR/processes.txt"
ps aux | egrep 'uvicorn|gunicorn|python' | egrep -v 'egrep' >> "$OUT_DIR/processes.txt" 2>&1 || true

echo "=== Listening ports ===" > "$OUT_DIR/ports.txt"
if command -v ss >/dev/null 2>&1; then ss -ltnp >> "$OUT_DIR/ports.txt" 2>&1 || true; else netstat -plnt >> "$OUT_DIR/ports.txt" 2>&1 || true; fi

echo "=== curl localhost health ===" > "$OUT_DIR/local_curl.txt"
for url in "http://127.0.0.1:8000/api/health" "http://localhost:8000/api/health" "http://127.0.0.1:8000/"; do
  echo "== $url ==" >> "$OUT_DIR/local_curl.txt"
  curl -sS -m 5 -D - "$url" >> "$OUT_DIR/local_curl.txt" 2>&1 || true
  echo "" >> "$OUT_DIR/local_curl.txt"
done

echo "=== nginx logs (if present) ===" > "$OUT_DIR/nginx_logs.txt"
if [ -f /var/log/nginx/error.log ]; then tail -n 500 /var/log/nginx/error.log >> "$OUT_DIR/nginx_logs.txt" 2>&1 || true; fi
if [ -f /var/log/nginx/access.log ]; then tail -n 200 /var/log/nginx/access.log >> "$OUT_DIR/nginx_logs.txt" 2>&1 || true; fi

echo "=== docker containers and logs ===" > "$OUT_DIR/docker.txt"
if command -v docker >/dev/null 2>&1; then
  docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' >> "$OUT_DIR/docker.txt" 2>&1 || true
  CONTAINERS=$(docker ps --format '{{.Names}}' | egrep -i 'annaseo' || true)
  for c in $CONTAINERS; do
    echo "=== logs for $c ===" >> "$OUT_DIR/docker.txt"
    docker logs --tail 500 "$c" >> "$OUT_DIR/docker.txt" 2>&1 || true
  done
fi

echo "=== systemd annaseo service (if present) ===" > "$OUT_DIR/systemd.txt"
if command -v systemctl >/dev/null 2>&1 && systemctl status annaseo >/dev/null 2>&1; then
  systemctl status annaseo --no-pager -l >> "$OUT_DIR/systemd.txt" 2>&1 || true
  journalctl -u annaseo -n 500 --no-pager >> "$OUT_DIR/systemd.txt" 2>&1 || true
fi

echo "=== environment vars (common) ===" > "$OUT_DIR/env.txt"
for v in ANNASEO_DB ANNASEO_DB_FALLBACK FERNET_KEY ANTHROPIC_API_KEY GROQ_API_KEY GEMINI_API_KEY OPENAI_API_KEY OLLAMA_URL; do
  # shellcheck disable=SC2154
  val="${!v-}"
  echo "$v=$val" >> "$OUT_DIR/env.txt" 2>&1 || true
done

echo "=== sqlite DB stat info (common paths) ===" > "$OUT_DIR/db_stat.txt"
if [ -n "${ANNASEO_DB-}" ] && [ -f "${ANNASEO_DB}" ]; then stat "${ANNASEO_DB}" >> "$OUT_DIR/db_stat.txt" 2>&1 || true; fi
if [ -f /tmp/annaseo.db ]; then stat /tmp/annaseo.db >> "$OUT_DIR/db_stat.txt" 2>&1 || true; fi

echo "=== summary: quick curl to public endpoint ===" > "$OUT_DIR/public_curl.txt"
curl -sS -D - "https://annaseo.pureleven.com/api/health" -m 10 >> "$OUT_DIR/public_curl.txt" 2>&1 || true

ARCHIVE="/tmp/annaseo_diagnostics_$(date +%Y%m%d_%H%M%S).tar.gz"
tar -czf "$ARCHIVE" -C /tmp "$(basename "$OUT_DIR")" || true

echo "Diagnostics collected into: $OUT_DIR"
echo "Archive created: $ARCHIVE"
echo "Please upload the archive or paste relevant logs from $OUT_DIR for further analysis."

exit 0
