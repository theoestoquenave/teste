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

## Entrega (decidido em 25/09/2026)

Sem infraestrutura de envio automático por WhatsApp (exigiria guardar
credenciais de API fora do HTML público do painel). O fluxo é:

1. Uma Routine agendada roda este script todo fim de mês.
2. As imagens sobem pro Google Drive, pasta "Relatórios de Uso - Painel Nave".
3. O usuário é avisado (notificação) e encaminha manualmente pelo WhatsApp.
