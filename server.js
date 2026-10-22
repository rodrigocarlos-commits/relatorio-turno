const express = require('express');
const playwright = require('playwright');
const app = express();

// Limite de payload aumentado para aceitar corpos grandes do JSON do Power Automate
app.use(express.json({ limit: '50mb' }));

// --- DICIONÁRIO DE REGIÕES E CORREDORES ---
const REGIOES_MAPA = {
  'CARAJAS': { nome: 'CARAJÁS', corredor: 'Corredor Norte' },
  'SALOBO': { nome: 'SALOBO', corredor: 'Corredor Norte' },
  'S11D': { nome: 'S11D', corredor: 'Corredor Norte' },
  'SLZ': { nome: 'SÃO LUÍS', corredor: 'Corredor Norte' },
  'SAO LUIZ': { nome: 'SÃO LUÍS', corredor: 'Corredor Norte' },
  'SÃO LUIZ': { nome: 'SÃO LUÍS', corredor: 'Corredor Norte' },
  'SOSSEGO': { nome: 'SOSSEGO', corredor: 'Corredor Norte' },
  'MOP': { nome: 'ONÇA PUMA', corredor: 'Corredor Norte' },
  'ONCA PUMA': { nome: 'ONÇA PUMA', corredor: 'Corredor Norte' },
  'ONÇA PUMA': { nome: 'ONÇA PUMA', corredor: 'Corredor Norte' },
  'MG': { nome: 'MG', corredor: 'Corredor Sul e Sudeste' },
  'VIX': { nome: 'ES', corredor: 'Corredor Sul e Sudeste' },
  'ES': { nome: 'ES', corredor: 'Corredor Sul e Sudeste' },
  'RJ': { nome: 'VALE RJ', corredor: 'Corredor Sul e Sudeste' },
  'VALE RJ': { nome: 'VALE RJ', corredor: 'Corredor Sul e Sudeste' }
};

function extrairRegiaoECorredor(anotacao) {
  if (!anotacao) return { nome: 'GERAL', corredor: 'Corredor Norte' };
  
  const tags = (Array.isArray(anotacao.tags) ? anotacao.tags : []).map(t => String(t).toUpperCase());
  const texto = String(anotacao.text || '').toUpperCase();
  const buscaTotal = `${tags.join(' ')} ${texto}`;

  for (const [chave, info] of Object.entries(REGIOES_MAPA)) {
    const regex = new RegExp(`\\b${chave}\\b`, 'i');
    if (regex.test(buscaTotal)) {
      return info;
    }
  }
  return { nome: 'GERAL', corredor: 'Corredor Norte' };
}

function formatarDataHora(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  if (isNaN(d.getTime())) return String(ts);
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function obterIntervaloTurno() {
  const agora = new Date();
  const hora = agora.getHours();
  let inicio = new Date(agora);
  let fim = new Date(agora);

  if (hora >= 6 && hora < 18) {
    inicio.setHours(6, 0, 0, 0);
    fim.setHours(18, 0, 0, 0);
  } else {
    if (hora >= 18) {
      inicio.setHours(18, 0, 0, 0);
      fim.setDate(fim.getDate() + 1);
      fim.setHours(6, 0, 0, 0);
    } else {
      inicio.setDate(inicio.getDate() - 1);
      inicio.setHours(18, 0, 0, 0);
      fim.setHours(6, 0, 0, 0);
    }
  }

  const pad = (n) => String(n).padStart(2, '0');
  return {
    meta_str: `${pad(inicio.getDate())}/${pad(inicio.getMonth() + 1)}/${inicio.getFullYear()} (${pad(inicio.getHours())}:${pad(inicio.getMinutes())} às ${pad(fim.getHours())}:${pad(fim.getMinutes())})`
  };
}

function limparEExtrairDescricao(textoBruto) {
  if (!textoBruto) return { tratando: 'ITOC', descricao: '', noc: '' };

  let texto = String(textoBruto)
    .replace(/[\x00-\x1F\x7F-\x9F]/g, '')
    .replace(/\[\s*\]/g, '')
    .replace(/C sá/g, 'Cls')
    .replace(/C-/g, 'Ch-')
    .replace(/^\[AGUARDANDO\s*-\s*\d+\]\s*/gi, '')
    .replace(/^\[(ATENDIMENTO|PROGRAMADO|INTERMITENTE|CONCLUIDO|CONCLUÍDO)\]\s*/gi, '');

  let tratando = 'ITOC';
  const matchTrat = texto.match(/^(.*?)\s+está tratando/i);
  if (matchTrat) tratando = matchTrat[1].trim();

  let descricao = texto;
  const matchDesc = texto.match(/"([^"]+)"/);
  if (matchDesc) descricao = matchDesc[1].trim();

  let noc = '';
  const matchNoc = texto.match(/\(chamado nº\s*([^)]+)\)/i);
  if (matchNoc) noc = matchNoc[1].trim();

  return { tratando, descricao, noc };
}

function gerarHtml(titulo, metaTurno, dataEmissao, itens, kpi) {
  let linhasHtml = '';
  if (!itens || itens.length === 0) {
    linhasHtml = '<tr><td colspan="9" style="text-align:center; padding: 20px; color: #94a3b8;">Nenhum atendimento nesta categoria para o turno atual.</td></tr>';
  } else {
    itens.forEach(item => {
      linhasHtml += `
        <tr>
          <td style="white-space: nowrap;">${item.dataAbertura || ''}</td>
          <td style="white-space: nowrap;">${item.dataAtualizacao || ''}</td>
          <td style="white-space: nowrap;">${item.dataFechamento || ''}</td>
          <td><b>${item.regiao || ''}</b></td>
          <td>${item.tratando || ''}</td>
          <td>${item.descricao || ''}</td>
          <td>${item.noc || ''}</td>
          <td>${item.vsc || ''}</td>
          <td style="text-align: center;">
            <span class="badge ${item.badgeClass}">${item.statusTxt}</span>
          </td>
        </tr>
      `;
    });
  }

  return `
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
      <meta charset="UTF-8">
      <title>${titulo}</title>
      <style>
        @page { size: A4 landscape; margin: 8mm; }
        * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        body { background: #fff; color: #333; margin: 0; padding: 10px; font-size: 11px; }
        .header-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 15px; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }
        .sub-title { color: #8c9ba5; font-size: 11px; font-weight: bold; margin: 0; }
        .main-title { color: #1e293b; font-size: 18px; font-weight: 800; margin: 2px 0; text-transform: uppercase; }
        .meta-info { color: #64748b; font-size: 11px; font-weight: 600; margin-top: 2px; }
        .tag-gerado { background: #fff8f0; border: 1px solid #ffedd5; color: #d97706; padding: 4px 10px; border-radius: 6px; font-size: 10px; font-weight: bold; text-align: right; }
        .kpi-container { display: flex; align-items: center; gap: 15px; background: #f8fafc; padding: 10px 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e2e8f0; }
        .big-number { font-size: 28px; font-weight: 800; color: #0f172a; line-height: 1; }
        .big-label { font-size: 10px; color: #64748b; font-weight: 600; display: block; margin-top: 2px; }
        .kpi-bars { display: flex; gap: 12px; flex: 1; align-items: center; border-left: 2px solid #e2e8f0; padding-left: 15px; }
        .kpi-item { font-size: 11px; font-weight: bold; color: #475569; display: flex; align-items: center; gap: 4px; }
        table { width: 100%; border-collapse: collapse; margin-top: 5px; }
        tr { page-break-inside: avoid; }
        th { text-align: left; padding: 6px 5px; border-bottom: 2px solid #e2e8f0; color: #64748b; font-size: 10px; font-weight: 700; text-transform: uppercase; background: #f8fafc; }
        td { padding: 6px 5px; border-bottom: 1px solid #f1f5f9; font-size: 10px; color: #334155; vertical-align: top; word-wrap: break-word; }
        .badge { padding: 3px 8px; border-radius: 10px; font-size: 10px; font-weight: 700; display: inline-block; white-space: nowrap; text-align: center; }
        .badge-concluido { background: #dcfce7; color: #15803d; }
        .badge-andamento { background: #fef3c7; color: #b45309; }
        .badge-programado { background: #dbeafe; color: #1d4ed8; }
        .badge-intermitente { background: #f3e8ff; color: #7e22ce; border: 1px solid #e9d5ff; }
      </style>
    </head>
    <body>
      <div class="report-card">
        <div class="header-top">
          <div>
            <p class="sub-title">NOC Aldak • Central de Alertas ITOC</p>
            <h1 class="main-title">${titulo}</h1>
            <p class="meta-info">Turno Vigente: ${metaTurno}</p>
          </div>
          <div class="tag-gerado">
            <div>Relatório Gerado em</div>
            <div>${dataEmissao}</div>
          </div>
        </div>

        <div class="kpi-container">
          <div>
            <div class="big-number">${itens ? itens.length : 0}</div>
            <span class="big-label">atendimentos neste relatório</span>
          </div>
          <div class="kpi-bars">
            <div class="kpi-item">🟢 <b>${kpi.concluidos}</b> Concluídos</div>
            <div class="kpi-item">🟡 <b>${kpi.andamento}</b> Em Andamento</div>
            <div class="kpi-item">🔵 <b>${kpi.programados}</b> Programados</div>
            <div class="kpi-item">🟣 <b>${kpi.intermitentes}</b> Intermitentes</div>
          </div>
        </div>

        <table>
          <thead>
            <tr>
              <th style="width: 105px;">Data / Abertura</th>
              <th style="width: 105px;">Atualização</th>
              <th style="width: 105px;">Fechamento</th>
              <th style="width: 100px;">Região / Site</th>
              <th style="width: 90px;">Tratando</th>
              <th>Descrição do Atendimento</th>
              <th style="width: 90px;">NOC</th>
              <th style="width: 45px;">VSC</th>
              <th style="width: 100px; text-align: center;">Status</th>
            </tr>
          </thead>
          <tbody>
            ${linhasHtml}
          </tbody>
        </table>
      </div>
    </body>
    </html>
  `;
}

async function renderizarPdfEImagem(html) {
  let browser = null;
  try {
    browser = await playwright.chromium.launch({
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
    });
    
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    await page.setContent(html, { waitUntil: 'domcontentloaded', timeout: 30000 });

    const pdfBuffer = await page.pdf({
      format: 'A4',
      landscape: true,
      printBackground: true,
      margin: { top: '8mm', right: '8mm', bottom: '8mm', left: '8mm' }
    });

    const imgBuffer = await page.screenshot({ fullPage: true, type: 'png' });
    await browser.close();

    return {
      pdfBase64: pdfBuffer.toString('base64'),
      imgBase64: imgBuffer.toString('base64')
    };
  } catch (err) {
    if (browser) await browser.close().catch(() => {});
    throw new Error(`Falha ao renderizar PDF/Imagem no Playwright: ${err.message}`);
  }
}

app.post('/gerar-relatorios', async (req, res) => {
  try {
    const payload = req.body || {};

    // PROTEÇÃO TOTAL DO PAYLOAD
    let anotacoes = [];
    if (Array.isArray(payload.anotacoes)) {
      anotacoes = payload.anotacoes;
    } else if (Array.isArray(payload.dados)) {
      anotacoes = payload.dados;
    } else if (Array.isArray(payload)) {
      anotacoes = payload;
    }

    const alertasAtivos = Array.isArray(payload.alertas_ativos) ? payload.alertas_ativos : [];

    const uidsAtivos = new Set();
    alertasAtivos.forEach(al => {
      if (al && al.labels && al.labels.__alert_rule_uid__) {
        uidsAtivos.add(al.labels.__alert_rule_uid__);
      }
    });

    const turno = obterIntervaloTurno();
    const dataEmissao = new Date().toLocaleString('pt-BR');

    const todosItens = [];

    anotacoes.forEach(an => {
      if (!an) return;
      
      const textoRaw = String(an.text || '');
      const tags = Array.isArray(an.tags) ? an.tags : [];
      const tagAlerta = tags.find(t => String(t).startsWith('alerta:'));
      const ruleUid = tagAlerta ? String(tagAlerta).replace('alerta:', '') : null;

      let ehConcluido = textoRaw.toUpperCase().includes('[CONCLUIDO]') || textoRaw.toUpperCase().includes('[CONCLUÍDO]');
      if (uidsAtivos.size > 0 && ruleUid && !uidsAtivos.has(ruleUid)) {
        ehConcluido = true;
      }

      const ehIntermitente = textoRaw.toUpperCase().includes('[INTERMITENTE]');
      const ehProgramado = textoRaw.toUpperCase().includes('ITOC-PROGRAMADO') || textoRaw.toUpperCase().includes('[PROGRAMADO]');

      let statusTxt = 'Em Andamento';
      let badgeClass = 'badge-andamento';

      if (ehConcluido) {
        statusTxt = 'Concluído';
        badgeClass = 'badge-concluido';
      } else if (ehIntermitente) {
        statusTxt = 'Intermitente';
        badgeClass = 'badge-intermitente';
      } else if (ehProgramado) {
        statusTxt = 'Programado';
        badgeClass = 'badge-programado';
      }

      const regInfo = extrairRegiaoECorredor(an);
      const extraido = limparEExtrairDescricao(textoRaw);

      todosItens.push({
        dataAbertura: formatarDataHora(an.time || an.created),
        dataAtualizacao: formatarDataHora(an.updated),
        dataFechamento: ehConcluido ? formatarDataHora(an.timeEnd || an.updated) : '',
        regiao: regInfo.nome,
        corredor: regInfo.corredor,
        tratando: extraido.tratando,
        descricao: extraido.descricao,
        noc: extraido.noc,
        vsc: '',
        statusTxt,
        badgeClass,
        ehConcluido
      });
    });

    const itensNorte = todosItens.filter(i => i.corredor === 'Corredor Norte' && !i.ehConcluido);
    const itensSul = todosItens.filter(i => i.corredor === 'Corredor Sul e Sudeste' && !i.ehConcluido);
    const itensGeral = todosItens.filter(i => i.ehConcluido);

    const categorias = [
      { chave: 'NORTE', titulo: 'RELATÓRIO DE ATENDIMENTOS • CORREDOR NORTE', itens: itensNorte },
      { chave: 'SUL_SUDESTE', titulo: 'RELATÓRIO DE ATENDIMENTOS • CORREDOR SUL E SUDESTE', itens: itensSul },
      { chave: 'GERAL_CONCLUIDOS', titulo: 'RELATÓRIO GERAL • ATENDIMENTOS CONCLUÍDOS DO TURNO', itens: itensGeral }
    ];

    const relatoriosOutput = [];

    for (const cat of categorias) {
      const kpi = {
        concluidos: cat.itens.filter(i => i.statusTxt === 'Concluído').length,
        andamento: cat.itens.filter(i => i.statusTxt === 'Em Andamento').length,
        programados: cat.itens.filter(i => i.statusTxt === 'Programado').length,
        intermitentes: cat.itens.filter(i => i.statusTxt === 'Intermitente').length
      };

      const html = gerarHtml(cat.titulo, turno.meta_str, dataEmissao, cat.itens, kpi);
      const { pdfBase64, imgBase64 } = await renderizarPdfEImagem(html);

      const dataHoje = new Date().toISOString().split('T')[0];
      const nomeBase = `Relatorio_GMG_${cat.chave}_${dataHoje}`;

      relatoriosOutput.push({
        regiao: cat.chave,
        filename: `${nomeBase}.pdf`,
        image_filename: `${nomeBase}.png`,
        pdf_base64: pdfBase64,
        image_base64: imgBase64
      });
    }

    return res.status(200).json({ relatorios: relatoriosOutput });
  } catch (e) {
    console.error("Erro no processamento:", e);
    return res.status(500).json({ error: e.message });
  }
});

const PORT = process.env.PORT || 10000;
app.listen(PORT, () => console.log(`Servidor a rodar na porta ${PORT}`));
