# Relatório mensal de uso de produtos

Gera as imagens do relatório de consumo do Painel Nave (comparativo
"esperado × feito" por produto, desde a última compra) pra envio manual por
WhatsApp todo início de mês:

- **1 imagem geral por unidade** — vai pros líderes (grupo + individual).
- **1 imagem detalhada por unidade** (até 12) — vai só pra coordenadora
  dos líderes.

## Uso

```
node gerar_relatorio_mensal.mjs [--out DIR] [--mes YYYY-MM]
```

- `--out`: diretório de saída (default: `./saida`)
- `--mes`: mês de referência dos pedidos a considerar/rotular (default: mês
  atual — o normal ao rodar no dia 1, ver `agendamento` abaixo)

Roda localmente com Playwright (sobe um servidor estático temporário pra
carregar o `index.html` e chamar `calcularComparativoUltimaCompra()` — a
mesma função usada pela aba "Análise de Consumo" do painel, então os números
batem com o que aparece lá). Não depende de rede.

Gera `manifest.json` com a lista de arquivos e a unidade de cada um.

## Filtro: só produtos pedidos no mês (decidido em 25/09/2026)

O usuário sobe os pedidos do mês seguinte no último dia do mês anterior
(ex.: pedidos de outubro, aprovados em 30/09, contam como compra de outubro
pela regra `mesSeguinte()` do `index.html`). O relatório mostra **só os
produtos com "última compra" registrada no mês de referência** — quem não
foi repedido nesse ciclo segue em uso e ainda pode render mais, então não
entra na comparação (evita mostrar como "problema" um produto que
simplesmente ainda não precisou de reposição). O cálculo de esperado/feito
em si não muda — é o mesmo de sempre (`calcularComparativoUltimaCompra()`),
só a lista de produtos exibidos é filtrada.

Isso pode deixar alguma unidade sem nenhum produto pedido no mês — nesse
caso a imagem "Detalhado" dela simplesmente não é gerada (fica menos de 12).

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

1. Uma Routine agendada roda este script todo dia 1 (ver `agendamento`
   abaixo).
2. As imagens são entregues direto pro usuário via `SendUserFile` (chega no
   app/chat, sem re-embutir o binário em texto — muito mais barato).
3. O usuário encaminha manualmente pelo WhatsApp a partir daí (imagem geral
   pros líderes — grupo e individual —, as detalhadas só pra coordenadora).

Se quiser arquivar no Drive, hoje isso fica por conta do usuário salvar
manualmente a partir do que ele recebe.

## Agendamento

Routine (`create_trigger`, id `trig_015Bu9zMi5xkBUNyMCeSsA2i`) com cron
`CRON_TZ=America/Sao_Paulo 47 8 1 * *` — roda todo dia 1 do mês, 08:47
(horário de SP). Rodar no dia 1 (em vez do último dia do mês anterior) é
proposital: garante que TODOS os pedidos submetidos ao longo do último dia
do mês anterior já foram capturados antes do relatório sair (rodar ainda no
próprio dia do fechamento arriscaria pegar só parte das aprovações feitas
naquele dia).
