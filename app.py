import base64
import datetime
import html
import os
import re
import pandas as pd
from flask import Flask, jsonify, request
from jinja2 import Template
import playwright.async_api as playwright_async

app = Flask(__name__)

# --- MAPA DE REGIÕES E CORREDORES ---
REGIOES_MAPA = {
    'CARAJAS': ('CARAJÁS', 'Corredor Norte'),
    'SALOBO': ('SALOBO', 'Corredor Norte'),
    'S11D': ('S11D', 'Corredor Norte'),
    'SLZ': ('SÃO LUÍS', 'Corredor Norte'),
    'SAO LUIZ': ('SÃO LUÍS', 'Corredor Norte'),
    'SÃO LUIZ': ('SÃO LUÍS', 'Corredor Norte'),
    'SOSSEGO': ('SOSSEGO', 'Corredor Norte'),
    'MOP': ('ONÇA PUMA', 'Corredor Norte'),
    'ONCA PUMA': ('ONÇA PUMA', 'Corredor Norte'),
    'ONÇA PUMA': ('ONÇA PUMA', 'Corredor Norte'),
    'MG': ('MG', 'Corredor Sul e Sudeste'),
    'VIX': ('ES', 'Corredor Sul e Sudeste'),
    'ES': ('ES', 'Corredor Sul e Sudeste'),
    'RJ': ('VALE RJ', 'Corredor Sul e Sudeste'),
    'VALE RJ': ('VALE RJ', 'Corredor Sul e Sudeste')
}

def extrair_regiao_e_corredor(anotacao):
    """Extrai estritamente APENAS o nome da Região (ex: MG, SOSSEGO) e define o Corredor."""
    tags = anotacao.get('tags', [])
    texto = str(anotacao.get('text', '')).upper()
    tags_str = ' '.join([str(t).upper() for t in tags])
    busca_total = f"{tags_str} {texto}"

    for chave, (nome_regiao, corredor) in REGIOES_MAPA.items():
        if re.search(r'\b' + re.escape(chave) + r'\b', busca_total):
            return nome_regiao, corredor
            
    return 'GERAL', 'Corredor Norte'

def formatar_data_hora(ts):
    if not ts:
        return ""
    try:
        if isinstance(ts, (int, float)):
            dt = datetime.datetime.fromtimestamp(ts / 1000.0)
            return dt.strftime("%d/%m/%Y %H:%M")
        dt = pd.to_datetime(ts)
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(ts)

def obter_intervalo_turno():
    agora = datetime.datetime.now()
    hora = agora.hour

    if 5 <= hora < 18:
        inicio = agora.replace(hour=5, minute=0, second=0, microsecond=0)
        fim = agora.replace(hour=18, minute=0, second=0, microsecond=0)
    else:
        if hora >= 18:
            inicio = agora.replace(hour=17, minute=0, second=0, microsecond=0)
            fim = (agora + datetime.timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
        else:
            inicio = (agora - datetime.timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)
            fim = agora.replace(hour=6, minute=0, second=0, microsecond=0)

    return {
        "inicio_ms": int(inicio.timestamp() * 1000),
        "fim_ms": int(fim.timestamp() * 1000),
        "meta_str": f"{inicio.strftime('%d/%m/%Y')} ({inicio.strftime('%H:%M')} às {fim.strftime('%H:%M')})"
    }

def limpar_e_extrair_descricao(texto_bruto):
    """Remove todo o lixo do Grafana ([AGUARDANDO], C sá, [], etc)."""
    if not texto_bruto:
        return "ITOC", "", ""
    
    texto = html.unescape(str(texto_bruto))
    texto = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', texto)
    
    # Limpeza de lixo e caracteres estranhos
    texto = re.sub(r'\[\s*\]', '', texto)
    texto = texto.replace("C sá", "Cls").replace("C-", "Ch-")
    
    # Remove prefixos do Grafana/Userscript
    texto = re.sub(r'^\[AGUARDANDO\s*-\s*\d+\]\s*', '', texto, flags=re.IGNORECASE)
    texto = re.sub(r'^\[(ATENDIMENTO|PROGRAMADO|INTERMITENTE|CONCLUIDO|CONCLUÍDO)\]\s*', '', texto, flags=re.IGNORECASE)
    
    tratando = "ITOC"
    match_trat = re.search(r'^(.*?)\s+está tratando', texto, re.IGNORECASE)
    if match_trat:
        tratando = match_trat.group(1).strip()

    descricao = texto
    match_desc = re.search(r'"([^"]+)"', texto)
    if match_desc:
        descricao = match_desc.group(1).strip()

    noc = ""
    match_noc = re.search(r'\(chamado nº\s*([^)]+)\)', texto, re.IGNORECASE)
    if match_noc:
        noc = match_noc.group(1).strip()

    return tratando, descricao, noc

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>{{ titulo }}</title>
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
                <h1 class="main-title">{{ titulo }}</h1>
                <p class="meta-info">Turno Vigente: {{ meta_turno }}</p>
            </div>
            <div class="tag-gerado">
                <div>Relatório Gerado em</div>
                <div>{{ data_emissao }}</div>
            </div>
        </div>

        <div class="kpi-container">
            <div>
                <div class="big-number">{{ itens|length }}</div>
                <span class="big-label">atendimentos neste relatório</span>
            </div>
            <div class="kpi-bars">
                <div class="kpi-item">🟢 <b>{{ total_concluidos }}</b> Concluídos</div>
                <div class="kpi-item">🟡 <b>{{ total_andamento }}</b> Em Andamento</div>
                <div class="kpi-item">🔵 <b>{{ total_programados }}</b> Programados</div>
                <div class="kpi-item">🟣 <b>{{ total_intermitentes }}</b> Intermitentes</div>
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
                {% if itens|length == 0 %}
                <tr>
                    <td colspan="9" style="text-align:center; padding: 20px; color: #94a3b8;">Nenhum atendimento nesta categoria para o turno atual.</td>
                </tr>
                {% else %}
                {% for item in itens %}
                <tr>
                    <td style="white-space: nowrap;">{{ item.dataAbertura }}</td>
                    <td style="white-space: nowrap;">{{ item.dataAtualizacao }}</td>
                    <td style="white-space: nowrap;">{{ item.dataFechamento }}</td>
                    <td><b>{{ item.regiao }}</b></td>
                    <td>{{ item.tratando }}</td>
                    <td>{{ item.descricao }}</td>
                    <td>{{ item.noc }}</td>
                    <td>{{ item.vsc }}</td>
                    <td style="text-align: center;">
                        <span class="badge {{ item.badge_class }}">{{ item.status_txt }}</span>
                    </td>
                </tr>
                {% endfor %}
                {% endif %}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

async def render_pdf_and_image(html_content):
    async with playwright_async.async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        await page.set_content(html_content, wait_until="networkidle")
        
        pdf_bytes = await page.pdf(format="A4", landscape=True, print_background=True, margin={"top": "8mm", "right": "8mm", "bottom": "8mm", "left": "8mm"})
        image_bytes = await page.screenshot(full_page=True, type="png")
        await browser.close()
        return pdf_bytes, image_bytes

@app.route("/gerar-relatorios", methods=["POST"])
async def processar_dados():
    try:
        payload = request.get_json(force=True)
        
        # Suporta tanto payload no formato 'anotacoes' quanto 'dados'
        anotacoes = payload.get("anotacoes", payload.get("dados", []))
        alertas_ativos = payload.get("alertas_ativos", [])
        
        if not isinstance(anotacoes, list):
            anotacoes = []
        if not isinstance(alertas_ativos, list):
            alertas_ativos = []

        # Mapeia uids dos alertas que estão efetivamente ativos
        uids_ativos = set()
        for al in alertas_ativos:
            if isinstance(al, dict):
                uid = al.get('labels', {}).get('__alert_rule_uid__')
                if uid:
                    uids_ativos.add(uid)

        turno = obter_intervalo_turno()
        data_emissao = datetime.datetime.now().strftime("%d/%m/%Y, %H:%M:%S")

        todos_itens = []

        for an in anotacoes:
            if not isinstance(an, dict):
                continue
                
            texto_raw = str(an.get('text', ''))
            
            tags = an.get('tags', [])
            tag_alerta = next((t for t in tags if str(t).startswith('alerta:')), None)
            rule_uid = str(tag_alerta).replace('alerta:', '') if tag_alerta else None

            # DETEÇÃO RIGOROSA DO STATUS CONCLUÍDO
            # É concluído se contiver [CONCLUIDO] no texto OU se o rule_uid já não constar da lista de alertas ativos do Grafana
            eh_concluido = "[CONCLUIDO]" in texto_raw.upper() or "[CONCLUÍDO]" in texto_raw.upper()
            if uids_ativos and rule_uid and rule_uid not in uids_ativos:
                eh_concluido = True

            eh_intermitente = "[INTERMITENTE]" in texto_raw.upper()
            eh_programado = "ITOC-PROGRAMADO" in texto_raw.upper() or "[PROGRAMADO]" in texto_raw.upper()

            if eh_concluido:
                status_txt = "Concluído"
                badge_class = "badge-concluido"
            elif eh_intermitente:
                status_txt = "Intermitente"
                badge_class = "badge-intermitente"
            elif eh_programado:
                status_txt = "Programado"
                badge_class = "badge-programado"
            else:
                status_txt = "Em Andamento"
                badge_class = "badge-andamento"

            regiao_limpa, corredor = extrair_regiao_e_corredor(an)
            tratando, descricao, noc = limpar_e_extrair_descricao(texto_raw)

            data_abertura = formatar_data_hora(an.get('time') or an.get('created'))
            data_atualizacao = formatar_data_hora(an.get('updated'))
            data_fechamento = formatar_data_hora(an.get('timeEnd') or an.get('updated')) if eh_concluido else ""

            todos_itens.append({
                "dataAbertura": data_abertura,
                "dataAtualizacao": data_atualizacao,
                "dataFechamento": data_fechamento,
                "regiao": regiao_limpa,
                "corredor": corredor,
                "tratando": tratando,
                "descricao": descricao,
                "noc": noc,
                "vsc": "",
                "status_txt": status_txt,
                "badge_class": badge_class,
                "eh_concluido": eh_concluido
            })

        # --- SEPARAÇÃO RIGOROSA ---
        # Filtra os relatórios para que Concluídos fiquem APENAS no Geral
        itens_norte = [i for i in todos_itens if i["corredor"] == "Corredor Norte" and not i["eh_concluido"]]
        itens_sul = [i for i in todos_itens if i["corredor"] == "Corredor Sul e Sudeste" and not i["eh_concluido"]]
        itens_geral = [i for i in todos_itens if i["eh_concluido"]]

        categorias = [
            {"chave": "NORTE", "titulo": "RELATÓRIO DE ATENDIMENTOS • CORREDOR NORTE", "itens": itens_norte},
            {"chave": "SUL_SUDESTE", "titulo": "RELATÓRIO DE ATENDIMENTOS • CORREDOR SUL E SUDESTE", "itens": itens_sul},
            {"chave": "GERAL_CONCLUIDOS", "titulo": "RELATÓRIO GERAL • ATENDIMENTOS CONCLUÍDOS DO TURNO", "itens": itens_geral}
        ]

        relatorios_output = []

        for cat in categorias:
            lista = cat["itens"]

            t_concluidos = sum(1 for i in lista if i["status_txt"] == "Concluído")
            t_andamento = sum(1 for i in lista if i["status_txt"] == "Em Andamento")
            t_programados = sum(1 for i in lista if i["status_txt"] == "Programado")
            t_intermitentes = sum(1 for i in lista if i["status_txt"] == "Intermitente")

            template = Template(HTML_TEMPLATE)
            html_final = template.render(
                titulo=cat["titulo"],
                meta_turno=turno["meta_str"],
                data_emissao=data_emissao,
                total_concluidos=t_concluidos,
                total_andamento=t_andamento,
                total_programados=t_programados,
                total_intermitentes=t_intermitentes,
                itens=lista
            )

            pdf_bytes, img_bytes = await render_pdf_and_image(html_final)

            pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")

            nome_base = f"Relatorio_GMG_{cat['chave']}_{datetime.datetime.now().strftime('%d-%m-%Y')}"

            relatorios_output.append({
                "regiao": cat["chave"],
                "filename": f"{nome_base}.pdf",
                "image_filename": f"{nome_base}.png",
                "pdf_base64": pdf_b64,
                "image_base64": img_b64
            })

        return jsonify({"relatorios": relatorios_output}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
