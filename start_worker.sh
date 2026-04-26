#!/bin/bash
cd /root/ANNASEOv1
exec /root/ANNASEOv1/.venv/bin/python3 /usr/local/bin/rq worker pipeline research score errors --url redis://localhost:6379/0
