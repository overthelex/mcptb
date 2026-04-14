#!/bin/bash
# Watches /tmp/sent_queue/ for .eml files and saves them to IMAP Sent via doveadm
QUEUE_DIR="/tmp/sent_queue"
mkdir -p "$QUEUE_DIR"

while true; do
    for f in "$QUEUE_DIR"/*.eml; do
        [ -f "$f" ] || continue
        if ssh -o ConnectTimeout=5 mail "sudo doveadm save -u vladimir@legal.org.ua -m 'Sent Messages'" < "$f" 2>/dev/null; then
            rm "$f"
        fi
    done
    sleep 5
done
