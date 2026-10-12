#!/usr/bin/env bash
# Abre um túnel HTTPS público (Cloudflare Quick Tunnel) para o Next em :3000.
# O celular acessa o site e a API (/api) pelo mesmo endereço, inclusive no 4G.
set -e
PORTA="${1:-3000}"
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "Instalando cloudflared..."
  ARQ=$(dpkg --print-architecture)   # amd64 ou arm64
  curl -fsSL -o /tmp/cloudflared.deb "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARQ}.deb"
  sudo dpkg -i /tmp/cloudflared.deb
fi
curl -fsS -o /dev/null "http://localhost:${PORTA}" || { echo "Nada respondendo em :${PORTA}. Rode 'npm run dev' na pasta frontend antes."; exit 1; }
echo "Abrindo túnel para http://localhost:${PORTA} (Ctrl+C encerra)..."
cloudflared tunnel --no-autoupdate --url "http://localhost:${PORTA}" 2>&1 | while IFS= read -r linha; do
  url=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' <<<"$linha" || true)
  if [ -n "$url" ]; then
    echo; echo "=============================================="
    echo " No celular abra:  ${url}/entrega"
    echo "=============================================="; echo
  fi
done
