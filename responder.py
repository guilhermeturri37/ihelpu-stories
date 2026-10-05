#!/usr/bin/env python3
"""Responde no Direct quem reagiu ou respondeu a um story de seminovo.

Regra de convivencia: age SOMENTE das 9h as 18h. Das 18h01 as 8h59 a resposta
automatica nativa do Instagram assume e direciona para o WhatsApp da central —
se os dois respondessem, a pessoa receberia duas mensagens automaticas seguidas.

Nao tenta vender nem conduzir a conversa: entrega os dados do aparelho que a
pessoa viu e passa o bastao para quem atende. Responde UMA vez por pessoa por
story, nunca insiste.

Nota: a curtida de story (o coracao) NAO existe na API — e privada por design.
So reacoes com emoji e respostas de texto chegam como mensagem no Direct.
"""
import json, os, pathlib, subprocess, sys, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

RAIZ = pathlib.Path(__file__).parent
BRT = timezone(timedelta(hours=-3))
IG_USER_ID = os.environ.get("IG_USER_ID", "17841400093603178")
TOKEN = os.environ["IG_ACCESS_TOKEN"]
ANON = os.environ["SUPABASE_ANON_KEY"]
SUPA = "https://tegdgtovwhbhsrbkxvog.supabase.co"
API = "https://graph.facebook.com/v21.0"

HORA_ABRE, HORA_FECHA = 9, 18        # atendimento humano; fora disso o IG nativo assume
JANELA_HORAS = 24                    # so olha conversas movimentadas nas ultimas 24h

def log(m): print(m, flush=True)

def get(path, **params):
    params["access_token"] = TOKEN
    url = f"{API}/{path}?" + urllib.parse.urlencode(params)
    try:
        return json.load(urllib.request.urlopen(url, timeout=60))
    except urllib.error.HTTPError as e:
        return {"__erro__": json.loads(e.read().decode()).get("error", {})}

def post(path, payload):
    req = urllib.request.Request(f"{API}/{path}",
        data=json.dumps({**payload, "access_token": TOKEN}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        return {"__erro__": json.loads(e.read().decode()).get("error", {})}

def anuncios_ativos():
    req = urllib.request.Request(f"{SUPA}/rest/v1/rpc/get_public_active_devices",
        data=b"{}", headers={"apikey": ANON, "Authorization": f"Bearer {ANON}",
                             "Content-Type": "application/json"})
    return {a["id"]: a for a in json.load(urllib.request.urlopen(req, timeout=60))}

def id_do_story(msg):
    """O campo que marca 'isto responde a um story' varia entre versoes da API.
    Aceita os formatos conhecidos em vez de depender de um so."""
    for caminho in (("story", "id"), ("reply_to", "story", "id")):
        v = msg
        for k in caminho:
            v = v.get(k) if isinstance(v, dict) else None
            if v is None: break
        if v: return v
    return None

def texto(aparelho, modelo):
    if aparelho is None:          # saiu do catalogo entre o story e a resposta
        return (f"Oi! Esse {modelo} que apareceu no story já saiu do nosso catálogo. "
                f"Mas chegam aparelhos novos toda semana — me diz o que você procura "
                f"que eu vejo o que temos agora 😊")
    preco = f"R$ {int(aparelho['asking_price']):,}".replace(",", ".")
    cap = aparelho.get("capacity") or aparelho.get("storage") or ""
    bat = aparelho.get("battery_health")
    linha_bat = f" Bateria em {bat}%." if isinstance(bat, int) and bat > 0 else ""
    return (f"Oi! Esse é o {modelo}{' ' + cap if cap else ''} — {preco} à vista no Pix, "
            f"com laudo técnico e garantia iHelpU.{linha_bat} Parcelamos em até 18x no cartão.\n\n"
            f"Quer saber mais alguma coisa sobre ele, ou prefere agendar pra ver na loja?")

def main():
    agora = datetime.now(BRT)
    forcar = os.environ.get("FORCAR") == "1"
    log(f"== {agora:%Y-%m-%d %H:%M} BRT ==")

    if not forcar and not (HORA_ABRE <= agora.hour < HORA_FECHA):
        return log(f"ignorado: {agora.hour}h fora do atendimento "
                   f"({HORA_ABRE}h-{HORA_FECHA}h). A resposta nativa do Instagram assume.")

    stories = {p["story_id"]: p for p in
               json.loads((RAIZ / "publicados.json").read_text())["publicados"]
               if p.get("story_id")}
    respondidos = json.loads((RAIZ / "respondidos.json").read_text())["respondidos"] \
                  if (RAIZ / "respondidos.json").exists() else []
    ja = {(r["conversa"], r["story_id"]) for r in respondidos}

    convs = get(f"{IG_USER_ID}/conversations", fields="id,updated_time", limit=50)
    if "__erro__" in convs:
        sys.exit(f"nao consegui ler as conversas: {convs['__erro__'].get('message')}")
    corte = datetime.now(timezone.utc) - timedelta(hours=JANELA_HORAS)
    recentes = [c for c in convs.get("data", [])
                if c.get("updated_time", "") >= corte.strftime("%Y-%m-%dT%H:%M:%S")]
    log(f"   {len(recentes)} conversas movimentadas nas ultimas {JANELA_HORAS}h")

    ativos = anuncios_ativos()
    enviadas = 0
    for c in recentes:
        det = get(c["id"], fields="messages{id,from,message,created_time,story,reply_to}")
        msgs = (det.get("messages") or {}).get("data", []) if "__erro__" not in det else []
        for m in msgs:
            if (m.get("from") or {}).get("id") == IG_USER_ID:
                continue                                  # mensagem nossa
            sid = id_do_story(m)
            if not sid or sid not in stories:
                continue                                  # nao e resposta a story nosso
            if (c["id"], sid) in ja:
                continue                                  # ja respondemos esta
            reg = stories[sid]
            msg = texto(ativos.get(reg.get("device_id")), reg.get("modelo"))
            r = post(f"{IG_USER_ID}/messages",
                     {"recipient": {"id": (m.get("from") or {}).get("id")},
                      "message": {"text": msg}})
            if "__erro__" in r:
                log(f"   falhou para {reg.get('modelo')}: {r['__erro__'].get('message')}")
                continue
            log(f"   respondido: {reg.get('modelo')} (story {sid})")
            respondidos.append({"conversa": c["id"], "story_id": sid,
                                "modelo": reg.get("modelo"),
                                "em": datetime.now(timezone.utc).isoformat(timespec="seconds")})
            enviadas += 1
            break                                         # uma resposta por conversa por rodada

    log(f"   {enviadas} resposta(s) enviada(s)")
    if enviadas:
        (RAIZ / "respondidos.json").write_text(
            json.dumps({"respondidos": respondidos}, indent=2, ensure_ascii=False) + "\n")
        for args in (["add", "respondidos.json"],
                     ["commit", "-m", f"Responde {enviadas} reacao(oes) de story"]):
            subprocess.run(["git", *args], cwd=RAIZ, check=True, capture_output=True)
        subprocess.run(["git", "push"], cwd=RAIZ, capture_output=True)

if __name__ == "__main__":
    main()
