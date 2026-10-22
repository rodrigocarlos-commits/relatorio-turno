import base64
import datetime
import html
import os
import re
import io
import pandas as pd
from flask import Flask, jsonify, request
from jinja2 import Template
from xhtml2pdf import pisa

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
    if not texto_bruto:
        return "ITOC", "", ""
    
    texto = html.unescape(str(texto_bruto))
    texto = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', texto)
    texto = re.sub(r'\[\s*\]', '', texto)
    texto = texto.replace("C sá", "Cls").replace("C-", "Ch-")
    
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
    <style>
        @page { size: A4 landscape; margin: 8mm; }
        body { font-family: Helvetica, Arial, sans-serif; color: #333; margin: 0; padding: 5px; font-size: 10px; }
        .header-top { width: 100%; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; margin-bottom: 10px; }
        .sub-title { color: #8c9ba5; font-size: 10px; font-weight: bold; margin: 0; }
        .main-title { color: #1e293b; font-size: 16px; font-weight: bold; margin: 2px 0; text-transform: uppercase; }
        .meta-info { color: #64748b; font-size: 10px; font-weight: bold; margin-top: 2px; }
        .kpi-container { background: #f8fafc; padding: 8px 12px; margin-bottom: 12px; border: 1px solid #e2e8f0; }
        .big-number { font-size: 20px; font-weight: bold; color: #0f172a; }
        table { width: 100%; border-collapse: collapse; margin-top: 5px; }
        th { text-align: left; padding: 6px 4px; border-bottom: 2px solid #e2e8f0; color: #64748b; font-size: 9px; font-weight: bold; text-transform: uppercase; background: #f8fafc; }
        td { padding: 5px 4px; border-bottom: 1px solid #f1f5f9; font-size: 9px; color: #334155; vertical-align: top; }
        .badge { padding: 2px 6px; font-size: 9px; font-weight: bold; text-align: center; }
        .badge-concluido { background-color: #dcfce7; color: #15803d; }
        .badge-andamento { background-color: #fef3c7; color: #b45309; }
        .badge-programado { background-color: #dbeafe; color: #1d4ed8; }
        .badge-intermitente { background-color: #f3e8ff; color: #7e22ce; }
    </style>
</head>
<body>
    <div class="header-top">
        <p class="sub-title">NOC Aldak • Central de Alertas ITOC</p>
        <h1 class="main-title">{{ titulo }}</h1>
        <p class="meta-info">Turno Vigente: {{ meta_turno }} | Gerado em: {{ data_emissao }}</p>
    </div>

    <div class="kpi-container">
        <span class="big-number">{{ itens|length }}</span> atendimentos | 
        Concluídos: <b>{{ total_concluidos }}</b> | 
        Em Andamento: <b>{{ total_andamento }}</b> | 
        Programados: <b>{{ total_programados }}</b> | 
        Intermitentes: <b>{{ total_intermitentes }}</b>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width: 80px;">Abertura</th>
                <th style="width: 80px;">Atualização</th>
                <th style="width: 80px;">Fechamento</th>
                <th style="width: 80px;">Região</th>
                <th style="width: 70px;">Tratando</th>
                <th>Descrição</th>
                <th style="width: 70px;">NOC</th>
                <th style="width: 80px; text-align: center;">Status</th>
            </tr>
        </thead>
        <tbody>
            {% if itens|length == 0 %}
            <tr>
                <td colspan="8" style="text-align:center; padding: 15px; color: #94a3b8;">Nenhum atendimento nesta categoria para o turno atual.</td>
            </tr>
            {% else %}
            {% for item in itens %}
            <tr>
                <td>{{ item.dataAbertura }}</td>
                <td>{{ item.dataAtualizacao }}</td>
                <td>{{ item.dataFechamento }}</td>
                <td><b>{{ item.regiao }}</b></td>
                <td>{{ item.tratando }}</td>
                <td>{{ item.descricao }}</td>
                <td>{{ item.noc }}</td>
                <td style="text-align: center;">
                    <span class="badge {{ item.badge_class }}">{{ item.status_txt }}</span>
                </td>
            </tr>
            {% endfor %}
            {% endif %}
        </tbody>
    </table>
</body>
</html>
"""

def gerar_pdf_bytes(html_content):
    """Converte HTML em PDF usando xhtml2pdf sem precisar de navegador."""
    pdf_stream = io.BytesIO()
    pisa_status = pisa.CreatePDF(io.StringIO(html_content), dest=pdf_stream)
    if pisa_status.err:
        raise Exception("Erro ao renderizar PDF")
    return pdf_stream.getvalue()

@app.route("/gerar-relatorios", methods=["POST"])
def processar_dados():
    try:
        payload = request.get_json(force=True)
        anotacoes = payload.get("anotacoes", payload.get("dados", []))
        alertas_ativos = payload.get("alertas_ativos", [])
        
        if not isinstance(anotacoes, list):
            anotacoes = []
        if not isinstance(alertas_ativos, list):
            alertas_ativos = []

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

            todos_itens.append({
                "dataAbertura": formatar_data_hora(an.get('time') or an.get('created')),
                "dataAtualizacao": formatar_data_hora(an.get('updated')),
                "dataFechamento": formatar_data_hora(an.get('timeEnd') or an.get('updated')) if eh_concluido else "",
                "regiao": regiao_limpa,
                "corredor": corredor,
                "tratando": tratando,
                "descricao": descricao,
                "noc": noc,
                "status_txt": status_txt,
                "badge_class": badge_class,
                "eh_concluido": eh_concluido
            })

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

            pdf_bytes = gerar_pdf_bytes(html_final)
            pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

            nome_base = f"Relatorio_GMG_{cat['chave']}_{datetime.datetime.now().strftime('%d-%m-%Y')}"

            relatorios_output.append({
                "regiao": cat["chave"],
                "filename": f"{nome_base}.pdf",
                "pdf_base64": pdf_b64
            })

        return jsonify({"relatorios": relatorios_output}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
