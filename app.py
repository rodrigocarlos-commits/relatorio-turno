import os
import re
from flask import Flask, request, jsonify

app = Flask(__name__)

API_KEY = os.environ.get("API_KEY", "SUA_CHAVE_AQUI")

def extrair_regiao(text, tags):
    tags_str = " ".join([str(t).upper() for t in tags])
    text_upper = str(text).upper()
    if any(k in tags_str or k in text_upper for k in ['CARAJAS', 'SALOBO', 'SOSSEGO', 'EFC', 'NORTE']):
        return 'NORTE'
    return 'SUL_SUDESTE'

def formatar_relatorio(itens, titulo):
    if not itens:
        return f"### 📋 {titulo}\n---\n*Nenhum atendimento ativo nesta categoria para o ciclo do turno atual.*"
    
    linhas = [f"### 📋 {titulo}", "---"]
    for idx, item in enumerate(itens, 1):
        status = "[CONCLUÍDO]" if item.get('is_concluido') else "[EM ABERTO]"
        texto = item.get('texto', 'Sem descrição')
        linhas.append(f"**{idx}.** {status} {texto}")
    
    return "\n\n".join(linhas)

@app.route('/gerar', methods=['POST'])
def gerar_relatorio():
    # Validação de token flexível (evita o erro 401 do Power Automate)
    key_recebida = request.headers.get('x-api-key') or request.headers.get('Authorization')
    if key_recebida and API_KEY != "SUA_CHAVE_AQUI":
        clean_key = key_recebida.replace('Bearer ', '').strip()
        if clean_key != API_KEY:
            return jsonify({"error": "Acesso não autorizado"}), 401

    try:
        dados = request.get_json() or {}
        anotacoes = dados.get('anotacoes') or dados.get('itens') or []

        itens_norte = []
        itens_sul = []
        itens_concluidos = []

        if isinstance(anotacoes, list):
            for item in anotacoes:
                texto = item.get('text') or item.get('descricao') or ''
                tags = item.get('tags') or []
                
                is_concluido = '[CONCLUIDO]' in str(texto).upper() or '[CONCLUÍDO]' in str(texto).upper()
                regiao = extrair_regiao(texto, tags)

                obj_item = {'texto': texto, 'is_concluido': is_concluido}

                if is_concluido:
                    itens_concluidos.append(obj_item)
                elif regiao == 'NORTE':
                    itens_norte.append(obj_item)
                else:
                    itens_sul.append(obj_item)

        rel_norte = formatar_relatorio(itens_norte, "RELATÓRIO CORREDOR NORTE")
        rel_sul = formatar_relatorio(itens_sul, "RELATÓRIO CORREDOR SUL E SUDESTE")
        rel_concluidos = formatar_relatorio(itens_concluidos, "RELATÓRIO DE ATENDIMENTOS CONCLUÍDOS")

        return jsonify({
            "relatorio_norte": rel_norte,
            "relatorio_sul": rel_sul,
            "relatorio_concluidos": rel_concluidos
        }), 200

    except Exception as e:
        return jsonify({
            "relatorio_norte": f"Erro no processamento: {str(e)}",
            "relatorio_sul": f"Erro no processamento: {str(e)}",
            "relatorio_concluidos": f"Erro no processamento: {str(e)}"
        }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
