#!/usr/bin/env bash
#
# Stop Consularis dev servers (frontend on 5173 or 5174, backend on 8000).
# Use this if you started them manually or in another terminal.
#
set -e

echo "Stopping Consularis dev servers..."

for port in 5173 5174 5175 8000; do
  pid=$(lsof -ti ":$port" 2>/dev/null || true)
  if [[ -n "$pid" ]]; then
    echo "  Killing process on port $port (PID $pid)"
    kill $pid 2>/dev/null || true
  else
    echo "  Nothing running on port $port"
  fi
done

echo "Done."
