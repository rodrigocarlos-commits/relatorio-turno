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

def sanitizar_texto(texto):
    """Limpa caracteres estranhos, codificações ANSI e símbolos corrompidos."""
    if not texto or pd.isna(texto):
        return ""
    texto = str(texto)
    # Decodifica entidades HTML se houver
    texto = html.unescape(texto)
    # Remove códigos de escape ANSI / caracteres de controle invisíveis
    texto = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', texto)
    # Substitui sequências corrompidas conhecidas vindas da fonte
    texto = texto.replace("C sá", "Cls").replace("[]", "").replace("", "")
    return texto.strip()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Relatório de Atendimentos</title>
    <style>
        @page {
            size: A4 landscape;
            margin: 10mm;
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
            margin-bottom: 12px;
            border-bottom: 2px solid #E2E8F0;
            padding-bottom: 6px;
        }
        .title {
            font-size: 16px;
            font-weight: bold;
            color: #1A202C;
            text-transform: uppercase;
        }
        .subtitle {
            font-size: 10px;
            color: #718096;
            margin-top: 2px;
        }
        .badge-gerado {
            background-color: #FEFCBF;
            color: #744210;
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 9px;
            text-align: right;
        }
        .cards-container {
            display: flex;
            gap: 12px;
            margin-bottom: 12px;
            background-color: #F7FAFC;
            padding: 8px 12px;
            border-radius: 6px;
            border: 1px solid #E2E8F0;
            align-items: center;
        }
        .card {
            font-weight: bold;
            font-size: 11px;
        }
        .status-pill {
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 9px;
            font-weight: bold;
            display: inline-block;
            text-align: center;
        }
        .status-concluido { background-color: #C6F6D5; color: #22543D; }
        .status-andamento { background-color: #FEEBC8; color: #742A2A; }
        .status-intermitente { background-color: #E9D8FD; color: #44337A; }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 5px;
        }
        tr {
            page-break-inside: avoid;
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
        .col-data { width: 11%; }
        .col-regiao { width: 18%; font-weight: 600; }
        .col-tratando { width: 10%; }
        .col-desc { width: 49%; }
        .col-status { width: 12%; text-align: center; }
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
        <div class="card"><span style="font-size: 15px; color: #2B6CB0;">{{ total_atendimentos }}</span> atendimentos neste relatório</div>
        {% if 'GERAL' in regiao_titulo %}
            <div class="card"><span class="status-pill status-concluido">{{ qtd_concluidos }} Concluídos</span></div>
        {% else %}
            <div class="card"><span class="status-pill status-andamento">{{ qtd_andamento }} Em Andamento</span></div>
            <div class="card"><span class="status-pill status-intermitente">{{ qtd_intermitentes }} Intermitentes</span></div>
        {% endif %}
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
                    {% if item.status_limpo == 'concluido' %}
                        <span class="status-pill status-concluido">Concluído</span>
                    {% elif item.status_limpo == 'intermitente' %}
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

        df = pd.DataFrame(dados_brutos)
        
        # Limpeza global de strings
        for col in df.columns:
            df[col] = df[col].apply(sanitizar_texto)

        # Mapeamento estrito de status
        def mapear_status(st):
            st_lower = str(st).lower()
            if "concluid" in st_lower:
                return "concluido"
            elif "intermitent" in st_lower:
                return "intermitente"
            else:
                return "andamento"

        df["status_normalizado"] = df["status"].apply(mapear_status)

        regioes = ["NORTE", "SUL", "LESTE", "GERAL"]
        relatorios_output = []

        agora = datetime.datetime.now()
        data_hoje = agora.strftime("%d/%m/%Y (05:00 às 18:00)")
        hora_geracao = agora.strftime("%d/%m/%Y, %H:%M:%S")

        for reg in regioes:
            if reg == "GERAL":
                # GERAL: Apenas os estritamente Concluídos
                df_reg = df[df["status_normalizado"] == "concluido"].copy()
            else:
                # DEMAIS REGIÕES: Apenas Em Andamento ou Intermitentes (EXCLUI Concluídos)
                # Verifica a região no campo 'regiao' ou na 'descricao'
                mask_reg = df["regiao"].str.upper().str.contains(reg, na=False) | df["descricao"].str.upper().str.contains(reg, na=False)
                mask_status = df["status_normalizado"].isin(["andamento", "intermitente"])
                df_reg = df[mask_reg & mask_status].copy()

            if df_reg.empty:
                continue

            qtd_concluidos = len(df_reg[df_reg["status_normalizado"] == "concluido"])
            qtd_andamento = len(df_reg[df_reg["status_normalizado"] == "andamento"])
            qtd_intermitentes = len(df_reg[df_reg["status_normalizado"] == "intermitente"])

            lista_itens = []
            for _, row in df_reg.iterrows():
                lista_itens.append({
                    "data_abertura": row.get("data_abertura", ""),
                    "atualizacao": row.get("atualizacao", ""),
                    "regiao_site": f"{row.get('regiao', '')} - {row.get('site', '')}".strip(" -"),
                    "tratando": row.get("tratando", "ITOC"),
                    "descricao": row.get("descricao", ""),
                    "status_limpo": row.get("status_normalizado", "andamento")
                })

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

            pdf_bytes, img_bytes = await render_pdf_and_image(html_final)

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
