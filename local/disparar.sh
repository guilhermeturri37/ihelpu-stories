#!/bin/bash
# Rede de seguranca: dispara o workflow no GitHub nos horarios de publicacao.
# Existe porque o cron do GitHub Actions nao disparou nenhuma vez em 22/09/2026,
# apesar da configuracao valida. Rodar os dois em paralelo e seguro: o
# publicados.json controla a meta diaria, entao um disparo a mais nao publica
# um story a mais.
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"
LOG="$HOME/Desktop/ihelpu-stories/local/disparos.log"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] disparando..." >> "$LOG"
if gh workflow run "Story do marketplace" --repo guilhermeturri37/ihelpu-stories >> "$LOG" 2>&1; then
  echo "[$(date '+%H:%M:%S')] ok" >> "$LOG"
else
  echo "[$(date '+%H:%M:%S')] FALHOU" >> "$LOG"
fi
