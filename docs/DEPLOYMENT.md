Deployment and 502 mitigation checklist
=====================================

This document describes steps to deploy the application and mitigate 502 Bad Gateway errors observed from the reverse proxy.

1) Why 502 happens
- 502 is returned by the proxy (nginx / Cloudflare) when the backend is unreachable or dies.

2) Quick fixes (apply in production)
- Ensure the backend process is auto-restarted: use systemd or docker-compose `restart: always` (we updated docker-compose.yml).
- Limit workers (use a single uvicorn worker in constrained environments): avoid `--reload` in production.
- Add a small watchdog (scripts/watchdog.sh) in a cron or systemd timer to detect long outage windows and restart.

3) Required diagnostic commands (run on server)
- Check nginx error logs:
  - `sudo tail -n 200 /var/log/nginx/error.log`

- Check service status (docker):
  - `docker ps -a`
  - `docker logs <api-container>`

- Check systemd status (if deployed without docker):
  - `sudo systemctl status annaseo`
  - `sudo journalctl -u annaseo -n 200`

- Check OOM events:
  - `dmesg | grep -i oom`

4) Nginx tuning (example)
Add to your proxy config block:

```
proxy_connect_timeout 5s;
proxy_read_timeout 60s;
proxy_send_timeout 60s;
proxy_next_upstream error timeout http_502 http_503 http_504;
proxy_next_upstream_tries 3;
```

5) Deploying systemd unit (docker-compose variant)
- Copy `deploy/annaseo.service` to `/etc/systemd/system/annaseo.service` and edit `WorkingDirectory` to the repo path (e.g., `/opt/annaseo`).
- Enable and start:
  - `sudo systemctl daemon-reload`
  - `sudo systemctl enable --now annaseo`

6) Setting up watchdog
- Add a cron entry or systemd timer to run `scripts/watchdog.sh` every 30s–1m.

7) Next steps
- Gather logs and share them if 502 persists. Specifically: nginx error.log and backend stdout/journal entries, and `dmesg` output.
- If OOM kills are observed, reduce concurrency and increase instance memory.
