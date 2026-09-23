#!/usr/bin/env python3
"""Publica um Story no @ihelpuoficial com um aparelho do marketplace iHelpU.

Roda no GitHub Actions as 9,10,11,12 e 13h de Brasilia. Cada execucao decide
sozinha se publica:
  - escolhe o anuncio mais novo que ainda nao foi ao ar; nunca repete aparelho
  - 5/dia enquanto houver ineditos; se o estoque apertar, cai para 2/dia (9h e 12h)
  - pula anuncio sem foto ou sem preco em vez de publicar algo quebrado

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

HORARIOS_CHEIOS = [9, 10, 11, 12, 13]
HORARIOS_REDUZIDOS = [9, 12]
META_CHEIA, META_REDUZIDA = 5, 2

COND = {"como_novo": "Como novo", "excelente": "Excelente", "bom": "Bom", "regular": "Regular"}
COM_BATERIA = {"iphone", "ipad", "macbook"}   # onde "Bateria X%" faz sentido

def log(m): print(m, flush=True)

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

def publicar(url_arte):
    c = graph(f"{IG_USER_ID}/media", {"media_type": "STORIES", "image_url": url_arte})
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
                sys.exit(f"container nao ficou consultavel: {r['__erro__'].get('message')}")
            time.sleep(3)
            continue
        estado = r.get("status_code")
        if estado == "FINISHED": break
        if estado in ("ERROR", "EXPIRED"): sys.exit(f"container falhou: {r.get('status')}")
        time.sleep(3)
    else:
        sys.exit("container nao ficou pronto em 90s")
    return graph(f"{IG_USER_ID}/media_publish", {"creation_id": cid})["id"]

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
    log(f"== {agora:%Y-%m-%d %H:%M} BRT ==")

    if not forcar and hora not in HORARIOS_CHEIOS:
        return log(f"ignorado: {hora}h fora da janela 9-13h")

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
    hoje_n = sum(1 for p in registro["publicados"] if p["em"][:10] == hoje)

    ativos = anuncios_ativos()
    ineditos = sorted([a for a in ativos if a["id"] not in ja
                       and (a.get("asking_price") or 0) > 0 and foto_de(a)],
                      key=lambda a: a["created_at"], reverse=True)
    log(f"   ativos={len(ativos)} ineditos={len(ineditos)} publicados_hoje={hoje_n}")

    if not ineditos:
        return log("ignorado: nenhum anuncio inedito disponivel")

    modo_cheio = (len(ineditos) + hoje_n) >= META_CHEIA
    meta = META_CHEIA if modo_cheio else META_REDUZIDA
    log(f"   modo={'cheio 5/dia' if modo_cheio else 'reduzido 2/dia'} meta={meta}")

    if not forcar and not modo_cheio and hora not in HORARIOS_REDUZIDOS:
        return log(f"ignorado: modo reduzido publica so as {HORARIOS_REDUZIDOS}h")
    if not forcar and hoje_n >= meta:
        return log(f"ignorado: meta de {meta} ja atingida hoje")

    a = ineditos[0]
    log(f"   escolhido: {a.get('model')} — R$ {a['asking_price']} ({a['id'][:8]})")

    nome = f"{hoje}-{hora:02d}h-{a['id'][:8]}.png"
    destino = RAIZ / "artes" / nome
    montar_arte(a, destino)
    log(f"   arte gerada: {nome} ({destino.stat().st_size // 1024} KB)")

    # A arte precisa estar publica ANTES de publicar: a Meta busca por URL.
    git("add", f"artes/{nome}")
    if git_commit(f"Arte: {a.get('model')} ({hoje} {hora:02d}h)"):
        git_push()
    url = f"{REPO_RAW}/artes/{nome}"
    log(f"   publicada em {url}")

    story_id = publicar(url)
    log(f"   >>> STORY NO AR: {story_id}")

    registro["publicados"].append({
        "device_id": a["id"], "modelo": a.get("model"),
        "story_id": story_id, "em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    (RAIZ / "publicados.json").write_text(json.dumps(registro, indent=2, ensure_ascii=False) + "\n")
    git("add", "publicados.json")
    if git_commit(f"Registra story {story_id}"):
        git_push()

if __name__ == "__main__":
    main()
