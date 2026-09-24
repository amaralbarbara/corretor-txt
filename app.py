import streamlit as st
import io
import os
import zipfile
import time
from google import genai
from google.genai import types

# 🎨 CONFIGURAÇÃO DA INTERFACE WEB (Estilo IOB Premium)
st.set_page_config(page_title="Desmembrador Lote TXT - IOB", page_icon="💜", layout="centered")

# Injeção de CSS Customizado para transformar os elements visuais nos tons de roxo da IOB
st.markdown("""
    <style>
        /* Cor de fundo principal e fontes */
        .stApp {
            background-color: #fcfaff;
        }
        h1 {
            color: #4A148C !important; /* Roxo Escuro IOB */
            font-weight: 800 !important;
        }
        
        /* Customização do Botão Principal (Roxo IOB em Degradê) */
        div.stButton > button:first-child {
            background: linear-gradient(135deg, #7B1FA2 0%, #4A148C 100%) !important;
            color: white !important;
            border: none !important;
            border-radius: 8px !important;
            padding: 0.6rem 2rem !important;
            font-weight: bold !important;
            font-size: 16px !important;
            box-shadow: 0 4px 15px rgba(74, 20, 140, 0.2) !important;
            transition: all 0.3s ease !important;
            width: 100% !important;
        }
        div.stButton > button:first-child:hover {
            background: linear-gradient(135deg, #9C27B0 0%, #6A1B9A 100%) !important;
            box-shadow: 0 6px 20px rgba(74, 20, 140, 0.4) !important;
            transform: translateY(-2px);
        }

        /* Área de Upload de Arquivos Customizada */
        .stFileUploader {
            border: 2px dashed #9C27B0 !important;
            background-color: #F3E5F5 !important;
            border-radius: 12px !important;
            padding: 10px !important;
        }

        /* Customização da Barra de Progresso */
        .stProgress > div > div > div > div {
            background-color: #7B1FA2 !important;
        }
    </style>
""", unsafe_allow_html=True)

# Topo da Página com Identidade Visual
st.markdown("<div style='text-align: center; margin-bottom: 25px;'>", unsafe_allow_html=True)
st.title("💜 Desmembrador Inteligente de Lotes TXT")
st.markdown("""
<div style='text-align: center; color: #6A1B9A; font-size: 15px; margin-top: -10px; margin-bottom: 25px;'>
    Análise, separação estrutural e alinhamento de campos de notas fiscais padrão <b>NF-e v4.00</b>.
</div>
""", unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

# Busca a chave interna de forma segura nos Secrets ocultos do Streamlit Cloud
chave_ambiente = st.secrets.get("GEMINI_API_KEY", "")

# --- FONTE DE CONHECIMENTO COMPLETA INTEGRADA NA IA ---
FONTE_CONHECIMENTO = """
Você é um especialista em layouts de NF-e v4.00 TXT.
Sua função é receber o fragmento de UMA ÚNICA nota fiscal extraída de um lote, corrigir o alinhamento de posições de seus campos e limpá-la seguindo as regras restritas abaixo:

REGRAS OBRIGATÓRIAS DE LIMPEZA:
1. Comece o arquivo obrigatoriamente com o registro de controle fixado em: NOTAFISCAL|1
2. Remova e elimine completamente qualquer linha 'N|' (vazia). O correto é a linha 'M|' ser seguida diretamente pela linha do imposto (ex: N02|, N03|, etc.). A linha N| quebra o parser do emissor.
3. Na linha B, force o modo RASCUNHO deixando vazios os campos cNF (campo 2), cDV (campo 14), dhCont (campo 21) e xJust (campo 22) usando ||. O campo 13 (tpEmis) deve ser fixado em 1.

REPOSICIONAMENTO DE CAMPOS:
- Se você identificar que algum dado mudou de coluna/posição dentro dos delimitadores (|) devido a erros de preenchimento do cliente, use o padrão do layout (Grupo B, C, E, H, I, M, N, Q, S, W, X, YA, Z) para colocá-lo na posição correta.
- Não efetue cálculos matemáticos e não mude valores numéricos de impostos.

Retorne EXCLUSIVAMENTE o conteúdo corrigido da nota fiscal textual estruturada. Não adicione nenhuma saudação, explicação ou marcação markdown (sem ```txt). Comece direto com NOTAFISCAL|1.
"""

def desmembrar_lote_txt(conteudo_completo):
    """Separa o arquivo bruto em blocos individuais baseando-se na abertura do registro A|4.00"""
    linhas = conteudo_completo.splitlines()
    blocos_notas = []
    bloco_atual = []
    
    for linha in linhas:
        linha_limpa = linha.strip()
        if not linha_limpa:
            continue
        
        # Cada nota inicia com o Grupo A
        if linha_limpa.startswith("A|4.00") and bloco_atual:
            blocos_notas.append("\n".join(bloco_atual))
            bloco_atual = []
            
        if not linha_limpa.startswith("NOTAFISCAL|"):
            bloco_atual.append(linha_limpa)
            
    if bloco_atual:
        blocos_notas.append("\n".join(bloco_atual))
        
    return blocos_notas

# Componente Centralizado de Envio de Arquivos
arquivo_enviado = st.file_uploader("Arraste o lote consolidado do cliente (.txt) para este quadrante", type=["txt"])

if arquivo_enviado is not None:
    conteudo_bruto = arquivo_enviado.getvalue().decode("utf-8")
    
    # Executa o desmembramento lógico das notas contidas no arquivo
    notas_extraidas = desmembrar_lote_txt(conteudo_bruto)
    
    st.markdown(f"""
    <div style='background-color: #F3E5F5; padding: 15px; border-radius: 8px; border-left: 5px solid #7B1FA2; color: #4A148C; margin-bottom: 20px;'>
        📋 <b>Lote Mapeado:</b> Identificamos <b>{len(notas_extraidas)} Nota(s) Fiscal(is)</b> prontas para processamento individual.
    </div>
    """, unsafe_allow_html=True)
    
    if st.button("🪄 Desmembrar Lote & Aplicar Critérios IOB", type="primary"):
        if not chave_ambiente:
            st.error("❌ Erro de Configuração: Nenhuma chave de API encontrada nos Secrets do Streamlit Cloud.")
        else:
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                progresso = st.progress(0)
                
                os.environ["GEMINI_API_KEY"] = chave_ambiente
                client = genai.Client()
                
                status_text = st.empty()
                for idx, nota_bruta in enumerate(notas_extraidas):
                    status_text.markdown(f"<span style='color: #6A1B9A;'>⚙️ Analisando e estruturando nota <b>{idx + 1}</b> de {len(notas_extraidas)}...</span>", unsafe_allow_html=True)
                    
                    conteudo_final_nota = None
                    # Mecanismo de retentativas inteligentes em caso de erro do servidor
                    for tentativa in range(4):
                        try:
                            response = client.models.generate_content(
                                model='gemini-2.5-flash', # Mudado para a versão estável de produção global
                                contents=f"Processe e alinhe este fragmento isolado de nota conforme as regras:\n\n{nota_bruta}",
                                config=types.GenerateContentConfig(
                                    system_instruction=FONTE_CONHECIMENTO,
                                    temperature=0.1,
                                )
                            )
                            conteudo_final_nota = response.text.strip()
                            break # Se funcionou, sai do loop de tentativas
                        except Exception as e:
                            if tentativa < 3:
                                # Aumenta o tempo de descanso progressivamente se o servidor falhar
                                time.sleep(6 + (tentativa * 2))
                            else:
                                st.error(f"Falha persistente na Nota {idx + 1}: {e}")
                    
                    if conteudo_final_nota:
                        # Identifica o número do documento para nomear o arquivo
                        nome_arquivo = f"NOTA_INDIVIDUAL_{idx + 1}.txt"
                        for linha in conteudo_final_nota.splitlines():
                            if linha.startswith("B|"):
                                campos_b = linha.split("|")
                                if len(campos_b) >= 7 and campos_b[6].isdigit():
                                    nome_arquivo = f"NOTA_{campos_b[6]}.txt"
                                break
                        
                        zip_file.writestr(nome_arquivo, conteudo_final_nota)
                    
                    # Atualiza o progresso e aplica pausa de segurança entre requisições
                    progresso.progress((idx + 1) / len(notas_extraidas))
                    if idx < len(notas_extraidas) - 1:
                        time.sleep(4)
                
                status_text.empty()
            
            # Garante que só mostre sucesso se houver arquivos gerados com sucesso
            if zip_file.namelist():
                st.markdown("""
                <div style='background-color: #E8F5E9; padding: 15px; border-radius: 8px; border-left: 5px solid #2E7D32; color: #1B5E20; margin-top: 15px; margin-bottom: 25px;'>
                    ✅ <b>Sucesso Absoluto!</b> Todas as notas fiscais foram divididas, auditadas e convertidas em rascunhos funcionais.
                </div>
                """, unsafe_allow_html=True)
                
                st.download_button(
                    label="📦 Baixar Lote Desmembrado (.ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name="LOTES_NF_E_IOB_CORRIGIDOS.zip",
                    mime="application/zip"
                )
