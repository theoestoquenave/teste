#!/usr/bin/env node
// Atualiza historicoServicos do Painel Nave puxando direto da API pública do
// TecPet (em vez de esperar a exportação manual em .xlsx) — mesmo filtro e
// mesma lógica validados manualmente em 17 e 18/11/2026 (ver git log).
//
// Não guarda nenhum segredo: a autenticação em api.tec.pet é injetada pelo
// proxy de rede do ambiente (configurado fora deste repositório). O script
// só assume que esse host está liberado e autenticado — se uma chamada vier
// 401/403, o ambiente que precisa ser revisto, não este arquivo.
//
// Uso:
//   node reports/importar_historico_api.mjs [--de AAAA-MM-DD] [--ate AAAA-MM-DD] [--html caminho]
//   Default: --de = dia 1 do mês atual, --ate = hoje, --html = ./index.html
//
// Saída: reescreve o bloco historicoServicos de --html no lugar (depois de
// mesclar com o que já existe, nunca substitui) e imprime um resumo em
// stdout. NÃO dá commit/push/publish — isso fica para quem chamou o script
// (rotina ou humano), depois de olhar o resumo e rodar as validações de
// sempre (sintaxe, smoke test, checar drift do artifact antes de publicar).

import fs from 'node:fs';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
const execFileP = promisify(execFile);

const BASE = 'https://api.tec.pet/v1';
const PACE_MS = 600; // API de produção — nunca paralelizar, sempre espaçar
let _lastCall = 0;
async function pace(){
  const wait = _lastCall + PACE_MS - Date.now();
  if (wait > 0) await new Promise(r => setTimeout(r, wait));
  _lastCall = Date.now();
}
// Autenticação em api.tec.pet é injetada pelo proxy de rede do ambiente —
// não se manda token nenhum. Usa curl (não o fetch nativo do Node, que não
// passa pela mesma camada de interceptação do proxy neste ambiente).
async function get(pathname, { shop, params } = {}){
  const url = new URL(BASE + pathname);
  for (const [k, v] of Object.entries(params || {})) if (v != null) url.searchParams.set(k, v);
  await pace();
  const curlArgs = ['-sS', '-w', '\n%{http_code}', url.toString()];
  if (shop) curlArgs.push('-H', `x-shop: ${shop}`);
  let lastErr;
  for (let tent = 0; tent < 3; tent++){
    const { stdout } = await execFileP('curl', curlArgs, { maxBuffer: 1024*1024*64 });
    const idx = stdout.lastIndexOf('\n');
    const status = Number(stdout.slice(idx+1));
    const bodyTxt = stdout.slice(0, idx);
    if (status >= 200 && status < 300) return JSON.parse(bodyTxt);
    if (status === 429 || status >= 500){ lastErr = new Error(`HTTP ${status}`); await new Promise(r => setTimeout(r, 2000*(tent+1))); continue; }
    throw new Error(`GET ${url.pathname} -> HTTP ${status}: ${bodyTxt.slice(0,300)}`);
  }
  throw lastErr;
}

const LOJAS = [
  { shopId: 1885, nome: 'Nave Tatuapé' },
  { shopId: 2086, nome: 'Nave São José dos Campos I' },
  { shopId: 3094, nome: 'Nave São José dos Campos II' },
  { shopId: 3096, nome: 'Nave Jacareí' },
  { shopId: 3113, nome: 'Nave Vila Prudente' },
  { shopId: 3114, nome: 'Nave Planalto Paulista' },
  { shopId: 3115, nome: 'Nave Casa Verde' },
  { shopId: 3116, nome: 'Nave Tucuruvi' },
  { shopId: 3117, nome: 'Nave Lapa' },
  { shopId: 3118, nome: 'Nave Vila Matilde' },
  { shopId: 3186, nome: 'Nave São Vicente' },
  { shopId: 3299, nome: 'Nave Jacareí II' },
  { shopId: 3626, nome: 'Nave Jabaquara' },
];
const SIZE_TO_PORTE = { MICRO: 0, SMALL: 0, MEDIUM: 1, BIG: 2, SUPERBIG: 2 };

function parseArgs(argv){
  const out = {};
  for (let i = 0; i < argv.length; i++){
    if (argv[i].startsWith('--')) out[argv[i].slice(2)] = argv[i+1]; i++;
  }
  return out;
}
const args = parseArgs(process.argv.slice(2));
const hoje = new Date();
const DE = args.de || `${hoje.getFullYear()}-${String(hoje.getMonth()+1).padStart(2,'0')}-01`;
const ATE = args.ate || hoje.toISOString().slice(0,10);
const HTML_PATH = path.resolve(args.html || './index.html');

async function paginateService(shopId){
  const out = [];
  let page = 1;
  while (true){
    const body = await get('/service', { shop: shopId, params: { page, limit: 200 } });
    out.push(...(body.data||[]));
    if (!body.pagination?.hasMore || !body.data?.length) break;
    page++;
  }
  return out;
}

async function main(){
  console.log(`Período: ${DE} a ${ATE}`);

  console.log('\nBaixando catálogo de preços por unidade...');
  const catalogoPrecos = new Map(); // `${shopId}|${serviceId}` -> priceTableByBreed[]
  for (const l of LOJAS){
    const lista = await paginateService(l.shopId).catch(() => []);
    for (const s of lista) catalogoPrecos.set(`${l.shopId}|${s.id}`, s.priceTableByBreed || []);
    console.log(`  ${l.nome}: ${lista.length} serviços`);
  }
  function precoPorRaca(shopId, serviceId, breedId){
    const tabela = catalogoPrecos.get(`${shopId}|${serviceId}`) || [];
    const porRaca = tabela.find(p => !p.default && (p.breeds||[]).includes(breedId));
    if (porRaca) return porRaca.price;
    const dflt = tabela.find(p => p.default) || tabela[0];
    return dflt ? dflt.price : 0;
  }

  console.log('\nBaixando diretório de pets (rede inteira, porte + raça)...');
  const petInfo = new Map(); // petId -> { porteFlag, breedId }
  {
    let lastId = 0, total = 0;
    while (true){
      const body = await get('/pet', { shop: LOJAS[0].shopId, params: { limit: 1000, lastId } });
      const rows = body.data || [];
      for (const p of rows) petInfo.set(p.id, { porteFlag: SIZE_TO_PORTE[p.size] ?? 0, breedId: p.breedId });
      total += rows.length;
      if (!body.pagination?.hasMore || !rows.length) break;
      lastId = rows[rows.length-1].id;
    }
    console.log(`  ${total} pets.`);
  }

  console.log(`\nBaixando agendamentos de ${DE} a ${ATE}...`);
  const grupos = new Map(); // unidade|servico|mes -> grupo
  for (const l of LOJAS){
    let lastId = 0, n = 0;
    while (true){
      const body = await get('/booking', { shop: l.shopId, params: { startDate: DE, endDate: ATE, status: 'DONE,DELIVERED', limit: 500, lastId } });
      const rows = body.data || [];
      for (const bk of rows){
        if (bk.segmentType !== 'PET_SHOP') continue;
        const servicos = bk.services || [];
        if (!servicos.length) continue;
        const info = petInfo.get(bk.petId);
        const porteFlag = info?.porteFlag ?? 0;
        const breedId = info?.breedId;
        const m = (bk.date || '').match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
        if (!m) continue;
        const dia = Number(m[1]);
        const mes = m[3] + '-' + m[2].padStart(2,'0');
        servicos.forEach(s => {
          const valorFinal = precoPorRaca(l.shopId, s.id, breedId);
          const chave = `${l.nome}|${s.name}|${mes}`;
          if (!grupos.has(chave)) grupos.set(chave, {
            unidade: l.nome, unidadeOriginal: l.nome, servico: s.name, mes,
            atendimentos: 0, atendimentosGrande: 0, atendimentosMedio: 0, valorTotal: 0, agendamentos: [],
          });
          const g = grupos.get(chave);
          g.atendimentos++;
          if (porteFlag === 2) g.atendimentosGrande++;
          else if (porteFlag === 1) g.atendimentosMedio++;
          g.valorTotal += valorFinal;
          g.agendamentos.push([bk.id, porteFlag, valorFinal, dia]);
          n++;
        });
      }
      if (!body.pagination?.hasMore || !rows.length) break;
      lastId = rows[rows.length-1].id;
    }
    console.log(`  ${l.nome}: ${n} serviços PET_SHOP`);
  }
  const candidatos = [...grupos.values()].map(g => ({ ...g, valorTotal: Math.round(g.valorTotal*100)/100 }));
  console.log(`\nTotal baixado: ${candidatos.reduce((s,g)=>s+g.atendimentos,0)} atendimentos em ${candidatos.length} grupos.`);

  // --- merge com o que já está no index.html (mesma lógica de mesclarGrupoHistorico/gruposComQueda) ---
  const html = fs.readFileSync(HTML_PATH, 'utf8');
  const m = html.match(/<script id="pedidos-state-data" type="application\/json">([\s\S]*?)<\/script>/);
  if (!m) throw new Error('Bloco pedidos-state-data não encontrado em ' + HTML_PATH);
  const pedidosState = JSON.parse(m[1]);

  function chaveHistoricoServico(item){ return [item.unidadeOriginal, item.servico, item.mes].join('|').toUpperCase(); }
  function mesclarGrupoHistorico(existente, novo){
    if (!existente) return novo;
    const podeReconciliar = Array.isArray(existente.agendamentos) && Array.isArray(novo.agendamentos);
    if (!podeReconciliar) return novo;
    const porCodigo = new Map(existente.agendamentos.map(a => [a[0], a]));
    let mudou = false;
    novo.agendamentos.forEach(b => {
      const a = porCodigo.get(b[0]);
      if (!a){ porCodigo.set(b[0], b); mudou = true; }
      else if (a[3] == null && b[3] != null){ porCodigo.set(b[0], b); mudou = true; }
    });
    if (!mudou) return existente;
    const agendamentos = [...porCodigo.values()];
    const atendimentos = agendamentos.length;
    const atendimentosGrande = agendamentos.reduce((s,a) => s + (a[1]===2?1:0), 0);
    const atendimentosMedio = agendamentos.reduce((s,a) => s + (a[1]===1?1:0), 0);
    const valorTotal = Math.round(agendamentos.reduce((s,a) => s+a[2], 0)*100)/100;
    return { ...existente, atendimentos, atendimentosGrande, atendimentosMedio, valorTotal, agendamentos };
  }
  function gruposComQueda(itensNovos, existentesArr){
    const existentes = new Map(existentesArr.map(i => [chaveHistoricoServico(i), i]));
    return itensNovos.map(i => {
      const ex = existentes.get(chaveHistoricoServico(i));
      if (!ex) return null;
      const podeReconciliar = Array.isArray(ex.agendamentos) && Array.isArray(i.agendamentos);
      if (podeReconciliar) return null;
      return i.atendimentos < ex.atendimentos ? { ...i, atendimentosAntes: ex.atendimentos } : null;
    }).filter(Boolean);
  }

  const quedas = gruposComQueda(candidatos, pedidosState.historicoServicos);
  if (quedas.length){
    console.error('\nABORTADO: gruposComQueda encontrou queda(s) — NÃO é seguro mesclar automaticamente.');
    console.error(JSON.stringify(quedas, null, 2));
    process.exit(1);
  }

  const totalAntes = pedidosState.historicoServicos.length;
  const mapa = new Map(pedidosState.historicoServicos.map(i => [chaveHistoricoServico(i), i]));
  let novosCount = 0, enriquecidosCount = 0;
  candidatos.forEach(i => {
    const k = chaveHistoricoServico(i);
    const antes = mapa.get(k);
    const depois = mesclarGrupoHistorico(antes, i);
    if (!antes) novosCount++;
    else if (depois !== antes) enriquecidosCount++;
    mapa.set(k, depois);
  });
  const finalArr = [...mapa.values()];

  // Substitui o estado inteiro (já temos ele parseado em memória) — mais
  // simples e seguro que tentar splicar só o trecho de historicoServicos
  // dentro do texto bruto do HTML.
  pedidosState.historicoServicos = finalArr;
  const antesDoScript = html.slice(0, m.index);
  const tagAbertura = m[0].slice(0, m[0].length - m[1].length - '</script>'.length);
  const depoisDoScript = html.slice(m.index + m[0].length);
  const htmlFinal = antesDoScript + tagAbertura + JSON.stringify(pedidosState) + '</script>' + depoisDoScript;
  fs.writeFileSync(HTML_PATH, htmlFinal);

  console.log(`\nMerge OK: ${totalAntes} -> ${finalArr.length} grupos (${novosCount} novos, ${enriquecidosCount} enriquecidos, 0 quedas).`);
  console.log(`\nRESUMO_JSON=${JSON.stringify({ de: DE, ate: ATE, baixados: candidatos.length, atendimentosBaixados: candidatos.reduce((s,g)=>s+g.atendimentos,0), novosCount, enriquecidosCount, totalFinal: finalArr.length })}`);
}

main().catch(e => { console.error('\nERRO:', e.message); process.exit(1); });
