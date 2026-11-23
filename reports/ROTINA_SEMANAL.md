# Rotina semanal — atualização do histórico de serviços via API

Substitui a espera pela exportação manual do TecPet: todo domingo à noite
(Routine `Painel Nave — atualização semanal (API)`), o histórico de
serviços é atualizado direto pela API pública do TecPet, para o mês
corrente (dia 1 até hoje).

## Por que é seguro rodar sozinho, sem supervisão

- **`api.tec.pet` só tem acesso de leitura** — a rotina nunca grava nada na
  plataforma da unidade.
- **Autenticação não é um segredo guardado em arquivo nenhum**: o host
  `api.tec.pet` está liberado na rede do ambiente e a credencial é
  injetada pelo proxy — ver `get_environment` (`network_secrets`). O
  `reports/importar_historico_api.mjs` não lê nem guarda token.
- **`node:fetch` nativo não pega a injeção do proxy neste ambiente** — o
  script usa `curl` (testado e funcionando; `fetch()` puro retorna 401
  mesmo com host liberado).
- **A mesclagem nunca perde dado**: reimplementa `chaveHistoricoServico`,
  `mesclarGrupoHistorico` e `gruposComQueda` (mesma lógica do
  `index.html`, usada em toda reimportação manual desde outubro/2026) —
  reconcilia por código de AGENDAMENTO, nunca duplica, nunca sobrescreve
  sem reconciliar. Se `gruposComQueda` encontrar qualquer queda, o script
  **aborta sem escrever nada** (`exit 1`).
- **Porte vem do cadastro do pet** (`/pet`, campo `size`) e **valor vem da
  tabela de preço por raça do catálogo** (`/service`, `priceTableByBreed`)
  — nunca do `invoice.totalValue` da reserva, que pode ser o pagamento do
  **plano** do pet (cobre vários atendimentos do mês) e infla o ticket
  médio (~45% medido em 18/11/2026, corrigido antes de entrar em
  produção — ver commit "Importa novembro via API TecPet").
- **Filtro `segmentType === 'PET_SHOP'`** — só conta banho & tosa (o
  painel é só disso), mesma decisão de 17/11/2026 que tirou "Leva e
  Tráz"/"Aplicação de Hidratação Externo" da lista de serviços clínicos.

## Passo a passo (o que a Routine deve fazer)

1. **Sincronizar**: ler o artifact publicado
   (`https://claude.ai/artifact/AfUvBNoVJeB8hUsGtnu9uD`) e comparar a
   `version id` com a do último publish conhecido nesta sessão. Se
   divergir, splicar o `<script id="pedidos-state-data">` do artifact ao
   vivo no `index.html` local antes de seguir (nunca sobrescrever
   cegamente — ver disciplina de "live-drift-check" usada em toda esta
   conversa).
   - Se esse link também der "artifact not found": não é pra recriar
     sozinho de novo — pare e avise o usuário (aconteceu em 23/11/2026
     com o link anterior, KB2kBmHWdTu93Ech2uyueV, que tinha sumido sem
     explicação e sem compartilhamento preservado no novo).
2. **Rodar o script**:
   ```
   node reports/importar_historico_api.mjs
   ```
   (sem argumentos = dia 1 do mês atual até hoje). Leva uns 3-5 minutos
   (o diretório de pets da rede tem ~125 mil registros, baixado em
   páginas de 1000 com espaçamento de 600ms entre chamadas — API de
   produção, nunca paralelizar).
3. **Se o script abortar** (`exit 1`, "gruposComQueda encontrou
   queda(s)"): **não mexer no index.html**, reportar o problema (não é
   pra "forçar" de nenhum jeito — investigar antes).
4. **Validar** (mesma disciplina de sempre):
   - `node --check` nos `<script>` não-JSON do HTML.
   - `JSON.parse` no bloco `pedidos-state-data`.
   - Smoke test Playwright: abrir cada aba (`data-view`), 0 erro de
     console (ignorando `ERR_TUNNEL_CONNECTION_FAILED`/`ERR_CERT_*`, que
     são da sandbox, não do painel), `gruposComQueda(...)` vazio no
     resultado final.
5. **Commitar e dar push** no branch
   `claude/painel-banho-tosa-facilites-r9hhjk`, mensagem citando o
   período importado e o resumo (`RESUMO_JSON` que o script imprime).
6. **Checar drift de novo** no artifact ao vivo (pode ter mudado entre os
   passos 1 e 6 — ex.: alguém aprovando um pedido no meio do processo) e
   publicar (prefixo/sufixo de sempre, ver `CLAUDE.md`/histórico desta
   sessão se precisar relembrar o texto exato).
7. **Reportar**: uma mensagem curta dizendo o período importado, quantos
   atendimentos/grupos novos ou enriquecidos, e qualquer coisa fora do
   padrão (ex.: unidade com volume muito abaixo do normal, serviço novo
   não visto antes). Só interromper e pedir confirmação se alguma
   validação falhar — combinado em 18/11/2026: publicar direto quando
   tudo passa.

## O que NÃO mudou

- A exportação manual quinzenal (planilha de serviços) continua existindo
  como lembrete (`trig_01Sw8LU4MMnrhQdxqqHJdMcy`) — essa rotina semanal
  via API não substitui o lembrete, só reduz a dependência dele pro
  histórico de serviços ficar em dia. Histórico de compras, Relação
  Serviço×Produto e Tabela de Rendimento continuam só manuais.
- Esta rotina **não mexe no ERP** nem em nada fora de `historicoServicos`.
