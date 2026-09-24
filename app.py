import streamlit as st
import io
import os
from google import genai
from google.genai import types

# Configuração da Interface Web
st.set_page_config(page_title="Validador Inteligente de TXT", page_icon="🤖", layout="centered")

st.title("🤖 Corretor Estrutural de TXT NF-e v4.00")
st.markdown("""
Esta ferramenta utiliza **Inteligência Artificial** para interpretar, mapear e corrigir a **posição dos campos** 
do TXT do seu cliente, baseando-se estritamente nas regras oficiais do layout.
""")

# Busca a chave de forma segura nos Secrets do Streamlit Cloud
chave_ambiente = st.secrets.get("GEMINI_API_KEY", "")

# Input na barra lateral (Mascarado por segurança)
api_key = st.sidebar.text_input("Sua Gemini API Key:", value=chave_ambiente, type="password")
st.sidebar.markdown("[Link da Fonte de Conhecimento Oficial (Google Drive)](https://google.com)")

# --- CONTEÚDO INTEGRAL DA SUA FONTE DE CONHECIMENTO ---
FONTE_CONHECIMENTO = """
Você é um interpretador e especialista em layouts de NF-e v4.00 TXT.
Sua única função é ler o TXT bagunçado ou desalinhado enviado pelo cliente, identificar quais informações foram colocadas nas posições erradas por erro de preenchimento ou geração do sistema deles, e reconstruir o TXT colocando cada dado na sua posição correta de acordo com as regras estruturais exatas mapeadas abaixo:

================================================================================
LAYOUT COMPLETO TXT NF-e v4.00 — MAPEADO CAMPO A CAMPO
================================================================================
📌 RESUMO DA ESTRUTURA DOS BLOCOS DE IMPOSTO:
Cada item obrigatoriamente deve seguir esta sequência:
H|... (Cabeçalho do item)
I|... (Dados do Produto)
M|    <- LINHA M (vazia) OBRIGATÓRIA
N02|0|00|3|... <- BLOCO DE ICMS DIRETO (SEM A LINHA N|)

⚠️ ATENÇÃO MÁXIMA: A linha N| (vazia) NÃO DEVE EXISTIR! O parser do sistema a interpreta como "FIM DE BLOCO" e corrompe a nota. Remova-a sempre se o cliente a enviar. O correto é M| seguido direto de N02|, N07|, etc.

⚠️ REGRA DE OURO — TORNAR A NOTA UM RASCUNHO (NÃO IMPORTADA):
Na linha B (Identificação da NF-e), limpe as informações para forçar o nascimento como rascunho:
1. cNF (campo 2 da linha B) DEVE FICAR VAZIO (||)
2. cDV (campo 14 da linha B) DEVE FICAR VAZIO (||)
3. tpEmis (campo 13 da linha B) DEVE SER FORÇADO PARA 1 (Normal)
4. dhCont (campo 21) e xJust (campo 22) DEVEM FICAR VAZIOS (||)

⚠️ REGRA DE OURO — COMPREENSÃO DE POSIÇÕES DOS GRUPOS:
As linhas são delimitadas por pipes (|). Se o cliente moveu informações de lugar por erro (ex: colocou NCM na coluna errada, ou inverteu a ordem de Razão Social), use sua inteligência de interpretação para identificar o que é o dado e reposicione-o no campo correto conforme o mapeamento abaixo:
- GRUPO B: B|<cUF>|<cNF>|<natOp>|<mod>|<serie>|<nNF>|<dhEmi>|<dhSaiEnt>|<tpNF>|<idDest>|<cMunFG>|<tpImp>|<tpEmis>|<cDV>|<tpAmb>|<finNFe>|<indFinal>|<indPres>|<procEmi>|<verProc>|<dhCont>|<xJust>|<indIntermed>|
- GRUPO C (Emitente): C|<xNome>|<xFant>|<IE>|<IEST>|<IM>|<CNAE>|<CRT>| -> Seguido de C02|<CNPJ>| e C05|Endereço|
- GRUPO E (Destinatário): E|<xNome>|<indIEDest>|<IE>|<ISUF>|<IM>|<email>| -> Seguido de E02|<CNPJ>| e E05|Endereço|
- GRUPO I (Produto): I|<cProd>|<cEAN>|<xProd>|<NCM>|<cBenef>|<EXTIPI>|<CFOP>|<uCom>|<qCom>|<vUnCom>|<vProd>|<cEANTrib>|<uTrib>|<qTrib>|<vUnTrib>|<vFrete>|<vSeg>|<vDesc>|<vOutro>|<indTot>|
- GRUPO Q (PIS): Linha Q vazia obrigatória antes de Q02|
- GRUPO S (COFINS): Linha S vazia obrigatória antes de S02|
- GRUPO W (Totais): Linha W vazia obrigatória antes de W02|

Não recalcule nenhum valor matemático. Apenas garanta que cada dado esteja exatamente no cano/coluna correto do layout de pipes (|).
Se houver múltiplas notas (NOTAFISCAL|N com N > 1), processe apenas a primeira ou certifique-se de separar os blocos mantendo a coerência.

Retorne APENAS o conteúdo do novo arquivo TXT corrigido. Não adicione nenhuma saudação, explicação ou formatação markdown (sem ```txt). Comece direto com NOTAFISCAL|1.
"""

# Carregar o arquivo do cliente
arquivo_enviado = st.file_uploader("Arraste ou selecione o arquivo .txt do cliente", type=["txt"])

if arquivo_enviado is not None:
    conteudo_cliente = arquivo_enviado.getvalue().decode("utf-8")
    
    st.subheader("Conteúdo Original do Cliente (Para Análise)")
    st.text_area("O que o cliente enviou:", conteudo_cliente, height=200, disabled=True)
    
    if st.button("🪄 Corrigir Posições e Estrutura com IA", type="primary"):
        chave_ativa = api_key if api_key else chave_ambiente
        
        if not chave_ativa:
            st.error("❌ Nenhuma API Key encontrada. Configure os Secrets do app ou insira na barra lateral.")
        else:
            with st.spinner("A IA está interpretando o arquivo e reposicionando os campos..."):
                try:
                    os.environ["GEMINI_API_KEY"] = chave_ativa
                    client = genai.Client()
                    
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=f"Aqui está o TXT com problemas do cliente:\n\n{conteudo_cliente}",
                        config=types.GenerateContentConfig(
                            system_instruction=FONTE_CONHECIMENTO,
                            temperature=0.1,
                        )
                    )
                    
                    txt_corrigido = response.text.strip()
                    
                    st.success("✅ Arquivo interpretado e corrigido com sucesso!")
                    st.text_area("TXT com campos reposicionados corretamente:", txt_corrigido, height=300)
                    
                    st.download_button(
                        label="📥 Baixar TXT Corrigido",
                        data=txt_corrigido,
                        file_name=f"ESTRUTURADO_{arquivo_enviado.name}",
                        mime="text/plain"
                    )
                    
                except Exception as e:
                    st.error(f"Erro ao processar com a IA: {e}")
