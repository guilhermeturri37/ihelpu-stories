#!/usr/bin/env python3
"""Inspeciona o Direct sem enviar nada. Responde duas perguntas que so dados
reais respondem: o token le as conversas, e qual campo marca 'isto responde a
um story' nesta versao da API."""
import json, os, urllib.parse, urllib.request, urllib.error

IG = os.environ.get("IG_USER_ID", "17841400093603178")
T = os.environ["IG_ACCESS_TOKEN"]
API = "https://graph.facebook.com/v21.0"

def get(path, **p):
    p["access_token"] = T
    try:
        return json.load(urllib.request.urlopen(f"{API}/{path}?" + urllib.parse.urlencode(p), timeout=60))
    except urllib.error.HTTPError as e:
        return {"__erro__": json.loads(e.read().decode()).get("error", {})}

print("1) LENDO CONVERSAS")
c = get(f"{IG}/conversations", fields="id,updated_time", limit=15)
if "__erro__" in c:
    e = c["__erro__"]
    print(f"   ERRO: {e.get('message')} | code {e.get('code')} | subcode {e.get('error_subcode')}")
    raise SystemExit(1)
convs = c.get("data", [])
print(f"   OK — {len(convs)} conversas")

print("\n2) PROCURANDO RESPOSTAS A STORY")
achou = 0
for conv in convs[:10]:
    d = get(conv["id"], fields="messages{id,from,message,created_time,story,reply_to}")
    if "__erro__" in d:
        print(f"   erro ao ler conversa: {d['__erro__'].get('message')}")
        continue
    for m in (d.get("messages") or {}).get("data", [])[:8]:
        tem = [k for k in ("story", "reply_to") if m.get(k)]
        if not tem:
            continue
        achou += 1
        print(f"   mensagem {m.get('id','')[:18]} de {m.get('created_time','')[:16]}")
        for k in tem:
            print(f"      campo '{k}' = {json.dumps(m[k], ensure_ascii=False)[:220]}")
        if achou >= 5:
            break
    if achou >= 5:
        break
if not achou:
    print("   nenhuma resposta a story nas conversas recentes.")
    print("   peca para alguem reagir com emoji a um story e rode de novo.")
