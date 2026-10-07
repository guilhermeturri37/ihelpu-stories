#!/usr/bin/env python3
"""Publica no Status do WhatsApp das lojas um iPhone do marketplace, pela Evolution API.

4 por dia em cada numero (8h10, 10h10, 12h10 e 14h10 — dez minutos depois do story do
Instagram), de segunda a sabado. Pedido do Guilherme em 07/10/2026. Usa a mesma arte dos
stories (template_v2.html), trocando o CTA. Cada loja mostra primeiro os aparelhos que
estao nela ("retire hoje na loja X"); o que faltar vem do estoque geral.

Variaveis de ambiente:
  PREVIA=1          so gera a proxima arte de cada instancia em previa/ — nao envia nada
  TESTE_PARA=55...  envia SO para esse numero (statusJidList), sem registrar
  INSTANCIAS=a,b    restringe a rodada a essas instancias (padrao: ATIVAS)
  FORCAR=1          ignora horario, domingo e a trava de "ja saiu neste horario"

A Evolution e uma API NAO oficial e estes sao os numeros de atendimento das lojas. Uma
loja por vez, com pausa entre elas; nao transformar isto num disparo em massa.
"""
import json, os, pathlib, re, subprocess, sys, time, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone

os.environ.setdefault("IG_ACCESS_TOKEN", "")      # o publicar.py exige a variavel ao importar
import publicar as P

RAIZ = pathlib.Path(__file__).parent
EVO = os.environ.get("EVOLUTION_URL", "https://evolutionapi.ihelpu.com.br")
REGISTRO = RAIZ / "status_whatsapp.json"
RAW = "https://raw.githubusercontent.com/guilhermeturri37/ihelpu-stories"
HORARIOS = [8, 10, 12, 14]
PAUSA = 45                      # segundos entre uma loja e a seguinte
DIAS_CONVERSA = 60              # o Status vai para quem conversou com a loja nesse prazo
# instancia da Evolution -> (loja no marketplace, nome que vai na arte). A central nao tem
# loja: mostra o estoque geral. Em ordem crescente de contatos guardados (07/10/2026).
LOJAS = {
    "SAO LEOPOLDO 2":      ("sao-leopoldo", "São Leopoldo"),
    "iHelpU Corp Emerson": (None, None),
    "TREND2":              ("trend", "Trend"),
    "ZONASUL":             ("zona-sul", "Zona Sul"),
    "SANTAMARIA":          ("santa-maria", "Santa Maria"),
    "ZONA NORTE 2":        ("zona-norte", "Zona Norte"),
    "NOVO HAMBURGO":       ("novo-hamburgo", "Novo Hamburgo"),
    "Caxias do Sul":       ("caxias-do-sul", "Caxias do Sul"),
    "CANOAS":              ("canoas", "Canoas"),
    "PELOTAS2":            ("pelotas", "Pelotas"),
}
# Quem ja esta no automatico. O envio para TODOS os contatos so foi medido nas menores;
# as de 13 mil contatos ou mais entram depois de ver quanto tempo essas levam.
ATIVAS = ["SAO LEOPOLDO 2", "iHelpU Corp Emerson", "TREND2"]

def fila(instancia, registro, ativos, hoje):
    """iPhones da propria loja primeiro, depois o estoque geral. Em cada grupo, inedito
    nesta instancia (mais novo antes) e depois o que saiu ha mais tempo. Nunca o mesmo
    aparelho duas vezes no dia no mesmo numero."""
    meus = [p for p in registro["publicados"] if p["instancia"] == instancia]
    ultima = {p["device_id"]: p["em"] for p in meus}
    de_hoje = {p["device_id"] for p in meus if P.dia_e_horario(p)[0] == hoje}
    aptos = [a for a in ativos if a.get("category") == "iphone" and (a.get("asking_price") or 0) > 0
             and P.foto_de(a) and a["id"] not in de_hoje]
    def ordem(grupo):
        ineditos = sorted([a for a in grupo if a["id"] not in ultima], key=lambda a: a["created_at"], reverse=True)
        return ineditos + sorted([a for a in grupo if a["id"] in ultima], key=lambda a: ultima[a["id"]])
    slug = LOJAS[instancia][0]
    return ordem([a for a in aptos if a.get("preferred_store") == slug]) + \
           ordem([a for a in aptos if a.get("preferred_store") != slug])

def arte(instancia, a, registro, destino):
    slug, nome = LOJAS[instancia]
    na_loja = slug and a.get("preferred_store") == slug
    banco = P.foto_do_banco(a, registro)
    P.montar_arte_iphone(a, destino, banco, cta="Responda este status",
                         retirada=f"Retire hoje na loja {nome}" if na_loja else "Retire ainda hoje")
    return banco

def publicar_artes(arquivos):
    """Poe as artes num commit solto no ramo artes-status (push forcado) e devolve o sha.
    A Evolution so aceita imagem por URL. Ramo proprio e sem historico: sao ate 40 artes de
    1 MB por dia, que na main fariam o repositorio crescer mais de 1 GB por mes."""
    def git(*args, entrada=None):
        return subprocess.run(["git", *args], cwd=RAIZ, check=True, capture_output=True,
                              text=True, input=entrada).stdout.strip()
    linhas = "".join(f"100644 blob {git('hash-object', '-w', str(arq))}\t{arq.name}\n" for arq in arquivos)
    commit = git("commit-tree", git("mktree", entrada=linhas), "-m", "Artes do Status do WhatsApp")
    git("push", "-f", "origin", f"{commit}:refs/heads/artes-status")
    return commit

def destinatarios(instancia):
    """Quem recebe o Status: os numeros com quem a loja trocou mensagem nos ultimos
    DIAS_CONVERSA dias. Nao e `allContacts` de proposito (decisao do Guilherme, 07/10/2026): a
    Evolution 2.3.7 reenvia a imagem inteira a cada 10 destinatarios (~0,13 s por
    destinatario) e "todos os contatos" vai de 494 a 20.875 conforme a loja — a Trend levou
    884 s e Pelotas levaria 47 min, quatro vezes ao dia, no numero de atendimento. O
    WhatsApp so mostra Status a quem tem o numero da loja salvo; conversa recente e a melhor
    aproximacao disso, e deixa as dez lojas entre 500 e 1.100 destinatarios.
    Conversa que a Evolution so conhece pelo @lid (sem telefone em `remoteJidAlt`) fica de fora."""
    req = urllib.request.Request(f"{EVO}/chat/findChats/{urllib.parse.quote(instancia)}",
        data=b"{}", method="POST",
        headers={"apikey": os.environ["EVOLUTION_API_KEY"], "Content-Type": "application/json"})
    desde = time.time() - DIAS_CONVERSA * 86400
    jids = set()
    for c in json.load(urllib.request.urlopen(req, timeout=300)):
        ultima = c.get("lastMessage") or {}
        if int(ultima.get("messageTimestamp") or 0) < desde:
            continue
        for jid in (c.get("remoteJid"), (ultima.get("key") or {}).get("remoteJidAlt")):
            if re.fullmatch(r"\d+@s\.whatsapp\.net", jid or ""):
                jids.add(jid)
                break
    return sorted(jids)

def enviar(instancia, url_arte, legenda, jids):
    """Devolve ("ok", id), ("recusado", motivo) ou ("incerto", motivo). Incerto = o pedido
    saiu e nao da para saber se o Status foi ao ar (tempo esgotado, erro do servidor)."""
    # `content` tem de ser URL: a Evolution 2.3.7 trata o valor como caminho de arquivo e
    # base64 volta "ENAMETOOLONG: name too long".
    # `statusJidList` vazio volta HTTP 400 ("does not meet minimum length of 1", 07/10/2026
    # 14h10, as 3 lojas): quem chama nao envia sem destinatario.
    corpo = {"type": "image", "content": url_arte, "caption": legenda, "statusJidList": jids}
    req = urllib.request.Request(f"{EVO}/message/sendStatus/{urllib.parse.quote(instancia)}",
        data=json.dumps(corpo).encode(), method="POST",
        headers={"apikey": os.environ["EVOLUTION_API_KEY"], "Content-Type": "application/json"})
    try:
        # A Evolution so responde quando termina de enviar, e leva ~0,13 s por destinatario
        # (reenvia a imagem a cada 10): com `allContacts` a Trend, com 6.544, levou 884 s em
        # 07/10/2026. Com a lista de destinatarios() a espera normal e de 1 a 3 min.
        r = json.load(urllib.request.urlopen(req, timeout=2400))
        return "ok", (r.get("key") or {}).get("id")
    except urllib.error.HTTPError as e:
        motivo = f"HTTP {e.code} {e.read().decode()[:200]}"
        return ("recusado" if 400 <= e.code < 500 else "incerto"), motivo
    except Exception as e:
        return "incerto", f"{type(e).__name__}: {e}"

def main():
    agora = datetime.now(P.BRT)
    hora, hoje = agora.hour, agora.strftime("%Y-%m-%d")
    forcar = os.environ.get("FORCAR") == "1"
    previa = os.environ.get("PREVIA") == "1"
    so_para = os.environ.get("TESTE_PARA", "").strip() or None
    pedidas = [i.strip() for i in os.environ.get("INSTANCIAS", "").split(",") if i.strip()] or ATIVAS
    fora = [i for i in pedidas if i not in LOJAS]
    if fora:
        sys.exit(f"instancia desconhecida: {fora}; conhecidas: {list(LOJAS)}")
    P.log(f"== {agora:%Y-%m-%d %H:%M} BRT — Status do WhatsApp ==")
    if not (previa or forcar or so_para):
        if agora.weekday() == 6:
            return P.ignorar("domingo", "domingo nao publica (segunda a sabado)")
        if hora not in HORARIOS:
            return P.ignorar("fora_da_janela", f"{hora}h fora dos horarios {HORARIOS}")
        try:
            subprocess.run(["git", "pull", "--rebase", "-q"], cwd=RAIZ, check=True, capture_output=True, timeout=120)
        except Exception as e:
            P.log(f"   aviso: nao consegui sincronizar antes de decidir ({e})")

    registro = json.loads(REGISTRO.read_text()) if REGISTRO.exists() else {"publicados": []}
    ativos = P.anuncios_ativos()
    pasta = RAIZ / ("previa" if previa else "_status")
    pasta.mkdir(exist_ok=True)
    rodada = []                                   # (instancia, anuncio, arquivo da arte, foto do banco)
    for inst in pedidas:
        feito = any(p["instancia"] == inst and P.dia_e_horario(p) == (hoje, hora) for p in registro["publicados"])
        if feito and not (previa or forcar or so_para):
            P.log(f"   {inst}: horario {hora}h ja publicado hoje")
            continue
        candidatos = fila(inst, registro, ativos, hoje)
        if not candidatos:
            P.log(f"   {inst}: nenhum iPhone disponivel que ainda nao saiu hoje")
            continue
        a = candidatos[0]
        nome = f"{'status' if previa else agora.strftime('%Y%m%d-%H%M')}-{re.sub(r'[^a-z0-9]', '', inst.lower())}-{a['id'][:8]}.png"
        banco = arte(inst, a, registro, pasta / nome)
        rodada.append((inst, a, pasta / nome, banco))
        P.log(f"   {inst}: {a.get('model')} ({a.get('preferred_store')}) — {banco['arquivo'] if banco else 'foto do anuncio'}")
    if previa or not rodada:
        return

    commit = publicar_artes([arq for _, _, arq, _ in rodada])
    falhas = 0
    for n, (inst, a, arq, banco) in enumerate(rodada):
        if n:
            time.sleep(PAUSA)
        preco = format(int(a["asking_price"]), ",d").replace(",", ".")
        legenda = " ".join(f"{a.get('model')} {a.get('capacity') or ''} por R$ {preco} no Pix. "
                           "Responda este status e fale com a gente.".split())
        inicio = time.time()
        try:
            jids = [f"{so_para}@s.whatsapp.net"] if so_para else destinatarios(inst)
            estado, detalhe = enviar(inst, f"{RAW}/{commit}/{arq.name}", legenda, jids) if jids else \
                ("recusado", f"ninguem conversou com a loja nos ultimos {DIAS_CONVERSA} dias")
        except Exception as e:                    # a lista nao veio: nada foi enviado
            jids, estado, detalhe = [], "recusado", f"nao consegui a lista de destinatarios ({type(e).__name__}: {e})"
        P.log(f"   >>> {inst}: {estado} em {time.time() - inicio:.0f}s, {len(jids)} destinatarios — {detalhe}"
              + (f" (TESTE para {so_para})" if so_para else ""))
        arq.unlink()
        if estado != "ok":
            falhas += 1
            P.anotar("status", f"{estado} | {inst} | {detalhe}", nivel="warning")
        if so_para or estado == "recusado":
            continue                              # teste nao entra no registro; recusado pode repetir
        item = {"instancia": inst, "device_id": a["id"], "modelo": a.get("model"),
                "em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "horario": hora,
                "destinatarios": len(jids)}
        if banco:
            item["foto"] = banco["arquivo"]
        if estado == "incerto":
            item["estado"] = "incerto"            # fica registrado para nao reenviar em dobro
        registro["publicados"].append(item)
        # Grava e sobe a cada loja, nao so no fim: a rodada leva minutos (a Trend levou 884 s)
        # e, se cair no meio, um novo disparo reenviaria para quem ja tinha recebido.
        REGISTRO.write_text(json.dumps(registro, indent=2, ensure_ascii=False) + "\n")
        P.git("add", REGISTRO.name)
        if P.git_commit(f"Registra Status: {inst} ({hoje} {hora:02d}h)"):
            P.git_push()
    if falhas:
        sys.exit(f"{falhas} envio(s) nao confirmados; ver os avisos acima")

if __name__ == "__main__":
    main()
