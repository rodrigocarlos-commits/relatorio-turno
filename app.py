import os
import datetime
import base64
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright

app = Flask(__name__)

API_KEY = os.environ.get("API_KEY", "SUA_CHAVE_AQUI")

def extrair_regiao(texto, tags):
    tags_str = " ".join([str(t).upper() for t in tags])
    text_upper = str(texto).upper()
    if any(k in tags_str or k in text_upper for k in ['CARAJAS', 'SALOBO', 'SOSSEGO', 'EFC', 'NORTE']):
        return 'NORTE'
    return 'SUL_SUDESTE'

def gerar_html_relatorio(itens, titulo_relatorio, periodo_turno, data_emissao):
    total_concluidos = sum(1 for i in itens if i.get('statusTxt') == 'Concluído')
    total_andamento = sum(1 for i in itens if i.get('statusTxt') == 'Em Andamento')
    total_programados = sum(1 for i in itens if i.get('statusTxt') == 'Programado')
    total_intermitentes = sum(1 for i in itens if i.get('statusTxt') == 'Intermitente')

    linhas_html = ""
    if not itens:
        linhas_html = '<tr><td colspan="9" style="text-align:center; padding: 20px; color: #94a3b8;">Nenhum atendimento ativo nesta categoria para o ciclo do turno atual.</td></tr>'
    else:
        for item in itens:
            linhas_html += f"""
            <tr>
              <td style="white-space: nowrap;">{item.get('dataAbertura', '')}</td>
              <td style="white-space: nowrap;">{item.get('dataAtualizacao', '')}</td>
              <td style="white-space: nowrap;">{item.get('dataFechamento', '')}</td>
              <td><b>{item.get('regiao', '')}</b></td>
              <td>{item.get('tratando', '')}</td>
              <td>{item.get('descricao', '')}</td>
              <td>{item.get('noc', '')}</td>
              <td>{item.get('vsc', '')}</td>
              <td style="text-align: center;">
                <span class="badge {item.get('statusBadgeClass', 'badge-intermitente')}">{item.get('statusTxt', '')}</span>
              </td>
            </tr>
            """

    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
      <meta charset="UTF-8">
      <style>
        * {{ box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
        body {{ background: #ffffff; color: #333333; margin: 0; padding: 20px; }}
        .report-card {{ background: #ffffff; border-radius: 12px; padding: 20px; max-width: 100%; margin: 0 auto; }}
        .header-top {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }}
        .sub-title {{ color: #8c9ba5; font-size: 13px; font-weight: bold; margin: 0; }}
        .main-title {{ color: #1e293b; font-size: 20px; font-weight: 800; margin: 4px 0; text-transform: uppercase; }}
        .meta-info {{ color: #64748b; font-size: 12px; font-weight: 600; }}
        .tag-gerado {{ background: #fff8f0; border: 1px solid #ffedd5; color: #d97706; padding: 6px 14px; border-radius: 8px; font-size: 11px; font-weight: bold; text-align: right; }}
        .kpi-container {{ display: flex; align-items: center; gap: 20px; background: #f8fafc; padding: 14px 18px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #e2e8f0; }}
        .big-number {{ font-size: 32px; font-weight: 800; color: #0f172a; line-height: 1; }}
        .big-label {{ font-size: 11px; color: #64748b; font-weight: 600; display: block; margin-top: 4px; }}
        .kpi-bars {{ display: flex; gap: 15px; flex: 1; align-items: center; border-left: 2px solid #e2e8f0; padding-left: 20px; flex-wrap: wrap; }}
        .kpi-item {{ font-size: 12px; font-weight: bold; color: #475569; display: flex; align-items: center; gap: 6px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th {{ text-align: left; padding: 8px 6px; border-bottom: 2px solid #e2e8f0; color: #64748b; font-size: 10px; font-weight: 700; text-transform: uppercase; }}
        td {{ padding: 8px 6px; border-bottom: 1px solid #f1f5f9; font-size: 11px; color: #334155; }}
        .badge {{ padding: 3px 8px; border-radius: 10px; font-size: 10px; font-weight: 700; display: inline-block; white-space: nowrap; text-align: center; }}
        .badge-concluido {{ background: #dcfce7; color: #15803d; }}
        .badge-andamento {{ background: #fef3c7; color: #b45309; }}
        .badge-programado {{ background: #dbeafe; color: #1d4ed8; }}
        .badge-intermitente {{ background: #f3e8ff; color: #7e22ce; border: 1px solid #e9d5ff; }}
      </style>
    </head>
    <body>
      <div class="report-card">
        <div class="header-top">
          <div>
            <p class="sub-title">NOC Aldak • Central de Alertas ITOC</p>
            <h1 class="main-title">{titulo_relatorio}</h1>
            <p class="meta-info">Turno Vigente: {periodo_turno}</p>
          </div>
          <div class="tag-gerado">
            <div>Relatório Gerado em</div>
            <div>{data_emissao}</div>
          </div>
        </div>

        <div class="kpi-container">
          <div>
            <div class="big-number">{len(itens)}</div>
            <span class="big-label">atendimentos neste relatório</span>
          </div>
          <div class="kpi-bars">
            <div class="kpi-item">🟢 <b>{total_concluidos}</b> Concluídos</div>
            <div class="kpi-item">🟡 <b>{total_andamento}</b> Em Andamento</div>
            <div class="kpi-item">🔵 <b>{total_programados}</b> Programados</div>
            <div class="kpi-item">🟣 <b>{total_intermitentes}</b> Intermitentes</div>
          </div>
        </div>

        <table>
          <thead>
            <tr>
              <th style="width: 110px;">Data / Abertura</th>
              <th style="width: 110px;">Atualização</th>
              <th style="width: 110px;">Fechamento</th>
              <th style="width: 100px;">Região / Site</th>
              <th style="width: 90px;">Tratando</th>
              <th>Descrição do Atendimento</th>
              <th style="width: 90px;">NOC</th>
              <th style="width: 50px;">VSC</th>
              <th style="width: 110px; text-align: center;">Status</th>
            </tr>
          </thead>
          <tbody>
            {linhas_html}
          </tbody>
        </table>
      </div>
    </body>
    </html>
    """

@app.route('/gerar', methods=['POST'])
def gerar_relatorio():
    try:
        dados = request.get_json() or {}
        anotacoes = dados.get('anotacoes', [])
        
        itens = []
        for a in anotacoes:
            texto = a.get('text', '')
            tags = a.get('tags', [])
            
            is_intermitente = '[INTERMITENTE]' in texto.upper()
            is_done = '[CONCLUIDO]' in texto.upper() or '[CONCLUÍDO]' in texto.upper()
            
            status_txt = 'Intermitente' if is_intermitente else ('Concluído' if is_done else 'Em Andamento')
            badge_class = 'badge-intermitente' if is_intermitente else ('badge-concluido' if is_done else 'badge-andamento')

            itens.append({
                'dataAbertura': datetime.datetime.fromtimestamp(a.get('time', 0)/1000).strftime("%d/%m/%Y %H:%M") if a.get('time') else '',
                'dataAtualizacao': datetime.datetime.fromtimestamp(a.get('updated', 0)/1000).strftime("%d/%m/%Y %H:%M") if a.get('updated') else '',
                'dataFechamento': '',
                'regiao': ", ".join(tags) if tags else 'Geral',
                'tratando': '[INTERMITENTE] ITOC' if is_intermitente else 'ITOC',
                'descricao': texto,
                'noc': '',
                'vsc': '',
                'statusTxt': status_txt,
                'statusBadgeClass': badge_class
            })

        agora = datetime.datetime.now()
        data_emissao = agora.strftime("%d/%m/%Y, %H:%M:%S")
        periodo_turno = f"{agora.strftime('%d/%m/%Y')} (05:00 às 18:00)"
        timestamp_str = agora.strftime('%Y%m%d_%H%M%S')
        
        html_content = gerar_html_relatorio(itens, "RELATÓRIO DE ATENDIMENTOS • CORREDOR NORTE", periodo_turno, data_emissao)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1200, "height": 800})
            page.set_content(html_content)
            
            # Gera os dois ficheiros
            pdf_bytes = page.pdf(format="A4", landscape=True, print_background=True)
            image_bytes = page.screenshot(full_page=True)
            browser.close()

        return jsonify({
            "filename": f"Relatorio_Corredor_Norte_{timestamp_str}.pdf",
            "image_filename": f"Relatorio_Corredor_Norte_{timestamp_str}.png",
            "pdf_base64": base64.b64encode(pdf_bytes).decode('utf-8'),
            "image_base64": base64.b64encode(image_bytes).decode('utf-8')
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
