#!/usr/bin/env python3
"""Publica o story de teste no @ihelpuoficial.
O token e lido do 1Password na hora — nao fica escrito em lugar nenhum."""
import json, subprocess, sys, time, urllib.request, urllib.error

IG_USER_ID = "17841400093603178"          # @ihelpuoficial
ARTE = ("https://raw.githubusercontent.com/guilhermeturri37/ihelpu-stories"
        "/main/artes/teste-2026-09-21.png")
COFRE = "op://iHelpU-Core/Instagram-Stories-Marketplace/credential"

def token():
    r = subprocess.run(["op", "read", COFRE], capture_output=True, text=True)
    t = r.stdout.strip()
    if not t:
        sys.exit(f"nao consegui ler o token do 1Password: {r.stderr.strip()}")
    return t

def chamar(path, payload=None, tok=None, metodo="POST"):
    if metodo == "POST":
        req = urllib.request.Request(
            f"https://graph.facebook.com/v21.0/{path}",
            data=json.dumps({**payload, "access_token": tok}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
    else:
        req = urllib.request.Request(
            f"https://graph.facebook.com/v21.0/{path}&access_token={tok}")
    try:
        return json.load(urllib.request.urlopen(req, timeout=90))
    except urllib.error.HTTPError as e:
        err = json.loads(e.read().decode()).get("error", {})
        sys.exit(f"FALHOU: {err.get('message')} (code {err.get('code')})")

t = token()

print("1/3  criando o container da midia...")
c = chamar(f"{IG_USER_ID}/media", {"media_type": "STORIES", "image_url": ARTE}, t)
cid = c["id"]
print(f"     container {cid}")

# O Instagram processa a midia de forma assincrona. Publicar antes de
# terminar devolve "Media ID is not available" (code 9007).
print("2/3  esperando o Instagram processar a imagem...")
for tentativa in range(1, 31):
    s = chamar(f"{cid}?fields=status_code,status", tok=t, metodo="GET")
    estado = s.get("status_code")
    print(f"     [{tentativa:>2}] {estado}")
    if estado == "FINISHED":
        break
    if estado in ("ERROR", "EXPIRED"):
        sys.exit(f"container falhou: {s.get('status')}")
    time.sleep(3)
else:
    sys.exit("tempo esgotado: o container nao ficou pronto em 90s")

print("3/3  publicando no perfil...")
r = chamar(f"{IG_USER_ID}/media_publish", {"creation_id": cid}, t)
print(f"\n>>> STORY PUBLICADO  (id {r['id']})")
print(">>> confira em https://instagram.com/ihelpuoficial")
