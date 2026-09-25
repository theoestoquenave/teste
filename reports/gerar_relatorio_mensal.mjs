// Gera as imagens do relatório mensal de uso de produtos (Painel Nave):
// 1 imagem "geral por unidade" (líderes) + 1 imagem "detalhado" por unidade
// (coordenadora). Roda 100% local (Playwright + servidor estático embutido),
// não depende de rede além do Chromium já instalado no ambiente.
//
// Rodar todo dia 1 do mês: o usuário sobe os pedidos do mês seguinte no
// último dia do mês anterior (ex.: pedidos de outubro, aprovados em 30/09,
// contam como compra de outubro — ver mesSeguinte() no index.html). No dia
// 1, essas compras já estão refletidas nos dados, e o relatório mostra só
// os produtos com compra registrada NESSE mês — quem não foi repedido
// segue em uso (ainda pode render mais) e fica de fora, pedido explícito
// do usuário (25/09/2026).
//
// Uso: node gerar_relatorio_mensal.mjs [--out DIR] [--mes YYYY-MM]
//   --out  diretório de saída (default: ./saida, relativo a este arquivo)
//   --mes  mês de referência dos pedidos a considerar/rotular, formato
//          YYYY-MM (default: mês atual — o normal ao rodar no dia 1)
//
// Saída: <out>/Geral - <Mês Ano>.png e <out>/Detalhado - <Unidade> - <Mês
// Ano>.png (só unidades com pelo menos 1 produto pedido nesse mês), mais
// manifest.json listando os arquivos gerados.

import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import http from 'http';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');

function parseArgs() {
  const args = process.argv.slice(2);
  const out = {};
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--out') out.outDir = args[++i];
    if (args[i] === '--mes') out.mes = args[++i];
  }
  return out;
}

// Produtos que não devem aparecer nas imagens de relatório (continuam no
// comparativo interno do painel — pedido explícito do usuário em 25/09/2026).
const OCULTOS_NA_IMAGEM = new Set(['SOFT TOUCH 500ML', 'EXPERT OIL REDUX 250G']);

const MESES_PT = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
function mesLabel(mesYYYYMM) {
  const [y, m] = mesYYYYMM.split('-').map(Number);
  return `${MESES_PT[m - 1]}/${y}`;
}
// Versão sem "/" pra usar em nome de arquivo (a barra vira separador de pasta).
function mesLabelArquivo(mesYYYYMM) {
  const [y, m] = mesYYYYMM.split('-').map(Number);
  const nome = MESES_PT[m - 1];
  return `${nome.charAt(0).toUpperCase()}${nome.slice(1)} ${y}`;
}
function slug(s) {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-+|-+$/g, '').toLowerCase();
}

function status(l) {
  if (l.servicosEsperados == null) return 'sem_esperado';
  if (l.desvioPct < -20) return 'abaixo';
  if (l.desvioPct > 20) return 'acima';
  return 'dentro';
}

function serveStatic(root, port) {
  const server = http.createServer((req, res) => {
    const filePath = path.join(root, decodeURIComponent(req.url.split('?')[0]));
    fs.readFile(filePath, (err, data) => {
      if (err) { res.writeHead(404); res.end('not found'); return; }
      const ext = path.extname(filePath);
      const type = ext === '.html' ? 'text/html' : ext === '.js' ? 'application/javascript' : 'application/octet-stream';
      res.writeHead(200, { 'Content-Type': type });
      res.end(data);
    });
  });
  return new Promise(resolve => server.listen(port, () => resolve(server)));
}

async function main() {
  const { outDir: outDirArg, mes: mesArg } = parseArgs();
  const outDir = path.resolve(outDirArg || path.join(__dirname, 'saida'));
  fs.mkdirSync(outDir, { recursive: true });

  const hoje = new Date();
  const mes = mesArg || `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, '0')}`;
  const mesLbl = mesLabel(mes);
  const mesLblArquivo = mesLabelArquivo(mes);

  const port = 8700 + Math.floor(Math.random() * 200);
  const server = await serveStatic(REPO_ROOT, port);

  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    // CDN externo (cdnjs) fica bloqueado no sandbox — não é necessário pra
    // essa página (só a de exportação p/ fornecedor usa JSZip), mas evita
    // erro de console poluir o log.
    await page.route('**/jszip.min.js', route => route.fulfill({ status: 200, contentType: 'application/javascript', body: '' }));
    await page.goto(`http://localhost:${port}/index.html`, { waitUntil: 'load' });
    const linhasTodas = await page.evaluate(() => calcularComparativoUltimaCompra());
    // Compras reais mescladas (histórico + pedidos aprovados), pra saber se
    // um produto já tinha sido comprado ANTES da compra atual — primeira
    // compra de um produto não tem "desde a última compra" pra comparar
    // (pedido do usuário, 25/09/2026: excluir estreias, ex. linha Soft Care).
    const comprasRaw = await page.evaluate(() => comprasReaisMescladas());
    await page.close();

    const mesesPorChave = new Map(); // "unidade\u0001produto" -> Set de meses distintos comprados
    comprasRaw.forEach(hc => {
      if (!hc.unidade || !hc.produtoCatalogo || !hc.mes) return;
      const k = hc.unidade + '\u0001' + hc.produtoCatalogo;
      if (!mesesPorChave.has(k)) mesesPorChave.set(k, new Set());
      mesesPorChave.get(k).add(hc.mes);
    });

    // Só produtos com compra registrada NESTE mês (pedido feito/repetido) —
    // os que não foram repedidos ainda estão em uso e podem render mais,
    // não entram na comparação; produtos pedidos pela 1ª vez também ficam
    // de fora (sem compra anterior pra comparar) (pedido do usuário,
    // 25/09/2026).
    const linhas = linhasTodas.filter(l => {
      if (OCULTOS_NA_IMAGEM.has(l.produto)) return false;
      if (l.mesUltimaCompra !== mes) return false;
      const meses = mesesPorChave.get(l.unidade + '\u0001' + l.produto);
      const primeiraCompra = !meses || meses.size <= 1;
      return !primeiraCompra;
    });

    // --- Imagem geral por unidade ---
    const porUnidade = new Map();
    linhas.forEach(l => {
      if (!porUnidade.has(l.unidade)) porUnidade.set(l.unidade, { abaixo: 0, dentro: 0, acima: 0, sem_esperado: 0 });
      porUnidade.get(l.unidade)[status(l)]++;
    });
    const unidadesGeral = [...porUnidade.entries()].map(([unidade, c]) => {
      const avaliados = c.abaixo + c.dentro + c.acima;
      return {
        unidade, abaixo: c.abaixo, dentro: c.dentro, acima: c.acima, semDado: c.sem_esperado, avaliados,
        pctAbaixo: avaliados ? c.abaixo / avaliados * 100 : 0,
        pctDentro: avaliados ? c.dentro / avaliados * 100 : 0,
        pctAcima: avaliados ? c.acima / avaliados * 100 : 0,
      };
    });
    unidadesGeral.sort((a, b) => b.pctAbaixo - a.pctAbaixo);

    let templateGeral = fs.readFileSync(path.join(__dirname, 'template_geral.html'), 'utf-8');
    templateGeral = templateGeral.replace('__DATA__', JSON.stringify(unidadesGeral)).replace('__MES_LABEL__', mesLbl);
    const tmpGeral = path.join(outDir, '_tmp_geral.html');
    fs.writeFileSync(tmpGeral, templateGeral);

    const pageGeral = await browser.newPage({ viewport: { width: 960, height: 800 }, deviceScaleFactor: 1 });
    await pageGeral.goto('file://' + tmpGeral, { waitUntil: 'load' });
    const geralFileName = `Geral - ${mesLblArquivo}.png`;
    const geralPng = path.join(outDir, geralFileName);
    await (await pageGeral.$('.card')).screenshot({ path: geralPng });
    await pageGeral.close();
    fs.unlinkSync(tmpGeral);

    // --- Imagens detalhadas por unidade ---
    const unidadesTodas = [...new Set(linhas.map(l => l.unidade))].sort();
    const arquivosDetalhado = [];
    for (const unidade of unidadesTodas) {
      const rows = linhas.filter(l => l.unidade === unidade);
      rows.sort((a, b) => {
        const rank = x => x.servicosEsperados == null ? 3 : (x.desvioPct < -20 ? 0 : (x.desvioPct > 20 ? 2 : 1));
        const ra = rank(a), rb = rank(b);
        if (ra !== rb) return ra - rb;
        if (ra === 0) return a.desvioPct - b.desvioPct;
        if (ra === 2) return b.desvioPct - a.desvioPct;
        return a.produto.localeCompare(b.produto);
      });

      let templateDet = fs.readFileSync(path.join(__dirname, 'template_detalhado.html'), 'utf-8');
      templateDet = templateDet
        .replace('__UNIDADE__', JSON.stringify(unidade))
        .replace('__ROWS__', JSON.stringify(rows))
        .replace('__MES_LABEL__', mesLbl);
      const tmpDet = path.join(outDir, `_tmp_det_${slug(unidade)}.html`);
      fs.writeFileSync(tmpDet, templateDet);

      const pageDet = await browser.newPage({ viewport: { width: 960, height: 800 }, deviceScaleFactor: 1 });
      await pageDet.goto('file://' + tmpDet, { waitUntil: 'load' });
      const fileName = `Detalhado - ${unidade} - ${mesLblArquivo}.png`;
      const outPath = path.join(outDir, fileName);
      await (await pageDet.$('.card')).screenshot({ path: outPath });
      await pageDet.close();
      fs.unlinkSync(tmpDet);
      arquivosDetalhado.push({ unidade, arquivo: fileName, produtos: rows.length });
    }

    const manifest = { mes, mesLabel: mesLbl, geradoEm: new Date().toISOString(), geral: geralFileName, detalhado: arquivosDetalhado };
    fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify(manifest, null, 2));
    console.log(JSON.stringify(manifest, null, 2));
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch(err => { console.error(err); process.exit(1); });
