# iHelpU Stories — CLAUDE.md

Automação que publica Stories no **@ihelpuoficial** com aparelhos do marketplace
de seminovos. Sai um story por hora, das 8h às 14h, de segunda a sábado (7 por dia).

```
launchd (Mac do Guilherme) ou n8n  →  workflow_dispatch  →  GitHub Actions  →  Story no ar
```

## Regras e convenções

- **NUNCA usar `seller_name` em nada que vá ao ar.** O RPC devolve nome completo de
  pessoa física (as consignações são de terceiros). O campo é filtrado de propósito
  em `montar_dados()` — não reintroduzir.
- **Sempre buscar os anúncios pelo RPC `get_public_active_devices`**, nunca `SELECT`
  direto em `devices`: a RLS devolve vazio para a chave pública.
- **Sempre esperar `status_code == FINISHED`** antes do `media_publish`. Publicar logo
  após criar o container devolve `Media ID is not available` (code 9007). E o próprio
  polling pode devolver 9007 nos primeiros segundos — isso é transitório e não pode
  abortar o script.
- **Nunca colocar script de launchd em `~/Desktop`, `~/Documents` ou `~/Downloads`.**
  O TCC do macOS nega acesso a processos em segundo plano e o agente falha com
  `Operation not permitted` (exit 126). Rodar o script à mão no terminal funciona e
  mascara o problema. O lugar certo é `~/Library/Application Support/`.
- **Sempre `git pull --rebase` antes de mexer no repo local.** O workflow commita a
  cada publicação, então o remoto muda sem aviso.
- **Bateria: usar sempre `bateria(a)`, nunca `battery_health` direto.** Quando o anúncio tem
  `battery_replacement_required`, a loja troca a bateria antes da retirada e o site mostra
  100% (regra `d1()` do site). Até 07/10/2026 o robô publicava o valor da vistoria — um
  13 mini saiu com 76% enquanto o marketplace dizia 100%. Vale para 12 dos 57 anúncios.
- **Nunca escrever "sem juros" nem um valor de parcela calculado sem a taxa.** A tabela
  `installment_fees` tem 18 parcelas, com 12,5% em 12x e 15,18% em 18x. "Parcelamos em
  até 18x no cartão" é o que pode ser afirmado.
- **Não propor Supabase Edge Functions.** O acesso de deploy foi recusado
  explicitamente pelo usuário; a arquitetura em GitHub Actions é a decisão final.
- **Não confiar no `schedule:` do GitHub Actions.** Foi testado e disparava com até
  4h26 de atraso, ou não disparava. Foi removido de propósito.
- **Ao mexer no `template.html`, conferir o `publicar.py` junto.** Os placeholders
  (`FOTO_URL`, `MODELO_NOME`, `FS_MODELO`, `ESTADO_LABEL`, `BATERIA`, `R$ PRECO`) e o
  regex que remove o badge de bateria vivem nos dois arquivos.
- **iPhone usa o `template_v2.html`; as outras categorias seguem no `template.html`.** O v2
  (foto em tela cheia + etiqueta branca) tem os seus proprios placeholders (`FOTO_URL`,
  `IMG_ATTRS`, `ALVO_H_PX`, `ALVO_Y_PX`, `BLOCO_TOP`, `FS_ETIQUETA`, `LINHAS`, `SELO_TXT`,
  `RODAPE_TXT`, `CTA_TXT`), preenchidos em `montar_arte_iphone()`.
- **Foto do banco e do MODELO, nao do aparelho.** `banco.json` mapeia o nome exato do modelo
  no marketplace para as fotos em `banco/`. Antes de cadastrar uma foto, conferir o modelo
  pela camera (iPhone 11 e 12: duas lentes na vertical; 13, 14 e 15: na diagonal) — o nome
  do arquivo que vem da loja ja veio errado. A arte com foto do banco diz "imagem
  ilustrativa"; a que usa a foto do anuncio diz "foto real do aparelho anunciado".
- **O iPhone 14 usa as fotos do 14 Plus, provisoriamente** (decisão do Guilherme em 07/10/2026:
  os dois só diferem no tamanho, e numa foto de mão não dá para distinguir). Quando chegar
  foto de um iPhone 14, trocar a lista do `"iPhone 14"` no `banco.json`.
- **Nunca subir foto de loja sem tirar o EXIF.** Os originais do iPhone trazem o GPS da
  loja e o repositorio e publico. Regravar com PIL, sem `exif`, antes de por em `banco/`.
- **Fontes ficam em `fonts/`, nao no Google Fonts.** Quando a fonte da internet nao
  carrega a tempo, o Chrome renderiza com a fonte padrao e nao da erro nenhum.
- **Aparelho pode reprisar, mas nunca no mesmo dia.** 7 stories/dia não se sustentam só
  com anúncio inédito (entram 1 a 2 por dia). Sem inédito, sai o anúncio ativo que está há
  mais tempo sem aparecer. A regra antiga de "nunca repete aparelho" acabou em 07/10/2026.
- **Mudou horário ou dia? São três lugares:** `HORARIOS` no `publicar.py`, o plist
  `~/Library/LaunchAgents/com.ihelpu.stories.plist` e o disparador do n8n.
- **Para ver a arte sem publicar: `SO_ARTE=1`** (input `so_arte` do workflow). Gera as
  proximas artes em `previa/` e sai antes de reservar, tocar na main ou chamar a Meta. As
  prévias sobem para o ramo `artes-previa` pelo mesmo `subir_artes()` das artes de verdade
  — é o ensaio desse caminho.
- **Arte de story não vai para a main.** Cada PNG tem ~1 MB e ficava para sempre no
  histórico (85 MB em 07/10/2026, +8 MB por dia). `subir_artes()` põe a arte num commit
  solto no ramo `artes-stories` (push forçado, só a última fica) e a Meta busca por
  `raw.githubusercontent.com/.../<sha>/<nome>`. A ordem é: arte no ramo → reserva na main
  → Meta. Não usar o `artes-status` (é do WhatsApp) nem voltar a dar `git add` em arte. A
  cópia de cada rodada fica 30 dias no artifact `arte` do run. A pasta `artes/` da main é
  o acervo antigo (até 07/10/2026) e não recebe mais nada.
- **Testar mudança rodando de verdade.** Os cinco bugs desta automação só apareceram em
  produção. `gh run view <id> --log | awk -F'\t' '$2=="Publicar"'` mostra a saída limpa.

- **Curtida de story não existe na API.** O coração é privado por design (a Meta listou
  "curtir stories" como não suportado em abril/2026). Só **reação com emoji** e **resposta
  de texto** chegam como mensagem no Direct. Ferramenta que promete disparar para quem
  curtiu está usando API não oficial — risco de banimento da conta.
- **Erro `code 3` da Graph API não é permissão do token.** "Application does not have the
  capability" significa que falta um **produto no app** da Meta. Checar o app antes de
  mexer em escopo: o token pode ter o escopo e a chamada falhar mesmo assim.

## Status do WhatsApp (desde 07/10/2026)

`status_whatsapp.py` + `.github/workflows/status.yml` publicam a mesma arte no Status do
WhatsApp das lojas, pela Evolution API (`https://evolutionapi.ihelpu.com.br`, versão 2.3.7,
chave em `op://iHelpU-Core/Evolution API - Lojas/password` e no secret `EVOLUTION_API_KEY`).

- **4 por dia em cada número: 8h10, 10h10, 12h10 e 14h10, de segunda a sábado** — dez
  minutos depois do story. Quem dispara é **só o n8n** ("Stories Marketplace — Disparador",
  gatilho `Status 8h10 a 14h10`, cron `10 8,10,12,14 * * 1-6`), desde 07/10/2026. O launchd
  `com.ihelpu.status` do Mac foi desligado (`launchctl disable`; o plist ficou no lugar) a
  pedido do Guilherme, para não depender do Mac ligado. Não religar os dois juntos sem necessidade. O registro do Status
  é gravado e enviado ao GitHub a cada loja (até 07/10/2026 14h34 era só no fim da rodada,
  e um disparo depois de uma queda no meio reenviaria para quem já tinha recebido).
- **`LOJAS` mapeia instância → loja do marketplace; `ATIVAS` diz quais estão no automático.**
  Desde 08/10/2026 são as dez (pedido do Guilherme em 07/10/2026; até então eram São
  Leopoldo, central e Trend). A rodada inteira deve levar uns 30 min; se passar muito
  disso, olhar o tempo por loja no log antes de mexer em horário ou frequência.
- **O Status vai para quem conversou com a loja nos últimos 60 dias (`DIAS_CONVERSA`), não
  para todos os contatos** (decisão do Guilherme em 07/10/2026). A Evolution 2.3.7 reenvia
  a imagem inteira a cada 10 destinatários (~0,13 s por destinatário) e ignora em silêncio
  os grupos de 10 que falham. Com `allContacts` (todo contato com nome) a lista ia de 494
  a 20.875 conforme a loja: no primeiro envio real São Leopoldo levou 43 s, a central
  144 s e a Trend 884 s; Pelotas levaria 47 min. Com `destinatarios()` as dez ficam entre
  500 e 1.100 (uns 2 min cada). Não voltar para `allContacts`. Conversa que a Evolution só
  conhece pelo `@lid`, sem telefone em `remoteJidAlt`, fica de fora.
- **Nunca mandar `statusJidList` vazio.** A Evolution valida a lista (mínimo de 1 item)
  antes de qualquer outra coisa; a lista vazia derrubou as 3 lojas com HTTP 400 em
  07/10/2026 14h10. O `TESTE_PARA` manda 1 número e não mostra tempo de envio real.
- **A Evolution é API não oficial e os números são os de atendimento das lojas.** Uma loja
  por vez, com pausa (`PAUSA`); nunca disparar as dez em paralelo nem aumentar a frequência
  sem o Guilherme pedir.
- **A imagem tem de ir por URL.** Base64 volta `ENAMETOOLONG`. As artes vão para o ramo
  `artes-status` (um commit solto, push forçado), não para a main — seriam 40 MB por dia.
- **Para testar sem atingir cliente: `TESTE_PARA=<número>`** (resolver o JID antes em
  `/chat/whatsappNumbers`; número do RS perde o 9). **Para ver a arte: `PREVIA=1`.**
- **Envio "incerto" fica no registro** (`status_whatsapp.json`) para não sair em dobro.

## Limites conhecidos

- Só publica com o **Mac ligado e o usuário logado** — o Mac está configurado para
  dormir em 1 minuto e depende do Amphetamine estar ativo. Horário perdido não é
  recuperado sozinho: o script recusa publicar fora dos horários (8h a 14h) e aos domingos.
  O n8n "Stories Marketplace — Disparador" é um segundo disparador, independente do Mac
  (`5 8-14 * * 1-6`, os 7 horários). Em 07/10/2026 14h o `gh workflow run` do Mac levou
  HTTP 500 do GitHub e quem publicou foi o n8n, às 14h05.
- A API do Instagram **não permite sticker de link** em Stories publicados por API.
  Vale para qualquer ferramenta. Por isso o CTA é o Direct.
- As fotos são de vistoria, não de venda. Categorias que não são iPhone às vezes
  trazem captura de tela de Ajustes. A arte aproveita foto boa, mas não inventa.
