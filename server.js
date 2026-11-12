const express = require('express');
const playwright = require('playwright');
const app = express();

app.use(express.json({ limit: '50mb' }));

// --- DICIONÁRIO DE REGIÕES, SITES E CORREDORES ---
const REGIOES_MAPA = {
  // Corredor Norte
  'CARAJAS': { nome: 'CARAJÁS', corredor: 'Corredor Norte' },
  'CARAJÁS': { nome: 'CARAJÁS', corredor: 'Corredor Norte' },
  'PALMARES': { nome: 'CARAJÁS', corredor: 'Corredor Norte' },
  'BOCAINA': { nome: 'CARAJÁS', corredor: 'Corredor Norte' },
  'N4EEN': { nome: 'CARAJÁS', corredor: 'Corredor Norte' },
  'TORRE SUL': { nome: 'CARAJÁS', corredor: 'Corredor Norte' },
  'SALOBO': { nome: 'SALOBO', corredor: 'Corredor Norte' },
  'CORTE 7': { nome: 'SALOBO', corredor: 'Corredor Norte' },
  'S11D': { nome: 'S11D', corredor: 'Corredor Norte' },
  'OFICINA MINA': { nome: 'S11D', corredor: 'Corredor Norte' },
  'OVERLAND': { nome: 'S11D', corredor: 'Corredor Norte' },
  'MINA S16': { nome: 'S11D', corredor: 'Corredor Norte' },
  'TORRE 140': { nome: 'S11D', corredor: 'Corredor Norte' },
  'MIRANTE': { nome: 'S11D', corredor: 'Corredor Norte' },
  'SLZ': { nome: 'SÃO LUÍS', corredor: 'Corredor Norte' },
  'SAO LUIZ': { nome: 'SÃO LUÍS', corredor: 'Corredor Norte' },
  'SÃO LUIZ': { nome: 'SÃO LUÍS', corredor: 'Corredor Norte' },
  'SOSSEGO': { nome: 'SOSSEGO', corredor: 'Corredor Norte' },
  'MARIA LUCIA': { nome: 'SOSSEGO', corredor: 'Corredor Norte' },
  'BACABA': { nome: 'SOSSEGO', corredor: 'Corredor Norte' },
  'MOP': { nome: 'ONÇA PUMA', corredor: 'Corredor Norte' },
  'ONCA PUMA': { nome: 'ONÇA PUMA', corredor: 'Corredor Norte' },
  'ONÇA PUMA': { nome: 'ONÇA PUMA', corredor: 'Corredor Norte' },

  // Corredor Sul e Sudeste
  'MG': { nome: 'MG', corredor: 'Corredor Sul e Sudeste' },
  'BRUCUTU': { nome: 'MG', corredor: 'Corredor Sul e Sudeste' },
  'BRUCU': { nome: 'MG', corredor: 'Corredor Sul e Sudeste' },
  'PICO DO MONGE': { nome: 'MG', corredor: 'Corredor Sul e Sudeste' },
  'VIGA': { nome: 'MG', corredor: 'Corredor Sul e Sudeste' },
  'ABOBORAS': { nome: 'MG', corredor: 'Corredor Sul e Sudeste' },
  'SERRA GERAL': { nome: 'MG', corredor: 'Corredor Sul e Sudeste' },
  'JOAO PEREIRA': { nome: 'MG', corredor: 'Corredor Sul e Sudeste' },
  'SAO GONCALO': { nome: 'MG', corredor: 'Corredor Sul e Sudeste' },
  'CAVA CPX': { nome: 'MG', corredor: 'Corredor Sul e Sudeste' },
  'GALINHEIRO': { nome: 'MG', corredor: 'Corredor Sul e Sudeste' },
  'VIX': { nome: 'ES', corredor: 'Corredor Sul e Sudeste' },
  'ES': { nome: 'ES', corredor: 'Corredor Sul e Sudeste' },
  'RJ': { nome: 'VALE RJ', corredor: 'Corredor Sul e Sudeste' },
  'VALE RJ': { nome: 'VALE RJ', corredor: 'Corredor Sul e Sudeste' },
  'TERNIUM': { nome: 'VALE RJ', corredor: 'Corredor Sul e Sudeste' },
  'TIG': { nome: 'VALE RJ', corredor: 'Corredor Sul e Sudeste' }
};

function normalizarTexto(str) {
  return String(str || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toUpperCase();
}

function extrairRegiaoECorredor(anotacao, descricaoLimpa = '') {
  const tags = (Array.isArray(anotacao?.tags) ? anotacao.tags : []).map(t => normalizarTexto(t));
  const texto = normalizarTexto(`${anotacao?.text || ''} ${descricaoLimpa}`);

  for (const tag of tags) {
    if (REGIOES_MAPA[tag]) {
      return REGIOES_MAPA[tag];
    }
  }

  for (const [chave, info] of Object.entries(REGIOES_MAPA)) {
    const chaveNorm = normalizarTexto(chave);
    const regex = new RegExp(`\\b${chaveNorm}\\b`, 'i');
    if (regex.test(texto)) {
      return info;
    }
  }

  return { nome: 'GERAL', corredor: 'Corredor Norte' };
}

// Extrai o nome limpo do Site para agrupar todos os alarmes do mesmo site
function extrairNomeSite(descricao) {
  if (!descricao) return '';
  let limpo = normalizarTexto(descricao)
    .replace(/\b(ALARME|ALERTA|ENLACE|ENLACES|MICROONDAS|PTP|CONEC|RSSI|SATELITES|SATELITE|NODE|BSC\s*\d*|PRINCIPAL|REDUNDANTE|POTENCIA|REFLETIDA|TENSAO|BATERIA|DC|CHUMBO|CONECTIVIDADE|INTERNET|WAN|DIFL|LATENCIA|CAPACIDADE|TANQ|GMG|ACIONADO|COM|AC|NORMAL|ATENDIMENTO|ALDAK|VALE|ATIVO|FASES|REDE|BANCO|BATERIAS|PDE|M\.\s*AUT|MINA\s*AUT|L[0-4]|C[0-4]|TR\d+)\b/g, ' ')
    .replace(/[-–—/()]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  if (limpo.includes('BRUCU')) limpo = 'BRUCUTU';

  return limpo.length >= 3 ? limpo : '';
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

function formatarTimestampConclusao(texto) {
  return String(texto || '').replace(
    /(CONCLU[IÍ]DO[_\s]+EM\s*:\s*)(\d{13}|\d{10})\b/gi,
    (trecho, rotulo, valor) => {
      const numero = Number(valor);
      const data = new Date(valor.length === 10 ? numero * 1000 : numero);
      if (Number.isNaN(data.getTime())) return trecho;
      const formatada = new Intl.DateTimeFormat('pt-BR', {
        timeZone: 'America/Sao_Paulo',
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
      }).format(data);
      return `${rotulo.replace(/[_\s]+/g, ' ').trim()} ${formatada}`;
    }
  );
}

function limparEExtrairDescricao(textoBruto) {
  if (!textoBruto) return { tratando: 'ITOC', descricao: '', noc: '' };

  const textoOriginal = String(textoBruto).replace(/[\x00-\x1F\x7F-\x9F]/g, '');
  const matchConclusao = textoOriginal.match(/CONCLU[IÍ]DO[_\s]+EM\s*:\s*(\d{13}|\d{10})\b/i);
  const textoComData = formatarTimestampConclusao(textoOriginal);

  let texto = textoComData
    .replace(/\[\s*\]/g, '')
    .replace(/C sá/g, 'Cls')
    .replace(/^\[AGUARDANDO\s*-\s*\d+\]\s*/gi, '')
    .replace(/^\[(ATENDIMENTO|PROGRAMADO|INTERMITENTE|CONCLUIDO|CONCLUÍDO)\]\s*/gi, '');

  let tratando = 'ITOC';
  const matchTrat = texto.match(/^(.*?)\s+está tratando/i);
  if (matchTrat) {
    tratando = matchTrat[1].trim();
  } else if (matchConclusao) {
    const restante = texto.replace(/.*?CONCLU[IÍ]DO[_\s]+EM\s*:\s*\d{13}|.*?CONCLU[IÍ]DO[_\s]+EM\s*:\s*\d{10}/i, '')
      .replace(/\[\s*CONCLU[IÍ]DO\s*\]/gi, '')
      .trim();
    const dataConclusao = texto.match(/CONCLU[IÍ]DO[_\s]+EM\s*:\s*\d{2}\/\d{2}\/\d{4}[^\]]*/i);
    const dataTexto = dataConclusao ? dataConclusao[0].replace(/_/g, ' ') : '';
    tratando = [dataTexto, restante].filter(Boolean).join(' — ').trim();
  }

  let descricao = texto;
  const matchDesc = texto.match(/"([^"]+)"/);
  if (matchDesc) descricao = matchDesc[1].trim();

  let noc = '';
  const matchNoc = texto.match(/\(chamado nº\s*([^)]+)\)/i);
  if (matchNoc) noc = matchNoc[1].trim().replace(/\bINCh-/gi, 'INC-');

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
          <td><b>${item.regiaoSite || ''}</b></td>
          <td>${item.tratando || ''}</td>
          <td>${item.descricaoHtml || item.descricao || ''}</td>
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
        .alarme-bloco { margin-bottom: 5px; }
        .alarme-bloco:last-child { margin-bottom: 0; }
        .historico-datas { font-size: 9px; color: #64748b; line-height: 1.35; margin-left: 8px; }
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
            <span class="big-label">sites/atendimentos neste relatório</span>
          </div>
          <div class="kpi-bars">
            <div class="kpi-item">🟡 <b>${kpi.andamento}</b> Em Andamento</div>
            <div class="kpi-item">🔵 <b>${kpi.programados}</b> Programados</div>
            <div class="kpi-item">🟣 <b>${kpi.intermitentes}</b> Intermitentes</div>
          </div>
        </div>

        <table>
          <thead>
            <tr>
              <th style="width: 95px;">1ª Abertura</th>
              <th style="width: 95px;">Últ. Atualização</th>
              <th style="width: 95px;">Fechamento</th>
              <th style="width: 125px;">Região / Site</th>
              <th style="width: 85px;">Tratando</th>
              <th>Alarmes do Site / Histórico de Registros</th>
              <th style="width: 85px;">NOC</th>
              <th style="width: 40px;">VSC</th>
              <th style="width: 95px; text-align: center;">Status</th>
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
    throw new Error(`Falha no Playwright: ${err.message}`);
  }
}

app.post('/gerar-relatorios', async (req, res) => {
  try {
    const payload = req.body || {};

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
    const mapaNomesReaisPorUid = new Map();
    const uidsPresentesNasAnotacoes = new Set();

    alertasAtivos.forEach(al => {
      if (al && al.labels && al.labels.__alert_rule_uid__) {
        const uid = al.labels.__alert_rule_uid__;
        uidsAtivos.add(uid);

        const nomeReal = al.labels.alertname || (al.annotations && (al.annotations.summary || al.annotations.title)) || '';
        if (nomeReal) {
          mapaNomesReaisPorUid.set(uid, String(nomeReal).trim());
        }
      }
    });

    // Mapa para concentrar alarmes do MESMO SITE e com o MESMO NOC em uma única linha
    const gruposPorSiteENoc = new Map();

    function registrarOcorrenciaNoGrupo({
      regInfo,
      nomeSite,
      nomeAlarme,
      tratando,
      noc,
      statusTxt,
      badgeClass,
      tsAbertura,
      tsAtualizacao
    }) {
      const regiaoSite = nomeSite && !nomeSite.includes(regInfo.nome)
        ? `${regInfo.nome} • ${nomeSite}`
        : regInfo.nome;

      const nocNormalizado = normalizarTexto(noc || '').replace(/\s+/g, ' ').trim();

      // Concentra na mesma linha se for o MESMO SITE e tiver a MESMA INFORMAÇÃO NA COLUNA NOC
      const chaveGrupo = nomeSite
        ? `${regInfo.corredor}::${regInfo.nome}::${nomeSite}::${nocNormalizado}`
        : `${regInfo.corredor}::${regInfo.nome}::${normalizarTexto(nomeAlarme)}::${nocNormalizado}`;

      if (!gruposPorSiteENoc.has(chaveGrupo)) {
        gruposPorSiteENoc.set(chaveGrupo, {
          minAbertura: tsAbertura,
          maxAtualizacao: tsAtualizacao,
          regiao: regInfo.nome,
          regiaoSite,
          corredor: regInfo.corredor,
          tratando: tratando || 'ITOC',
          noc: (noc || '').trim(),
          vsc: '',
          statusTxt,
          badgeClass,
          alarmesDoSite: new Map()
        });
      }

      const grupo = gruposPorSiteENoc.get(chaveGrupo);

      if (tsAbertura && (!grupo.minAbertura || tsAbertura < grupo.minAbertura)) {
        grupo.minAbertura = tsAbertura;
      }
      if (tsAtualizacao && tsAtualizacao > grupo.maxAtualizacao) {
        grupo.maxAtualizacao = tsAtualizacao;
      }

      if (statusTxt === 'Em Andamento') {
        grupo.statusTxt = 'Em Andamento';
        grupo.badgeClass = 'badge-andamento';
      } else if (statusTxt === 'Programado' && grupo.statusTxt === 'Intermitente') {
        grupo.statusTxt = 'Programado';
        grupo.badgeClass = 'badge-programado';
      }

      if (tratando && tratando !== 'ITOC') {
        grupo.tratando = tratando;
      }

      const chaveAlarme = normalizarTexto(nomeAlarme);
      if (!grupo.alarmesDoSite.has(chaveAlarme)) {
        grupo.alarmesDoSite.set(chaveAlarme, {
          nomeOriginal: nomeAlarme,
          registros: []
        });
      }

      grupo.alarmesDoSite.get(chaveAlarme).registros.push({
        abertura: tsAbertura,
        atualizacao: tsAtualizacao
      });
    }

    // 1. Processa as anotações retornadas
    anotacoes.forEach(an => {
      if (!an) return;

      const textoRaw = String(an.text || '');
      const tags = Array.isArray(an.tags) ? an.tags : [];
      const tagAlerta = tags.find(t => String(t).startsWith('alerta:'));
      const ruleUid = tagAlerta ? String(tagAlerta).replace('alerta:', '') : null;

      if (ruleUid) uidsPresentesNasAnotacoes.add(ruleUid);

      const textoStatus = normalizarTexto(`${textoRaw} ${tags.join(' ')}`);

      let ehConcluido = /\[\s*CONCLUID[OA]S?\s*\]/.test(textoStatus)
        || /\bSTATUS\s*[:=]\s*CONCLUID[OA]S?\b/.test(textoStatus);

      if (uidsAtivos.size > 0 && ruleUid && !uidsAtivos.has(ruleUid)) {
        ehConcluido = true;
      }

      if (ehConcluido) return;

      const ehIntermitente = textoRaw.toUpperCase().includes('[INTERMITENTE]');
      const ehProgramado = textoRaw.toUpperCase().includes('ITOC-PROGRAMADO') || textoRaw.toUpperCase().includes('[PROGRAMADO]');

      let statusTxt = 'Em Andamento';
      let badgeClass = 'badge-andamento';

      if (ehIntermitente) {
        statusTxt = 'Intermitente';
        badgeClass = 'badge-intermitente';
      } else if (ehProgramado) {
        statusTxt = 'Programado';
        badgeClass = 'badge-programado';
      }

      const extraido = limparEExtrairDescricao(textoRaw);
      const nomeAlarmeFinal = (ruleUid && mapaNomesReaisPorUid.has(ruleUid))
        ? mapaNomesReaisPorUid.get(ruleUid)
        : extraido.descricao;

      const regInfo = extrairRegiaoECorredor(an, nomeAlarmeFinal);
      const nomeSite = extrairNomeSite(nomeAlarmeFinal);

      registrarOcorrenciaNoGrupo({
        regInfo,
        nomeSite,
        nomeAlarme: nomeAlarmeFinal,
        tratando: extraido.tratando,
        noc: extraido.noc,
        statusTxt,
        badgeClass,
        tsAbertura: Number(an.time || an.created || 0),
        tsAtualizacao: Number(an.updated || an.time || an.created || 0)
      });
    });

    // 2. Resgata alarmes antigos ativos caso não tenham vindo nas anotações
    alertasAtivos.forEach(al => {
      if (!al || !al.labels) return;
      const uid = al.labels.__alert_rule_uid__;
      if (!uid || uidsPresentesNasAnotacoes.has(uid)) return;

      const estado = String(al.state || al.status?.state || '').toLowerCase();
      if (estado && estado !== 'alerting' && estado !== 'firing') return;

      const nomeReal = mapaNomesReaisPorUid.get(uid) || al.labels.alertname || '';
      if (!nomeReal) return;

      const regInfo = extrairRegiaoECorredor({ tags: Object.values(al.labels || {}), text: nomeReal }, nomeReal);
      const nomeSite = extrairNomeSite(nomeReal);
      const tsInicio = al.startsAt ? new Date(al.startsAt).getTime() : Date.now();

      registrarOcorrenciaNoGrupo({
        regInfo,
        nomeSite,
        nomeAlarme: nomeReal,
        tratando: 'ITOC',
        noc: '',
        statusTxt: 'Em Andamento',
        badgeClass: 'badge-andamento',
        tsAbertura: tsInicio,
        tsAtualizacao: Date.now()
      });
    });

    // Monta as linhas consolidadas
    const todosItens = Array.from(gruposPorSiteENoc.values()).map(g => {
      const blocosAlarmesHtml = [];

      g.alarmesDoSite.forEach(alInfo => {
        alInfo.registros.sort((a, b) => a.abertura - b.abertura);
        const datasUnicas = [];
        const vistos = new Set();

        alInfo.registros.forEach(r => {
          const dtAb = formatarDataHora(r.abertura);
          const dtAt = formatarDataHora(r.atualizacao);
          const textoRegistro = dtAt && dtAt !== dtAb ? `${dtAb} (att ${dtAt})` : dtAb;
          if (textoRegistro && !vistos.has(textoRegistro)) {
            vistos.add(textoRegistro);
            datasUnicas.push(textoRegistro);
          }
        });

        blocosAlarmesHtml.push(`
          <div class="alarme-bloco">
            <div><b>• ${alInfo.nomeOriginal}</b></div>
            <div class="historico-datas">
              Registros (${alInfo.registros.length}x): ${datasUnicas.join(' &bull; ')}
            </div>
          </div>
        `);
      });

      return {
        dataAbertura: formatarDataHora(g.minAbertura),
        dataAtualizacao: formatarDataHora(g.maxAtualizacao),
        dataFechamento: '',
        regiao: g.regiao,
        regiaoSite: g.regiaoSite,
        corredor: g.corredor,
        tratando: g.tratando,
        descricao: Array.from(g.alarmesDoSite.keys()).join(', '),
        descricaoHtml: blocosAlarmesHtml.join(''),
        noc: g.noc,
        vsc: g.vsc,
        statusTxt: g.statusTxt,
        badgeClass: g.badgeClass
      };
    });

    const turno = obterIntervaloTurno();
    const dataEmissao = new Date().toLocaleString('pt-BR');

    const itensNorte = todosItens.filter(i => i.corredor === 'Corredor Norte');
    const itensSul = todosItens.filter(i => i.corredor === 'Corredor Sul e Sudeste');

    const categorias = [
      { chave: 'NORTE', titulo: 'RELATÓRIO DE ATENDIMENTOS • CORREDOR NORTE', itens: itensNorte },
      { chave: 'SUL_SUDESTE', titulo: 'RELATÓRIO DE ATENDIMENTOS • CORREDOR SUL E SUDESTE', itens: itensSul }
    ];

    const relatoriosOutput = [];

    for (const cat of categorias) {
      const kpi = {
        concluidos: 0,
        andamento: cat.itens.filter(i => i.statusTxt === 'Em Andamento').length,
        programados: cat.itens.filter(i => i.statusTxt === 'Programado').length,
        intermitentes: cat.itens.filter(i => i.statusTxt === 'Intermitente').length
      };

      const html = gerarHtml(cat.titulo, turno.meta_str, dataEmissao, cat.itens, kpi);
      const { pdfBase64, imgBase64 } = await renderizarPdfEImagem(html);

      const dataHoje = new Date().toISOString().split('T')[0];
      const nomeBase = `Relatorio_${cat.chave}_${dataHoje}`;

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
