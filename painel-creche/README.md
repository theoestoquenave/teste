# Painel Creche & Hotel · Nave Tatuapé

Painel publicado: https://claude.ai/artifact/UeZcGVLvAhxH7LtmG41HnL

## Como atualizar os dados

1. `python3 coletar.py brutos.json` puxa da API TecPet (loja 1885) agendamentos, faturas,
   pagamentos e pacotes de 2026, mais 90 dias de agenda futura. Precisa de acesso autenticado
   a `api.tec.pet` (token Bearer) e envia o cabeçalho `x-shop: 1885`.
2. `python3 processar.py brutos.json dados/` gera os arquivos do painel:
   `agenda`, `estadias`, `faturas`, `pacotes`, `clientes`, `recebimentos`.
3. Os arquivos de `dados/` são enviados ao painel e substituem os anteriores.

`index.html` é a página do painel (fica guardada no próprio painel, a cópia aqui é referência).

## Regras usadas

- Creche/Hotel = segmento `DAY_CARE`/`HOTEL` da loja.
- Hotel = serviços "Diária 24 horas", "Diária Gato" e o pacote "Aluguel". Creche = "Diária Avulsa",
  "Meia Diária" e pacotes Daycare. O resto (medicação, silvestres) entra como "Outros".
- Estadia = noites seguidas do mesmo pet.
- Faturamento = faturas não canceladas, pela data de emissão (mesma regra da Projeção financeira do TecPet).
- Pacote atual = o mais recente de cada pet. Alerta quando sobram 2 diárias ou menos, ou faltam 7 dias para o fim.
