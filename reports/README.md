# Relatório mensal de uso de produtos

Gera as imagens do relatório de consumo do Painel Nave (comparativo
"esperado × feito" por produto, desde a última compra) pra envio manual por
WhatsApp todo fim de mês:

- **1 imagem geral por unidade** — vai pros líderes (grupo + individual).
- **1 imagem detalhada por unidade** (12 no total) — vai só pra coordenadora
  dos líderes.

## Uso

```
node gerar_relatorio_mensal.mjs [--out DIR] [--mes YYYY-MM]
```

- `--out`: diretório de saída (default: `./saida`)
- `--mes`: mês de fechamento a rotular nas imagens (default: mês atual)

Roda localmente com Playwright (sobe um servidor estático temporário pra
carregar o `index.html` e chamar `calcularComparativoUltimaCompra()` — a
mesma função usada pela aba "Análise de Consumo" do painel, então os números
batem com o que aparece lá). Não depende de rede.

Gera `manifest.json` com a lista de arquivos e a unidade de cada um.

## Produtos ocultos nas imagens

`SOFT TOUCH 500ML` e `EXPERT OIL REDUX 250G` ficam de fora das imagens (mas
continuam no comparativo interno do painel) — pedido do usuário em
25/09/2026, ver `OCULTOS_NA_IMAGEM` no script.

## Entrega (decidido em 25/09/2026, ajustado no mesmo dia)

Sem infraestrutura de envio automático por WhatsApp (exigiria guardar
credenciais de API fora do HTML público do painel). A ideia inicial era subir
as imagens pro Google Drive, mas isso esbarrou num limite prático: fazer
upload via ferramenta MCP exige embutir o conteúdo do arquivo em base64
dentro da própria chamada — pra uma imagem de ~115KB isso custou ~1 milhão de
tokens de contexto num teste real, e as 13 imagens juntas passariam de 10
milhões. Inviável como rotina mensal.

O fluxo ficou:

1. Uma Routine agendada roda este script todo fim de mês (ver
   `agendamento` abaixo).
2. As imagens são entregues direto pro usuário via `SendUserFile` (chega no
   app/chat, sem re-embutir o binário em texto — muito mais barato).
3. O usuário encaminha manualmente pelo WhatsApp a partir daí (imagem geral
   pros líderes — grupo e individual —, as 12 detalhadas só pra coordenadora).

Se quiser arquivar no Drive, hoje isso fica por conta do usuário salvar
manualmente a partir do que ele recebe.

## Agendamento

Routine (`create_trigger`) com cron no formato `MM HH 28-31 * *` (campo de
dia-do-mês = 28-31 — roda em todo dia 28, 29, 30 e 31 de cada mês, já que
cron não tem um jeito nativo de expressar "último dia do mês"). O prompt da
Routine checa se amanhã é dia 1 antes de gerar o relatório; se não for, é
`noop` (o mês ainda não fechou). Isso garante que o relatório sai
exatamente no último dia, independente do mês ter 28, 29, 30 ou 31 dias.
