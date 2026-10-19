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

# Configuração de suporte para acentos e símbolos especiais
def limpar_texto(texto):
    if not texto or pd.isna(texto):
        return ""
    texto = str(texto)
    # Garante decodificação limpa UTF-8 e escape de entidades HTML
    texto = html.unescape(texto)
    return texto

# Template HTML com codificação UTF-8 explícita e regras CSS para layout
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Relatório de Atendimentos</title>
    <style>
        @page {
            size: A4 landscape;
            margin: 12mm 10mm 12mm 10mm;
        }
        body {
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            color: #2D3748;
            margin: 0;
            padding: 0;
            font-size: 10px;
            background-color: #ffffff;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            border-bottom: 2px solid #E2E8F0;
            padding-bottom: 8px;
        }
        .title {
            font-size: 18px;
            font-weight: bold;
            color: #1A202C;
            text-transform: uppercase;
        }
        .subtitle {
            font-size: 11px;
            color: #718096;
            margin-top: 3px;
        }
        .badge-gerado {
            background-color: #FEFCBF;
            color: #744210;
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 10px;
        }
        .cards-container {
            display: flex;
            gap: 15px;
            margin-bottom: 15px;
            background-color: #F7FAFC;
            padding: 10px;
            border-radius: 6px;
            border: 1px solid #E2E8F0;
        }
        .card {
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: bold;
        }
        .status-pill {
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 9px;
            font-weight: bold;
            text-transform: capitalize;
            display: inline-block;
            text-align: center;
        }
        .status-concluido { background-color: #C6F6D5; color: #22543D; }
        .status-andamento { background-color: #FEEBC8; color: #742A2A; }
        .status-intermitente { background-color: #E9D8FD; color: #44337A; }
        .status-programado { background-color: #BEE3F8; color: #2B6CB0; }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 5px;
            page-break-inside: auto;
        }
        tr {
            page-break-inside: avoid;
            page-break-after: auto;
        }
        th {
            background-color: #EDF2F7;
            color: #4A5568;
            font-weight: bold;
            text-align: left;
            padding: 6px 5px;
            border-bottom: 2px solid #CBD5E0;
            font-size: 9px;
            text-transform: uppercase;
        }
        td {
            padding: 5px;
            border-bottom: 1px solid #E2E8F0;
            font-size: 9px;
            vertical-align: top;
            word-wrap: break-word;
        }
        .col-data { width: 10%; }
        .col-regiao { width: 15%; font-weight: 600; }
        .col-tratando { width: 8%; }
        .col-desc { width: 45%; }
        .col-status { width: 10%; text-align: center; }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <div class="title">RELATÓRIO DE ATENDIMENTOS • {{ regiao_titulo }}</div>
            <div class="subtitle">Turno Vigente: {{ data_hoje }}</div>
        </div>
        <div class="badge-gerado">
            Relatório Gerado em<br>{{ hora_geracao }}
        </div>
    </div>

    <div class="cards-container">
        <div class="card"><span style="font-size: 16px;">{{ total_atendimentos }}</span> atendimentos neste relatório</div>
        <div class="card"><span class="status-pill status-concluido">{{ qtd_concluidos }} Concluídos</span></div>
        <div class="card"><span class="status-pill status-andamento">{{ qtd_andamento }} Em Andamento</span></div>
        <div class="card"><span class="status-pill status-intermitente">{{ qtd_intermitentes }} Intermitentes</span></div>
    </div>

    <table>
        <thead>
            <tr>
                <th class="col-data">DATA / ABERTURA</th>
                <th class="col-data">ATUALIZAÇÃO</th>
                <th class="col-regiao">REGIÃO / SITE</th>
                <th class="col-tratando">TRATANDO</th>
                <th class="col-desc">DESCRIÇÃO DO ATENDIMENTO</th>
                <th class="col-status">STATUS</th>
            </tr>
        </thead>
        <tbody>
            {% for item in itens %}
            <tr>
                <td>{{ item.data_abertura }}</td>
                <td>{{ item.atualizacao }}</td>
                <td class="col-regiao">{{ item.regiao_site }}</td>
                <td>{{ item.tratando }}</td>
                <td class="col-desc">{{ item.descricao }}</td>
                <td class="col-status">
                    {% if 'concluid' in item.status.lower() %}
                        <span class="status-pill status-concluido">Concluído</span>
                    {% elif 'intermitent' in item.status.lower() %}
                        <span class="status-pill status-intermitente">Intermitente</span>
                    {% else %}
                        <span class="status-pill status-andamento">Em Andamento</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</body>
</html>
"""

async def render_pdf_and_image(html_content):
    """Utiliza o Playwright para gerar o PDF e a Imagem PNG a partir do HTML em UTF-8."""
    async with playwright_async.async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        
        # Define o conteúdo da página garantindo suporte a caracteres UTF-8
        await page.set_content(html_content, wait_until="networkidle")
        
        # Gerar PDF
        pdf_bytes = await page.pdf(
            format="A4",
            landscape=True,
            print_background=True,
            margin={"top": "10mm", "right": "10mm", "bottom": "10mm", "left": "10mm"}
        )
        
        # Gerar Imagem PNG
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

        df = pd.DataFrame(dados_brutos)
        
        # Normalização dos campos
        for col in df.columns:
            df[col] = df[col].apply(limpar_texto)

        # Regiões ativas para relatório
        regioes = ["NORTE", "SUL", "LESTE", "GERAL"]
        relatorios_output = []

        agora = datetime.datetime.now()
        data_hoje = agora.strftime("%d/%m/%Y (05:00 às 18:00)")
        hora_geracao = agora.strftime("%d/%m/%Y, %H:%M:%S")

        for reg in regioes:
            # 1. Filtro por Região e Regras de Status
            if reg == "GERAL":
                # Relatório GERAL: Somente Concluídos
                df_reg = df[df["status"].str.lower().str.contains("concluid", na=False)].copy()
            else:
                # Demais relatórios: Em Atendimento / Em Andamento e Intermitentes
                mask_regiao = df["regiao"].str.upper().str.contains(reg, na=False)
                mask_status = df["status"].str.lower().str.contains("atendimento|andamento|intermitent", na=False)
                df_reg = df[mask_regiao & mask_status].copy()

            if df_reg.empty:
                continue

            # Contadores para os Cards superiores
            qtd_concluidos = len(df_reg[df_reg["status"].str.lower().str.contains("concluid", na=False)])
            qtd_andamento = len(df_reg[df_reg["status"].str.lower().str.contains("atendimento|andamento", na=False)])
            qtd_intermitentes = len(df_reg[df_reg["status"].str.lower().str.contains("intermitent", na=False)])

            # Montagem da lista de itens
            lista_itens = []
            for _, row in df_reg.iterrows():
                lista_itens.append({
                    "data_abertura": row.get("data_abertura", ""),
                    "atualizacao": row.get("atualizacao", ""),
                    "regiao_site": f"{row.get('regiao', '')} - {row.get('site', '')}",
                    "tratando": row.get("tratando", "ITOC"),
                    "descricao": row.get("descricao", ""),
                    "status": row.get("status", "")
                })

            # Renderização do Jinja2
            template = Template(HTML_TEMPLATE)
            html_final = template.render(
                regiao_titulo=f"CORREDOR {reg}" if reg != "GERAL" else "GERAL",
                data_hoje=data_hoje,
                hora_geracao=hora_geracao,
                total_atendimentos=len(lista_itens),
                qtd_concluidos=qtd_concluidos,
                qtd_andamento=qtd_andamento,
                qtd_intermitentes=qtd_intermitentes,
                itens=lista_itens
            )

            # Geração do PDF e Imagem
            pdf_bytes, img_bytes = await render_pdf_and_image(html_final)

            # Codificação Base64
            pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")

            nome_base = f"Relatorio_GMG_{reg}_{agora.strftime('%d-%m-%Y')}"

            relatorios_output.append({
                "regiao": reg,
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
