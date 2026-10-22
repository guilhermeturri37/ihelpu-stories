#!/usr/bin/env python3
"""Publica um story "VENDIDO" no @ihelpuoficial quando um iPhone e vendido no marketplace.

Pedido do Guilherme em 22/10/2026. Quem avisa da venda e o proprio marketplace (Lovable):
no backend, chama o workflow_dispatch do vendido.yml com o input `aparelho` — um TEXTO com
um JSON: device_id, model, capacity, aesthetic_condition, category, preferred_store, sold_at,
photos e teste. Aparelho vendido some do RPC get_public_active_devices, entao os dados vem
no aviso; o robo nao consegue busca-los depois.

  - venda de segunda a sabado, das 8h as 21h: publica na hora
  - fora disso (noite, domingo): fica "pendente" e sai na primeira rodada de stories do dia
    seguinte (o story.yml chama este script, sem aviso, toda hora: ele publica os pendentes)
  - um story por aparelho, nunca dois: cada venda e um arquivo vendidos/<device_id>.json,
    conferido antes de tudo, e a reserva ("publicando") sobe para a main antes da Meta
  - teste=true: gera a arte e para — nao registra, nao publica
  - so iPhone; nome, telefone, preco e qualquer dado de vendedor ou comprador nao entram

A arte e o layout v2 com um selo "VENDIDO" por cima do aparelho, sem preco e sem bateria
(aprovada pelo Guilherme em 22/10/2026, com a janela das 8h as 21h e sem o preco).
"""
import html, json, os, pathlib, re, sys
from datetime import datetime, timezone

import publicar as P

RAIZ = pathlib.Path(__file__).parent
# Um arquivo por venda, nao um registro unico: o vendido.yml NAO tem `concurrency` de proposito
# (no GitHub, um pedido novo cancela o que estava na fila do mesmo grupo — e o aviso da venda so
# existe no input do pedido; cancelado, a venda se perderia). Sem fila, duas vendas seguidas
# rodam juntas, e arquivos separados nao dao conflito no rebase.
PASTA = RAIZ / "vendidos"
RAMO = "artes-vendido"                  # proprio: o artes-stories e do publicar.py
JANELA = range(8, 21)                   # publica na hora entre 8h00 e 20h59, de segunda a sabado
FOTOS_OK = "https://tegdgtovwhbhsrbkxvog.supabase.co/storage/"   # so foto do bucket do marketplace
# preferred_store -> nome da loja na arte (os slugs do marketplace, como no status_whatsapp.py)
LOJAS = {"sao-leopoldo": "São Leopoldo", "trend": "Trend", "zona-sul": "Zona Sul",
         "santa-maria": "Santa Maria", "zona-norte": "Zona Norte", "novo-hamburgo": "Novo Hamburgo",
         "caxias-do-sul": "Caxias do Sul", "canoas": "Canoas", "pelotas": "Pelotas"}
CARIMBO = """<style>
.carimbo{position:absolute;left:50%;top:840px;transform:translate(-50%,-50%) rotate(-10deg);
  background:var(--roxo);color:#fff;padding:26px 64px 30px;border-radius:28px;text-align:center;
  box-shadow:0 20px 60px rgba(0,0,0,.5);outline:5px solid #fff;outline-offset:-18px}
.carimbo b{display:block;font-family:'Bricolage Grotesque';font-weight:800;font-size:176px;
  line-height:.95;letter-spacing:-3px}
.carimbo small{display:block;font-weight:600;font-size:32px;letter-spacing:7px;margin-top:6px}
</style>
<div class="carimbo"><b>VENDIDO</b><small>IHELPU SEMINOVOS</small></div>
"""

def ler_aviso(texto):
    """O JSON do marketplace, so com os campos que a arte usa. Recusa o que nao for iPhone e
    descarta foto de fora do bucket do marketplace (a URL vai direto para a arte publica)."""
    try:
        d = json.loads(texto)
    except ValueError as e:
        sys.exit(f"aviso nao e JSON: {e}")
    if not re.fullmatch(r"[0-9a-f-]{36}", str(d.get("device_id", ""))):
        sys.exit(f"device_id invalido: {d.get('device_id')!r}")
    if d.get("category") != "iphone" or not str(d.get("model", "")).startswith("iPhone"):
        P.ignorar("nao_iphone", f"{d.get('category')} / {d.get('model')}: so iPhone ganha story de vendido")
        return None
    fotos = [{"photo_url": f["photo_url"], "photo_type": f.get("photo_type")} for f in d.get("photos") or []
             if str(f.get("photo_url", "")).startswith(FOTOS_OK)]
    return {"id": d["device_id"], "model": d["model"], "capacity": d.get("capacity"),
            "aesthetic_condition": d.get("aesthetic_condition"), "category": "iphone",
            "preferred_store": d.get("preferred_store"), "sold_at": d.get("sold_at"),
            "photos": fotos, "teste": d.get("teste") is True}

def montar(a, destino, registro):
    modelo = a["model"].replace("iPhone ", "").replace("(", "").replace(")", "")
    estado = P.COND.get(a.get("aesthetic_condition"), "Seminovo")
    linha1 = " ".join(f"{modelo} {a.get('capacity') or ''}".split()) + f" [{estado}]"
    loja = LOJAS.get(a.get("preferred_store"))
    banco = P.foto_do_banco(a, registro)
    if not banco and not a["photos"]:
        sys.exit(f"{a['model']}: sem foto no banco e sem foto no aviso — nao ha com o que montar a arte")
    P.montar_arte_iphone(a, destino, banco, cta="Quer um também? Chama no Direct",
        linhas=f"{html.escape(linha1)}<br><em>JÁ ESTÁ COM O NOVO DONO</em>",
        selo=f"Vendido na loja {loja}" if loja else "Vendido no marketplace",
        resto="Veja os iPhones seminovos disponíveis em seminovos.ihelpu.com.br", extra=CARIMBO)
    return banco

def gravar(item):
    arq = PASTA / f"{item['device_id']}.json"
    arq.write_text(json.dumps(item, indent=2, ensure_ascii=False) + "\n")
    P.git("add", str(arq.relative_to(RAIZ)))

def todos():
    return [json.loads(f.read_text()) for f in sorted(PASTA.glob("*.json"))]

def publicar_um(item, registro):
    """Arte no ramo -> reserva na main -> Meta, a mesma ordem do publicar.py."""
    agora = datetime.now(P.BRT)
    destino = RAIZ / "_story" / f"vendido-{agora:%Y%m%d-%H%M}-{item['device_id'][:8]}.png"
    destino.parent.mkdir(exist_ok=True)
    banco = montar(item["aparelho"], destino, registro)
    [url] = P.subir_artes([destino], RAMO)
    item.update(estado="publicando", em=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    if banco:
        item["foto"] = banco["arquivo"]
    gravar(item)
    # Outra rodada publicando o mesmo pendente mexe no mesmo arquivo: o push desta da conflito,
    # o git_push desiste e a rodada sai aqui, antes da Meta. Nunca dois stories da mesma venda.
    P.git_commit(f"Reserva vendido: {item['modelo']} ({item['device_id'][:8]})")
    P.git_push()
    onde = f"vendido | {item['modelo']} ({item['device_id'][:8]})"
    try:
        story_id = P.publicar(url)
    except P.NaoPublicou as e:
        item["estado"] = "pendente"          # certeza de que nada saiu: tenta de novo na proxima rodada
        gravar(item)
        if P.git_commit(f"Vendido volta a pendente: {item['modelo']} ({item['device_id'][:8]})"):
            P.git_push()
        sys.exit(str(e))
    except BaseException as e:
        porque = str(e.code) if isinstance(e, SystemExit) else f"{type(e).__name__}: {e}"
        P.ficou(onde, f"desfecho incerto ({porque}): ver no Instagram — saiu: preencher story_id; nao saiu: estado pendente")
        raise
    P.log(f"   >>> STORY DE VENDIDO NO AR: {story_id}")
    P.anotar("decisao", f"publicado | {onde} | story {story_id}")
    item.update(estado="publicado", story_id=story_id, em=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    gravar(item)
    if P.git_commit(f"Registra story de vendido {story_id}"):
        P.git_push()

def main():
    agora = datetime.now(P.BRT)
    P.log(f"== {agora:%Y-%m-%d %H:%M} BRT — story de vendido ==")
    na_janela = agora.weekday() != 6 and agora.hour in JANELA
    aviso = os.environ.get("APARELHO", "").strip()
    a = ler_aviso(aviso) if aviso else None
    if aviso and not a:
        return
    if a and a["teste"]:
        destino = RAIZ / "previa" / f"vendido-{a['id'][:8]}.png"
        destino.parent.mkdir(exist_ok=True)
        montar(a, destino, {"publicados": []})
        P.log(f"   TESTE: arte gerada em previa/{destino.name}; nada registrado nem publicado")
        return

    try:
        P.git("pull", "--rebase", "-q")
    except Exception as e:
        P.log(f"   aviso: nao consegui sincronizar antes de decidir ({e})")
    PASTA.mkdir(exist_ok=True)
    if a:
        if (PASTA / f"{a['id']}.json").exists():
            return P.ignorar("repetido", f"{a['model']} ({a['id'][:8]}) ja recebeu aviso de venda")
        gravar({"device_id": a["id"], "modelo": a["model"], "loja": a.get("preferred_store"),
                "vendido_em": a.get("sold_at"), "estado": "pendente", "aparelho": a})
        P.git_commit(f"Venda recebida: {a['model']} ({a['id'][:8]})")
        P.git_push()
        P.log(f"   venda recebida: {a['model']} ({a['id'][:8]})")
    registro = {"publicados": todos()}           # para as fotos do banco se revezarem entre os vendidos
    pendentes = [p for p in registro["publicados"] if p.get("estado") == "pendente"]
    if not pendentes:
        return P.log("   nenhum story de vendido pendente")
    if not na_janela:
        return P.ignorar("fora_da_janela", f"{len(pendentes)} pendente(s); saem na proxima rodada entre 8h e 21h, de segunda a sabado")
    for item in pendentes:
        P.log(f"   publicando: {item['modelo']} ({item['device_id'][:8]})")
        publicar_um(item, registro)

if __name__ == "__main__":
    main()
