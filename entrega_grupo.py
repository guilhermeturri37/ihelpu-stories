#!/usr/bin/env python3
"""Entrega no grupo "iHelpU Todas" as artes do dia, para cada loja postar no Status pelo celular.

Pedido do Guilherme em 13/10/2026, combinado com os gerentes: o Status publicado pelo
WhatsApp do celular vai para a agenda inteira da loja (o automatico da Evolution so alcanca
quem conversou nos ultimos 60 dias — ver status_whatsapp.py). O robo monta as artes e entrega;
quem posta e o gerente.

Todo dia as 8h30, de segunda a sabado: POR_LOJA artes por loja, sempre separadas por loja —
um texto com o nome da loja e, em seguida, as artes dela. Quem envia e o numero da central;
se ele estiver desconectado, a instancia "andre" (REMETENTES).
A legenda de cada imagem e a que vai ao cliente: ela acompanha a imagem quando o gerente
encaminha para "Meu status". O nome da loja NAO vai na legenda por isso.

Variaveis de ambiente:
  PREVIA=1          so gera as artes em previa/ — nao envia nada
  TESTE_PARA=55...  envia para esse numero em vez do grupo, sem registrar
  INSTANCIAS=a,b    restringe a essas lojas (padrao: todas)
  FORCAR=1          ignora horario e domingo (a trava de "ja entregue hoje" continua valendo)
"""
import json, os, pathlib, sys, time, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone

os.environ.setdefault("IG_ACCESS_TOKEN", "")      # o publicar.py exige a variavel ao importar
import publicar as P
import status_whatsapp as S

RAIZ = pathlib.Path(__file__).parent
REGISTRO = RAIZ / "entrega_grupo.json"
GRUPO = "120363431408903236@g.us"       # "iHelpU Todas": os numeros das lojas e a central
# Quem envia, em ordem: a central e, se ela estiver desconectada, a instancia "andre" (pedido do
# Guilherme em 19/10/2026: a central caiu em 15/10 com 401 e as entregas de 16, 17 e 19/10
# falharam inteiras com "Connection Closed", sem ninguem perceber). As duas estao no grupo.
REMETENTES = ["iHelpU Corp Emerson", "andre"]
remetente = REMETENTES[0]
POR_LOJA = 5
HORA = 8                                # a entrega e as 8h30; fora da hora 8 o pedido e ignorado
RAMO = "artes-grupo"                    # proprio: o artes-status e do Status automatico
PAUSA = 2                               # segundos entre uma mensagem e a seguinte

def conectado(instancia):
    try:
        req = urllib.request.Request(f"{S.EVO}/instance/connectionState/{urllib.parse.quote(instancia)}",
                                     headers={"apikey": os.environ["EVOLUTION_API_KEY"]})
        return json.load(urllib.request.urlopen(req, timeout=60))["instance"]["state"] == "open"
    except Exception:
        return False

def evo(caminho, corpo):
    """("ok", id) ou ("erro", motivo). Se o remetente cair no meio da entrega, passa para o
    proximo de REMETENTES e reenvia a mesma mensagem."""
    global remetente
    while True:
        estado, detalhe = enviar(remetente, caminho, corpo)
        if estado == "ok" or "Connection Closed" not in detalhe or remetente == REMETENTES[-1]:
            return estado, detalhe
        reserva = REMETENTES[REMETENTES.index(remetente) + 1]
        P.anotar("grupo", f"{remetente} desconectada no meio da entrega; seguindo pela {reserva}", nivel="warning")
        remetente = reserva

def enviar(instancia, caminho, corpo):
    """Mensagem comum para um grupo: sem a lista de destinatarios do Status, entao a resposta
    vem em segundos."""
    req = urllib.request.Request(f"{S.EVO}/{caminho}/{urllib.parse.quote(instancia)}",
        data=json.dumps(corpo).encode(), method="POST",
        headers={"apikey": os.environ["EVOLUTION_API_KEY"], "Content-Type": "application/json"})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=180))
        return "ok", (r.get("key") or {}).get("id")
    except urllib.error.HTTPError as e:
        return "erro", f"HTTP {e.code} {e.read().decode()[:200]}"
    except Exception as e:
        return "erro", f"{type(e).__name__}: {e}"

def escolher(instancia, registro, ativos, hoje):
    """Os POR_LOJA aparelhos do dia: a fila do Status (os da propria loja primeiro, inedito
    antes de reprise), pulando modelo repetido enquanto houver outro — cinco iPhone 13
    seguidos nao e variedade. Se faltar, completa com os repetidos."""
    fila = S.fila(instancia, registro, ativos, hoje)
    variados, modelos = [], set()
    for a in fila:
        if a.get("model") not in modelos:
            variados.append(a)
            modelos.add(a.get("model"))
    resto = [a for a in fila if a not in variados]
    return (variados + resto)[:POR_LOJA]

def para_jpeg(png):
    """JPEG pesa um quinto do PNG, e sao 50 imagens por dia no celular de cada gerente. Sem
    Pillow (rodando na mao, fora do workflow) a arte segue em PNG."""
    try:
        from PIL import Image
    except ImportError:
        return png
    jpg = png.with_suffix(".jpg")
    Image.open(png).convert("RGB").save(jpg, "JPEG", quality=90)
    png.unlink()
    return jpg

def main():
    agora = datetime.now(P.BRT)
    hoje = agora.strftime("%Y-%m-%d")
    forcar = os.environ.get("FORCAR") == "1"
    previa = os.environ.get("PREVIA") == "1"
    teste = os.environ.get("TESTE_PARA", "").strip() or None
    pedidas = [i.strip() for i in os.environ.get("INSTANCIAS", "").split(",") if i.strip()] or list(S.LOJAS)
    fora = [i for i in pedidas if i not in S.LOJAS]
    if fora:
        sys.exit(f"instancia desconhecida: {fora}; conhecidas: {list(S.LOJAS)}")
    P.log(f"== {agora:%Y-%m-%d %H:%M} BRT — artes do Status para o grupo ==")
    if not (previa or forcar or teste):
        if agora.weekday() == 6:
            return P.ignorar("domingo", "domingo nao entrega (segunda a sabado)")
        if agora.hour != HORA:
            return P.ignorar("fora_da_janela", f"{agora.hour}h fora da hora da entrega ({HORA}h)")
    if not (previa or teste):
        try:
            P.git("pull", "--rebase", "-q")
        except Exception as e:
            P.log(f"   aviso: nao consegui sincronizar antes de decidir ({e})")

    registro = json.loads(REGISTRO.read_text()) if REGISTRO.exists() else {"publicados": []}
    ativos = P.anuncios_ativos()
    pasta = RAIZ / ("previa" if previa else "_grupo")
    pasta.mkdir(exist_ok=True)
    rodizio = {"publicados": list(registro["publicados"])}   # as fotos do banco se revezam dentro da entrega
    blocos = []                                             # (instancia, [(anuncio, arquivo, foto do banco)])
    for inst in pedidas:
        if not (previa or teste) and any(p["instancia"] == inst and P.dia_e_horario(p)[0] == hoje
                                         for p in registro["publicados"]):
            P.log(f"   {inst}: ja entregue hoje")
            continue
        itens = []
        for n, a in enumerate(escolher(inst, registro, ativos, hoje), 1):
            slug = "".join(c for c in inst.lower() if c.isalnum())
            arq = pasta / f"{hoje.replace('-', '')}-{slug}-{n}-{a['id'][:8]}.png"
            banco = S.arte(inst, a, rodizio, arq)
            rodizio["publicados"].append({"foto": banco["arquivo"]} if banco else {})
            itens.append((a, para_jpeg(arq), banco))
        P.log(f"   {inst}: " + (", ".join(f"{a.get('model')} R$ {P.preco(a)}" for a, _, _ in itens) or "nenhum iPhone disponivel"))
        if itens:
            blocos.append((inst, itens))
    if previa or not blocos:
        return

    urls = dict(zip([arq.name for _, itens in blocos for _, arq, _ in itens],
                    P.subir_artes([arq for _, itens in blocos for _, arq, _ in itens], RAMO)))
    global remetente
    remetente = next((r for r in REMETENTES if conectado(r)), REMETENTES[0])
    if remetente != REMETENTES[0]:
        P.anotar("grupo", f"{REMETENTES[0]} desconectada; a entrega sai pela {remetente}", nivel="warning")
    P.log(f"   remetente: {remetente}")
    destino = teste or GRUPO
    dia = agora.strftime("%d/%m")
    falhas = 0
    if teste or not any(P.dia_e_horario(p)[0] == hoje for p in registro["publicados"]):
        evo("message/sendText", {"number": destino, "text":
            f"Bom dia! Artes de hoje ({dia}) para o Status de cada loja.\n"
            "Para postar: abra a imagem, toque em Encaminhar e escolha *Meu status*. "
            "Cada loja posta as suas."})
        time.sleep(PAUSA)
    for inst, itens in blocos:
        nome = S.LOJAS[inst][1] or "Central"
        estado, detalhe = evo("message/sendText", {"number": destino, "text": f"*{nome.upper()}* — {len(itens)} artes de hoje ({dia})"})
        enviados = []
        if estado == "ok":
            for a, arq, banco in itens:
                time.sleep(PAUSA)
                legenda = " ".join(f"{a.get('model')} {a.get('capacity') or ''} por R$ {P.preco(a)} no Pix. "
                                   "Responda este status e fale com a gente.".split())
                estado, detalhe = evo("message/sendMedia", {"number": destino, "mediatype": "image",
                    "mimetype": "image/jpeg" if arq.suffix == ".jpg" else "image/png",
                    "media": urls[arq.name], "fileName": arq.name, "caption": legenda})
                if estado == "ok":
                    enviados.append((a, banco))
                else:
                    P.anotar("grupo", f"arte nao enviada | {inst} | {a.get('model')} | {detalhe}", nivel="warning")
        else:
            P.anotar("grupo", f"loja nao entregue | {inst} | {detalhe}", nivel="warning")
        P.log(f"   >>> {inst}: {len(enviados)} de {len(itens)} artes entregues"
              + (f" (TESTE para {teste})" if teste else ""))
        falhas += len(itens) - len(enviados)
        for _, arq, _ in itens:
            arq.unlink()
        if teste or not enviados:
            continue                              # teste nao entra no registro; loja sem nada pode repetir
        for a, banco in enviados:
            item = {"instancia": inst, "device_id": a["id"], "modelo": a.get("model"),
                    "em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "horario": HORA}
            if banco:
                item["foto"] = banco["arquivo"]
            registro["publicados"].append(item)
        # Grava e sobe a cada loja: se a rodada cair no meio, um novo pedido so entrega as que faltam.
        REGISTRO.write_text(json.dumps(registro, indent=2, ensure_ascii=False) + "\n")
        P.git("add", REGISTRO.name)
        if P.git_commit(f"Registra entrega no grupo: {inst} ({hoje})"):
            P.git_push()
        time.sleep(PAUSA)
    if falhas:
        sys.exit(f"{falhas} arte(s) nao entregues; ver os avisos acima")

if __name__ == "__main__":
    main()
