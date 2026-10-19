import base64
import datetime
import html
import io
import os
import re
import pandas as pd
from flask import Flask, jsonify, request
from jinja2 import Template
import playwright.async_api as playwright_async

app = Flask(__name__)

# --- LISTA DE REGIÕES OFICIAIS PARA ISOLAR O NOME LIMPO ---
REGIOES_CONHECIDAS = [
    'CARAJAS', 'SALOBO', 'S11D', 'SLZ', 'SÃO LUIZ', 'SAO LUIZ', 
    'SOSSEGO', 'MOP', 'ONÇA PUMA', 'ONCA PUMA', 'MG', 'VIX', 'ES', 'RJ', 'VALE RJ'
]

# --- REGRA DE NEGÓCIO: ISOLAR APENAS O NOME DA REGIÃO ---
def extrair_regiao_limpa(regiao_raw):
    if not regiao_raw or pd.isna(regiao_raw):
        return "Geral"
    
    texto = str(regiao_raw)
    # Procura por qualquer uma das regiões conhecidas dentro do texto/tags
    for reg in REGIOES_CONHECIDAS:
        if re.search(r'\b' + re.escape(reg) + r'\b', texto, re.IGNORECASE):
            return reg.upper()
    
    # Se não encontrar nenhuma conhecida, limpa tags do Grafana (aldak-tratando, alerta:xxx)
    partes = texto.split(',')
    partes_limpas = [p.strip() for p in partes if not p.strip().startswith('aldak-') and not p.strip().startswith('alerta:')]
    if partes_limpas:
        return partes_limpas[0].upper()
    
    return "GERAL"

# --- REGRA DE NEGÓCIO: DEFINIÇÃO DE CORREDOR ---
def obter_corredor(regiao_limpa):
    r = str(regiao_limpa or '').upper().strip()
    if any(k in r for k in ['MG', 'VIX', 'ES', 'RJ', 'VALE RJ', 'SUDESTE', 'SUL']):
        return 'Corredor Sul e Sudeste'
    return 'Corredor Norte'

# --- REGRA DE NEGÓCIO: INTERVALO DE TURNO ---
def obter_intervalo_turno():
    agora = datetime.datetime.now()
    hora_atual = agora.hour

    if 5 <= hora_atual < 18:
        inicio_turno = agora.replace(hour=5, minute=0, second=0, microsecond=0)
        fim_turno = agora.replace(hour=18, minute=0, second=0, microsecond=0)
    else:
        if hora_atual >= 18:
            inicio_turno = agora.replace(hour=17, minute=0, second=0, microsecond=0)
            fim_turno = (agora + datetime.timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
        else:
            inicio_turno = (agora - datetime.timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)
            fim_turno = agora.replace(hour=6, minute=0, second=0, microsecond=0)

    return {
        "inicio_ms": int(inicio_turno.timestamp() * 1000),
        "fim_ms": int(fim_turno.timestamp() * 1000),
        "inicio_str": inicio_turno.strftime("%H:%M"),
        "fim_str": fim_turno.strftime("%H:%M"),
        "data_str": inicio_turno.strftime("%d/%m/%Y")
    }

# --- REGRA DE NEGÓCIO: EXTRAÇÃO DE TRATANDO, DESCRIÇÃO E NOC ---
def extrair_dados_texto(texto):
    texto = str(texto or '')
    tratando = ""
    descricao = texto
    noc = ""

    match_tratando = re.search(r'(?:\[INTERMITENTE\]\s*)?^(.*?)\s+está tratando', texto, re.IGNORECASE)
    if match_tratando:
        tratando = match_tratando.group(1).strip()

    match_desc = re.search(r'"([^"]+)"', texto)
    if match_desc:
        descricao = match_desc.group(1).strip()

    match_noc = re.search(r'\(chamado nº\s*([^)]+)\)', texto, re.IGNORECASE)
    if match_noc:
        noc = match_noc.group(1).strip()

    return tratando, descricao, noc

def sanitizar_texto(texto):
    if not texto or pd.isna(texto):
        return ""
    texto = str(texto)
    texto = html.unescape(texto)
    texto = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', texto)
    texto = re.sub(r'\[\s*\]', '', texto)
    texto = texto.replace("C sá", "Cls").replace("C-", "Ch-")
    return re.sub(r'\s+', ' ', texto).strip()

# --- TEMPLATE HTML ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>{{ titulo_relatorio }}</title>
    <style>
        @page { size: A4 landscape; margin: 8mm; }
        * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        body { background: #fff; color: #333; margin: 0; padding: 10px; font-size: 11px; }

        .report-card { width: 100%; max-width: 1400px; margin: 0 auto; }
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

        table { width: 100%; border-collapse: collapse; margin-top: 5px; page-break-inside: auto; }
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
                <h1 class="main-title">{{ titulo_relatorio }}</h1>
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
                        <span class="badge {{ item.statusBadgeClass }}">{{ item.statusTxt }}</span>
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
        
        pdf_bytes = await page.pdf(
            format="A4",
            landscape=True,
            print_background=True,
            margin={"top": "8mm", "right": "8mm", "bottom": "8mm", "left": "8mm"}
        )
        image_bytes = await page.screenshot(full_page=True, type="png")
        await browser.close()
        return pdf_bytes, image_bytes

@app.route("/gerar-relatorios", methods=["POST"])
async def processar_dados():
    try:
        payload = request.get_json(force=True)
        dados_brutos = payload.get("dados", [])
        
        if not dados_brutos:
            return jsonify({"error": "Nenhum dado recebido"}), 400

        turno = obter_intervalo_turno()
        meta_turno = f"{turno['data_str']} ({turno['inicio_str']} às {turno['fim_str']})"
        data_emissao = datetime.datetime.now().strftime("%d/%m/%Y, %H:%M:%S")

        todos_itens = []

        for item in dados_brutos:
            texto_bruto = sanitizar_texto(item.get("text", "") or item.get("descricao", ""))
            
            # Limpa o campo de região para exibir apenas a palavra chave (ex: SOSSEGO, SALOBO)
            regiao_bruta = item.get("regiao", "GERAL")
            regiao_limpa = extrair_regiao_limpa(regiao_bruta)

            # Define se é ativo ou concluído
            esta_ativo = item.get("estaAtivo", True)
            if "status" in item:
                st_lower = str(item["status"]).lower()
                if "concluid" in st_lower:
                    esta_ativo = False
            if "[CONCLUIDO]" in texto_bruto or "[CONCLUÍDO]" in texto_bruto:
                esta_ativo = False

            eh_programado = "ITOC-Programado" in texto_bruto or "[PROGRAMADO]" in texto_bruto
            eh_intermitente = "[INTERMITENTE]" in texto_bruto

            if not esta_ativo:
                status_txt = "Concluído"
                status_badge_class = "badge-concluido"
            elif eh_intermitente:
                status_txt = "Intermitente"
                status_badge_class = "badge-intermitente"
            elif eh_programado:
                status_txt = "Programado"
                status_badge_class = "badge-programado"
            else:
                status_txt = "Em Andamento"
                status_badge_class = "badge-andamento"

            tratando, descricao, noc = extrair_dados_texto(texto_bruto)
            corredor = obter_corredor(regiao_limpa)

            todos_itens.append({
                "dataAbertura": item.get("dataAbertura", item.get("data_abertura", "")),
                "dataAtualizacao": item.get("dataAtualizacao", item.get("atualizacao", "")),
                "dataFechamento": item.get("dataFechamento", item.get("fechamento", "") if not esta_ativo else ""),
                "regiao": regiao_limpa,
                "corredor": corredor,
                "tratando": tratando or item.get("tratando", "ITOC"),
                "descricao": descricao,
                "noc": noc,
                "vsc": item.get("vsc", ""),
                "statusTxt": status_txt,
                "statusBadgeClass": status_badge_class
            })

        # --- FILTRAGEM RIGOROSA DA REGRA V4.0 ---
        # Corredores Norte e Sul exibem EXCLUSIVAMENTE itens em aberto (removidos todos os Concluídos)
        itens_norte = [i for i in todos_itens if i["corredor"] == "Corredor Norte" and i["statusTxt"] != "Concluído"]
        itens_sul_sudeste = [i for i in todos_itens if i["corredor"] == "Corredor Sul e Sudeste" and i["statusTxt"] != "Concluído"]
        
        # O Relatório Geral exibe SOMENTE os Concluídos do turno
        itens_concluidos = [i for i in todos_itens if i["statusTxt"] == "Concluído"]

        categorias = [
            {"chave": "NORTE", "titulo": "RELATÓRIO DE ATENDIMENTOS • CORREDOR NORTE", "itens": itens_norte},
            {"chave": "SUL_SUDESTE", "titulo": "RELATÓRIO DE ATENDIMENTOS • CORREDOR SUL E SUDESTE", "itens": itens_sul_sudeste},
            {"chave": "GERAL_CONCLUIDOS", "titulo": "RELATÓRIO GERAL • ATENDIMENTOS CONCLUÍDOS DO TURNO", "itens": itens_concluidos}
        ]

        relatorios_output = []

        for cat in categorias:
            lista_itens = cat["itens"]

            t_concluidos = sum(1 for i in lista_itens if i["statusTxt"] == "Concluído")
            t_andamento = sum(1 for i in lista_itens if i["statusTxt"] == "Em Andamento")
            t_programados = sum(1 for i in lista_itens if i["statusTxt"] == "Programado")
            t_intermitentes = sum(1 for i in lista_itens if i["statusTxt"] == "Intermitente")

            template = Template(HTML_TEMPLATE)
            html_final = template.render(
                titulo_relatorio=cat["titulo"],
                meta_turno=meta_turno,
                data_emissao=data_emissao,
                total_concluidos=t_concluidos,
                total_andamento=t_andamento,
                total_programados=t_programados,
                total_intermitentes=t_intermitentes,
                itens=lista_itens
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
