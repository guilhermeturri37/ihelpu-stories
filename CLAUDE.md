# iHelpU Stories — CLAUDE.md

Automação que publica Stories no **@ihelpuoficial** com aparelhos do marketplace
de seminovos. Roda sozinha às 9h05, 10h05, 11h05, 12h05 e 13h05.

```
launchd (Mac do Guilherme)  →  gh workflow run  →  GitHub Actions  →  Story no ar
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
- **Testar mudança rodando de verdade.** Os cinco bugs desta automação só apareceram em
  produção. `gh run view <id> --log | awk -F'\t' '$2=="Publicar"'` mostra a saída limpa.

## Limites conhecidos

- Só publica com o **Mac ligado e o usuário logado** — o Mac está configurado para
  dormir em 1 minuto e depende do Amphetamine estar ativo. Horário perdido não é
  recuperado: o script recusa publicar fora da janela 9h–13h.
- A API do Instagram **não permite sticker de link** em Stories publicados por API.
  Vale para qualquer ferramenta. Por isso o CTA é o Direct.
- As fotos são de vistoria, não de venda. Categorias que não são iPhone às vezes
  trazem captura de tela de Ajustes. A arte aproveita foto boa, mas não inventa.
