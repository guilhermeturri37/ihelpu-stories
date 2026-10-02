#!/usr/bin/env python3
"""Publica um Story no @ihelpuoficial com um aparelho do marketplace iHelpU.

Roda no GitHub Actions; quem pede, pede de hora em hora das 9 as 13h de Brasilia, e so
as 9, 11 e 13h publicam (3/dia, pedido do Guilherme em 02/10/2026). Cada execucao decide
sozinha se publica:
  - escolhe o anuncio mais novo que ainda nao foi ao ar; nunca repete aparelho
  - 3/dia (9h, 11h, 13h) enquanto houver ineditos; se o estoque apertar, cai para 2/dia (9h e 13h)
  - pula anuncio sem foto ou sem preco em vez de publicar algo quebrado
  - um story por horario: um segundo disparo na mesma hora nao publica de novo
  - HORARIO (so com FORCAR) repoe um horario perdido de hoje e registra o story nele
  - reserva o aparelho e o horario no registro ANTES de publicar: nunca duplica story
  - anota a decisao de cada rodada (::notice title=decisao::) e avisa quando a reserva
    fica (::warning title=reserva::) — o vigia do n8n le essas anotacoes sem token

O nome do vendedor (seller_name) vem no RPC mas NUNCA entra na arte: sao
consignacoes de pessoas fisicas. Nao reintroduza esse campo.
"""
import json, os, pathlib, re, subprocess, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

RAIZ = pathlib.Path(__file__).parent
BRT = timezone(timedelta(hours=-3))          # Brasilia, sem horario de verao desde 2019

SUPA = "https://tegdgtovwhbhsrbkxvog.supabase.co"
ANON = os.environ["SUPABASE_ANON_KEY"]       # chave publica, a mesma do site
IG_USER_ID = os.environ.get("IG_USER_ID", "17841400093603178")
IG_TOKEN = os.environ["IG_ACCESS_TOKEN"]
REPO_RAW = "https://raw.githubusercontent.com/guilhermeturri37/ihelpu-stories/main"

HORARIOS_CHEIOS = [9, 11, 13]           # os pedidos das 10h e 12h caem em fora_da_janela
HORARIOS_REDUZIDOS = [9, 13]            # tem de ser subconjunto de HORARIOS_CHEIOS
META_CHEIA, META_REDUZIDA = 3, 2
# Codigos que o media_publish devolveu, medidos, para container que existia e
# estava FINISHED — "ainda nao da para publicar", nao "nunca vai dar".
PUBLISH_AINDA_NAO = {9007, 24}

COND = {"como_novo": "Como novo", "excelente": "Excelente", "bom": "Bom", "regular": "Regular"}
COM_BATERIA = {"iphone", "ipad", "macbook"}   # onde "Bateria X%" faz sentido

def log(m): print(m, flush=True)

def anotar(titulo, texto, nivel="notice"):
    """Anotacao do GitHub Actions: fica na rodada e e PUBLICA — o vigia do n8n le em
    GET <check_run_url>/annotations, sem token. Uma linha so: o runner desfaz %25, %0D e %0A
    no texto (actions/runner, ActionCommand.cs), entao escapa exatamente esses tres."""
    texto = str(texto).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::{nivel} title={titulo}::{texto}", flush=True)

def ignorar(codigo, motivo):
    """A rodada decidiu NAO publicar: a mesma linha de sempre no log, mais a decisao anotada."""
    log(f"ignorado: {motivo}")
    anotar("decisao", f"ignorado:{codigo} | {motivo}")

def ficou(onde, situacao):
    """A rodada termina com a reserva na main ("estado": "publicando"): aparelho e horario ficam
    presos ate alguem resolver, com o robo parado. Diz no log e anota para o vigia."""
    log(f"   RESERVA FICA na main ({onde}): {situacao}")
    anotar("reserva", f"fica | {onde} | {situacao}", nivel="warning")

def dia_e_horario(p):
    """Data e horario (Brasilia) que um registro ocupa. O `em` e UTC e marca quando
    o story saiu; o `horario` marca qual horario ele cobre — numa reposicao os dois
    diferem. Registro anterior ao campo `horario` usa a hora do `em`."""
    em = datetime.fromisoformat(p["em"].replace("Z", "+00:00")).astimezone(BRT)
    return em.strftime("%Y-%m-%d"), p.get("horario", em.hour)

def anuncios_ativos():
    req = urllib.request.Request(f"{SUPA}/rest/v1/rpc/get_public_active_devices",
        data=b"{}", headers={"apikey": ANON, "Authorization": f"Bearer {ANON}",
                             "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))

def foto_de(a):
    fs = a.get("photos") or []
    if not fs: return None
    return (next((f for f in fs if f.get("photo_type") == "front"), fs[0])).get("photo_url")

def montar_arte(a, destino):
    cap = a.get("capacity") or a.get("storage") or a.get("ram") or ""
    # Sem a loja de propria: o story fala com as 7 cidades ao mesmo tempo.
    specs = " · ".join([p for p in [cap, "Retire ainda hoje"] if p])
    bat = a.get("battery_health")
    mostra_bat = a.get("category") in COM_BATERIA and isinstance(bat, int) and bat > 0

    modelo = a.get("model") or a.get("title") or "Seminovo"
    # Nomes longos (iPad 10a geracao 10.9" 2022) quebravam em duas linhas e
    # comprimiam o bloco de preco. Encolhe a fonte em vez de deixar quebrar.
    fs = 82 if len(modelo) <= 16 else max(46, int(82 * 16 / len(modelo)))

    h = (RAIZ / "template.html").read_text()
    h = (h.replace("FOTO_URL", foto_de(a))
           .replace("ESTADO_LABEL", COND.get(a.get("aesthetic_condition"), "Seminovo"))
           .replace("FS_MODELO", str(fs))
           .replace("MODELO_NOME", modelo)
           .replace("ARMAZENAMENTO · Retire ainda hoje", specs)
           .replace("R$ PRECO", "R$ " + format(int(a["asking_price"]), ",d").replace(",", ".")))
    h = h.replace("BATERIA", str(bat)) if mostra_bat else \
        re.sub(r'<span class="pill badge-bat">.*?</span>', "", h, flags=re.S)

    html = RAIZ / "_arte.html"
    html.write_text(h)
    subprocess.run(["google-chrome", "--headless", "--disable-gpu", "--no-sandbox",
                    "--hide-scrollbars", f"--screenshot={destino}",
                    "--window-size=1080,1920", "--virtual-time-budget=25000", str(html)],
                   check=True, capture_output=True)
    html.unlink()
    if not destino.exists() or destino.stat().st_size < 50_000:
        sys.exit("a arte nao foi gerada corretamente")

def graph(path, payload=None, metodo="POST", tolerar=False):
    if metodo == "POST":
        req = urllib.request.Request(f"https://graph.facebook.com/v21.0/{path}",
            data=json.dumps({**payload, "access_token": IG_TOKEN}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
    else:
        req = urllib.request.Request(
            f"https://graph.facebook.com/v21.0/{path}&access_token={IG_TOKEN}")
    try:
        return json.load(urllib.request.urlopen(req, timeout=90))
    except urllib.error.HTTPError as e:
        err = json.loads(e.read().decode()).get("error", {})
        if tolerar:
            return {"__erro__": err}
        sys.exit(f"Graph API: {err.get('message')} (code {err.get('code')})")

class NaoPublicou(Exception):
    """A publicacao falhou com CERTEZA de que nenhum story saiu — a reserva pode ser liberada.
    Qualquer outra saida de erro de publicar() e 'nao da para saber': a reserva fica."""

def publicar(url_arte):
    # Tudo antes do primeiro media_publish nao publica nada: qualquer falha aqui e certeza.
    try:
        c = graph(f"{IG_USER_ID}/media", {"media_type": "STORIES", "image_url": url_arte}, tolerar=True)
        if "__erro__" in c:
            e = c["__erro__"]
            raise NaoPublicou(f"Graph API ao criar o container: {e.get('message')} (code {e.get('code')})")
        cid = c["id"]
        log(f"   container {cid}; aguardando processamento...")
        # Publicar antes de FINISHED devolve "Media ID is not available" (code 9007).
        for tentativa in range(30):
            # Logo apos criar, a Meta pode ainda nao responder consultas sobre o
            # container e devolver 9007. Isso e transitorio: e exatamente o que
            # este laco existe para esperar, entao nao pode abortar.
            r = graph(f"{cid}?fields=status_code,status", metodo="GET", tolerar=True)
            if "__erro__" in r:
                if tentativa >= 10:
                    raise NaoPublicou(f"container nao ficou consultavel: {r['__erro__'].get('message')}")
                time.sleep(3)
                continue
            estado = r.get("status_code")
            if estado == "FINISHED": break
            if estado in ("ERROR", "EXPIRED"): raise NaoPublicou(f"container falhou: {r.get('status')}")
            time.sleep(3)
        else:
            raise NaoPublicou("container nao ficou pronto em 90s")
    except NaoPublicou:
        raise
    except Exception as e:
        # QUALQUER erro antes do primeiro media_publish e certeza de que nada saiu: rede, JSON,
        # resposta cortada no meio (IncompleteRead), 200 sem `id` (cetico, rodada 3).
        raise NaoPublicou(f"falha antes de publicar: {type(e).__name__}: {e}")
    # FINISHED nao garante que o publish aceita: em 25/09 13h e 26/09 9h o status
    # veio FINISHED na primeira consulta e o media_publish, 0,6-0,7 s depois, devolveu
    # 9007; em 26/09 10h38, 0,8 s depois, devolveu 24 ("does not exist") para um
    # container que existia. A tentativa recusada NAO publica (os tres containers
    # seguem FINISHED, nao PUBLISHED), entao repetir e seguro. Outro erro sai na hora
    # e SEM certeza (a reserva fica); rede caindo no meio tambem.
    for tentativa in range(1, 7):
        r = graph(f"{IG_USER_ID}/media_publish", {"creation_id": cid}, tolerar=True)
        if "__erro__" not in r:
            return r["id"]
        err = r["__erro__"]
        if err.get("code") not in PUBLISH_AINDA_NAO:
            sys.exit(f"Graph API: {err.get('message')} (code {err.get('code')})")
        if tentativa == 6:
            raise NaoPublicou(f"Graph API: {err.get('message')} (code {err.get('code')}) em 6 tentativas")
        log(f"   publish recusado com {err.get('code')} (tentativa {tentativa}/6); de novo em 5s...")
        time.sleep(5)

def git(*args):
    subprocess.run(["git", *args], cwd=RAIZ, check=True, capture_output=True)

def git_commit(msg):
    """Commita so se houver algo staged. Uma reexecucao na mesma hora reusa o
    mesmo nome de arte; sem isto o 'nothing to commit' derruba o script."""
    if subprocess.run(["git", "diff", "--cached", "--quiet"],
                      cwd=RAIZ).returncode == 0:
        log("   (nada novo para commitar)")
        return False
    git("commit", "-m", msg)
    return True

def git_push():
    """O repo recebe commits de outras execucoes, entao o push pode ser
    recusado. Rebaseia e tenta de novo antes de desistir."""
    for tentativa in range(3):
        try:
            subprocess.run(["git", "push"], cwd=RAIZ, check=True, capture_output=True)
            return
        except subprocess.CalledProcessError:
            log(f"   push recusado (tentativa {tentativa + 1}); rebaseando...")
            subprocess.run(["git", "pull", "--rebase", "-q"], cwd=RAIZ, capture_output=True)
            time.sleep(2)
    sys.exit("nao consegui enviar ao repositorio apos 3 tentativas")

def main():
    agora = datetime.now(BRT)
    hora, hoje = agora.hour, agora.strftime("%Y-%m-%d")
    forcar = os.environ.get("FORCAR") == "1"
    repor = os.environ.get("HORARIO", "").strip()
    log(f"== {agora:%Y-%m-%d %H:%M} BRT ==")

    if repor:
        if not forcar:
            sys.exit("HORARIO so vale junto com FORCAR=1 (reposicao de horario perdido)")
        if not repor.isdigit() or int(repor) not in HORARIOS_CHEIOS:
            sys.exit(f"HORARIO invalido: {repor!r}; use um de {HORARIOS_CHEIOS}")
        # Repor horario que ainda nao chegou ocuparia a vaga e o disparo de verdade seria
        # ignorado depois — inclusive o de amanha, se alguem repuser apos a meia-noite.
        if int(repor) > hora:
            sys.exit(f"HORARIO {repor}h ainda nao chegou hoje ({hora}h): reposicao e so de horario que ja passou")
    horario = int(repor) if repor else hora

    if not forcar and hora not in HORARIOS_CHEIOS:
        return ignorar("fora_da_janela", f"{hora}h fora dos horarios {HORARIOS_CHEIOS}")

    # Sem isto, duas execucoes proximas leem o mesmo publicados.json antigo e
    # escolhem o MESMO aparelho (aconteceu em 23/09: o disparo manual e o do
    # launchd cairam com 34s de diferenca). So nao duplicou porque o push da
    # arte falhou por conflito — sorte, nao design.
    try:
        subprocess.run(["git", "pull", "--rebase", "-q"], cwd=RAIZ, check=True,
                       capture_output=True, timeout=120)
    except Exception as e:
        log(f"   aviso: nao consegui sincronizar antes de decidir ({e})")

    registro = json.loads((RAIZ / "publicados.json").read_text())
    ja = {p["device_id"] for p in registro["publicados"]}
    feitos_hoje = [h for d, h in map(dia_e_horario, registro["publicados"]) if d == hoje]
    hoje_n = len(feitos_hoje)

    # Um story por horario. Com dois disparadores ligados (o launchd antigo e o
    # n8n), cada horario recebe dois disparos e saiam dois stories na mesma hora.
    # FORCAR sem HORARIO segue passando por cima de tudo (uso manual); a reposicao
    # respeita a trava do horario que ela repoe, para nao repor duas vezes.
    if (not forcar or repor) and horario in feitos_hoje:
        return ignorar("horario", f"horario {horario}h ja publicado hoje")

    ativos = anuncios_ativos()
    ineditos = sorted([a for a in ativos if a["id"] not in ja
                       and (a.get("asking_price") or 0) > 0 and foto_de(a)],
                      key=lambda a: a["created_at"], reverse=True)
    log(f"   ativos={len(ativos)} ineditos={len(ineditos)} publicados_hoje={hoje_n}")

    if not ineditos:
        return ignorar("sem_inedito", "nenhum anuncio inedito disponivel")

    modo_cheio = (len(ineditos) + hoje_n) >= META_CHEIA
    meta = META_CHEIA if modo_cheio else META_REDUZIDA
    log(f"   modo={'cheio' if modo_cheio else 'reduzido'} {meta}/dia meta={meta}")

    if not forcar and not modo_cheio and hora not in HORARIOS_REDUZIDOS:
        return ignorar("reduzido", f"modo reduzido publica so as {HORARIOS_REDUZIDOS}h")
    if not forcar and hoje_n >= meta:
        return ignorar("meta", f"meta de {meta} ja atingida hoje")

    a = ineditos[0]
    log(f"   escolhido: {a.get('model')} — R$ {a['asking_price']} ({a['id'][:8]})")

    nome = f"{hoje}-{horario:02d}h-{a['id'][:8]}.png"
    destino = RAIZ / "artes" / nome
    montar_arte(a, destino)
    log(f"   arte gerada: {nome} ({destino.stat().st_size // 1024} KB)")

    # RESERVA ANTES DE PUBLICAR. O aparelho e o horario entram no registro no MESMO commit da
    # arte (que precisa estar publica antes: a Meta busca por URL), e esse push acontece antes
    # de a Meta ser chamada. Push que nao sai = nada publicado. Story que sai e registro final
    # que nao sobe = a reserva ja esta na main e segura o aparelho e o horario, hoje e nos
    # proximos dias. Duplicar fica impossivel por construcao (cetico, 26/09: uma trava pela
    # contagem da Meta so enxergava o proprio dia, e no dia seguinte o aparelho voltava).
    reserva = {"device_id": a["id"], "modelo": a.get("model"), "story_id": None,
               "em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "horario": horario, "estado": "publicando"}
    registro["publicados"].append(reserva)
    gravar(registro)
    git("add", f"artes/{nome}", "publicados.json")
    git_commit(f"Arte e reserva: {a.get('model')} ({hoje} {horario:02d}h)")
    git_push()
    url = f"{REPO_RAW}/artes/{nome}"
    log(f"   publicada em {url}")

    onde = f"{horario}h | {a.get('model')} ({a['id'][:8]})"
    try:
        story_id = publicar(url)
    except NaoPublicou as e:
        # Certeza de que nada saiu: devolve o aparelho e o horario (pode repor depois).
        try:
            registro["publicados"].remove(reserva)
            gravar(registro)
            git("add", "publicados.json")
            if git_commit(f"Libera reserva: {a.get('model')} ({hoje} {horario:02d}h) — nao publicou"):
                git_push()
        except BaseException:
            log("   aviso: a reserva nao foi liberada na main; o horario fica bloqueado ate alguem tirar")
            ficou(onde, "NAO publicou (certeza) e a liberacao nao subiu: apagar a entrada")
        sys.exit(str(e))
    except BaseException as e:
        # Sem certeza (codigo desconhecido ou rede caindo NO publish): a reserva fica, e o vigia sabe.
        porque = str(e.code) if isinstance(e, SystemExit) else f"{type(e).__name__}: {e}"
        ficou(onde, f"desfecho incerto ({porque}): ver no Instagram se saiu — saiu: preencher story_id e tirar estado; nao saiu: apagar a entrada")
        raise
    log(f"   >>> STORY NO AR: {story_id}")
    # A decisao sai ANTES do registro final: se ele nao subir, a rodada falha, mas o vigia
    # sabe que o story saiu e nao manda repor.
    anotar("decisao", f"publicado | {onde} | story {story_id}")

    try:
        reserva.update(story_id=story_id, em=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        del reserva["estado"]
        gravar(registro)
        git("add", "publicados.json")
        if git_commit(f"Registra story {story_id}"):
            git_push()
    except BaseException:
        ficou(onde, f"story {story_id} NO AR e o registro final nao subiu: preencher story_id {story_id} e tirar estado")
        raise

def gravar(registro):
    (RAIZ / "publicados.json").write_text(json.dumps(registro, indent=2, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main()
