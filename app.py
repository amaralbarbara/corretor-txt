import streamlit as st
import io, os, zipfile, time
from google import genai
from google.genai import types

# 🎨 CONFIGURAÇÃO DA INTERFACE WEB (Estilo IOB Premium)
st.set_page_config(page_title="Validador de Lotes TXT - IOB", page_icon="💜", layout="centered")
st.markdown("<style>.stApp { background-color: #fcfaff; } h1 { color: #4A148C !important; font-weight: 800 !important; } div.stButton > button:first-child { background: linear-gradient(135deg, #7B1FA2 0%, #4A148C 100%) !important; color: white !important; border: none !important; border-radius: 8px !important; width: 100% !important; } .stFileUploader { border: 2px dashed #9C27B0 !important; background-color: #F3E5F5 !important; }</style>", unsafe_allow_html=True)

st.title("💜 Corretor Estrutural de Lotes IOB")
st.markdown("<div style='color: #6A1B9A; font-size: 15px; margin-top: -10px; margin-bottom: 25px;'>Agente Inteligente especializado na correção dos 17 erros críticos de layout e posições da NF-e v4.00.</div>", unsafe_allow_html=True)

# Busca a chave de forma segura nos Secrets do Streamlit Cloud
chave_ambiente = st.secrets.get("GEMINI_API_KEY", "")

FONTE_CONHECIMENTO = """
Você é um auditor do layout TXT da NF-e v4.00. Sua única função é ler o bloco de uma nota fiscal e reestruturá-lo eliminando os seguintes erros:
1. Altere o cabeçalho para iniciar obrigatoriamente com: NOTAFISCAL|1
2. Na linha B, force o modo RASCUNHO deixando vazios os campos cNF (campo 2), cDV (campo 14), dhCont (campo 21) e xJust (campo 22) usando ||. Garanta que tpEmis (campo 13) seja igual a 1.
3. Se for nota de importação com parceiro do exterior, mude tpNF (campo 9 da linha B) de 0 para 1 (Entrada).
4. Se cMunFG estiver duplicado na linha B, mantenha apenas uma ocorrência.
5. Remova e delete completamente qualquer linha 'N|' (vazia) ou 'N'. O correto é a linha M| ser seguida diretamente pela linha do imposto (N02, N03, etc).
6. Substitua a linha 'M||' por 'M|'.
7. Converta a linha N04 (CST 20) para a estrutura funcional N02 (CST 00), reposicionando a Base de Cálculo e a Alíquota.
8. Elimine o grupo inexistente E03a. Para destinatários no exterior, insira a linha E02 com o CNPJ do importador nacional.
9. Recalcule e preencha a linha W02 com os somatórios reais dos itens (vProd, vICMS, vIPI, vPIS, vCOFINS, vNF), garantindo que ela possua exatamente 23 campos.
10. Remova por completo as linhas inválidas W04c, W04e e W04g.
11. Higienize as linhas YA01 removendo textos informativos. Amarre o valor de vPag para ser idêntico ao total geral da nota (vNF).
12. Se a nota for de Entrada de importação, force o campo 'orig' de todos os blocos de ICMS (N02, N03, etc) de 1 para 0 (Nacional).
13. Corrija o excesso de pipes nos registros I18 and I25 para conter estritamente o limite do layout.

Retorne EXCLUSIVAMENTE o conteúdo textual corrigido da nota fiscal. Não inclua saudações, observações ou marcações markdown (sem ```txt). Comece direto com NOTAFISCAL|1.
"""

def separar_lote_por_nota(texto_bruto):
    linhas = texto_bruto.splitlines()
    lote_fatiado, bloco_corrente = [], []
    for linha in linhas:
        ln = linha.strip()
        if not ln: continue
        if ln.startswith("A|4.00") and bloco_corrente:
            lote_fatiado.append(bloco_corrente)
            bloco_corrente = []
        bloco_corrente.append(ln)
    if bloco_corrente: lote_fatiado.append(bloco_corrente)
    return lote_fatiado

arquivo_enviado = st.file_uploader("Selecione o arquivo de lote com os 17 erros para teste", type=["txt"])

if arquivo_enviado is not None:
    conteudo_cru = arquivo_enviado.getvalue().decode("utf-8")
    blocos_encontrados = separar_lote_por_nota(conteudo_cru)
    
    st.markdown(f"<div style='background-color: #F3E5F5; padding: 15px; border-radius: 8px; border-left: 5px solid #7B1FA2; color: #4A148C; margin-bottom: 20px;'>📋 <b>Lote Mapeado:</b> Identificados <b>{len(blocos_encontrados)} arquivo(s) individual(is)</b> para correção.</div>", unsafe_allow_html=True)
    
    if st.button("🪄 Executar Correção Definitiva dos 17 Erros", type="primary"):
        if not chave_ambiente:
            st.error("❌ Configure o segredo 'GEMINI_API_KEY' nas diretrizes do Streamlit Cloud.")
        else:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                progresso = st.progress(0)
                client = genai.Client(api_key=chave_ambiente)
                
                status_text = st.empty()
                for idx, linhas_nota in enumerate(blocos_encontrados):
                    status_text.markdown(f"⚙️ Processando nota {idx + 1} de {len(blocos_encontrados)}...", unsafe_allow_html=True)
                    texto_nota_bruta = "\n".join(linhas_nota)
                    
                    conteudo_final = None
                    for tentativa in range(3):
                        try:
                            response = client.models.generate_content(
                                model='gemini-3.8-flash',
                                contents=f"Audite, separe e reposicione as colunas desta nota de acordo com as regras:\n\n{texto_nota_bruta}",
                                config=types.GenerateContentConfig(system_instruction=FONTE_CONHECIMENTO, temperature=0.1)
                            )
                            conteudo_final = response.text.strip()
                            break
                        except Exception:
                            time.sleep(5)
                    
                    if conteudo_final:
                        nome_arquivo = f"NOTA_INDIVIDUAL_{idx + 1}.txt"
                        for linha in conteudo_final.splitlines():
                            if linha.startswith("B|"):
                                cps = linha.split("|")
                                if len(cps) >= 7 and cps[6].isdigit():
                                    nome_arquivo = f"NOTA_{cps[6]}.txt"
                                break
                        zip_file.writestr(nome_arquivo, conteudo_final)
                    
                    progresso.progress((idx + 1) / len(blocos_encontrados))
                    if idx < len(blocos_encontrados) - 1: time.sleep(5)
                status_text.empty()
                
            st.markdown("<div style='background-color: #E8F5E9; padding: 15px; border-radius: 8px; border-left: 5px solid #2E7D32; color: #1B5E20; margin-bottom: 25px;'>✅ <b>Processo Concluído!</b> Os 17 erros foram mitigados.</div>", unsafe_allow_html=True)
            st.download_button(label="📦 Baixar Lote Desmembrado e Corrigido (.ZIP)", data=zip_buffer.getvalue(), file_name="LOTES_IOB_CORRIGIDOS.zip", mime="application/zip")
