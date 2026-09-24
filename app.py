import streamlit as st
import io
from google import genai
from google.genai import types

# Configuração da Interface Web
st.set_page_config(page_title="Validador Inteligente de TXT", page_icon="🤖", layout="centered")

st.title("🤖 Corretor Estrutural de TXT NF-e v4.00")
st.markdown("""
Esta ferramenta utiliza **Inteligência Artificial** para interpretar, mapear e corrigir a **posição dos campos** 
do TXT do seu cliente, baseando-se estritamente nas regras oficiais do layout.
""")

# Input para o usuário colocar a chave gratuita da API do Gemini
api_key = st.sidebar.text_input("Insira sua Gemini API Key:", type="password")
st.sidebar.markdown("[Clique aqui para obter uma chave de API gratuita](https://google.com)")

# Carregar o arquivo do cliente
arquivo_enviado = st.file_uploader("Arraste ou selecione o arquivo .txt do cliente", type=["txt"])

# Sua fonte de conhecimento incorporada diretamente como regra de sistema
FONTE_CONHECIMENTO = """
Você é um interpretador e especialista em layouts de NF-e v4.00 TXT.
Sua única função é ler o TXT bagunçado ou desalinhado enviado pelo cliente, identificar quais informações foram colocadas nas posições erradas por erro de preenchimento ou geração do sistema deles, e reconstruir o TXT colocando cada dado na sua posição correta de acordo com as regras abaixo:

REGRA DE OURO DA ESTRUTURA:
- Cada item deve seguir a sequência: Linha H -> Linha I -> Linha M (vazia) -> Linha Nxx (Bloco de ICMS direto).
- NUNCA use ou mantenha a linha 'N|' vazia. Se ela existir entre a M e a Nxx, elimine-a completamente, pois ela quebra o parser.

REGRA DE OURO DO RASCUNHO:
- Na linha B, você deve forçar o modo rascunho limpando as posições de cNF (campo 2), cDV (campo 14), dhCont (campo 21) e xJust (campo 22) - deixe-os vazios (||). Garanta que o campo 13 (tpEmis) seja igual a 1.

COMPREENSÃO DE CAMPOS FORA DE POSIÇÃO:
- Analise os delimitadores (|). Se você perceber que campos numéricos (como NCM de 8 dígitos, CFOP de 4 dígitos ou valores decimais) mudaram de posição por erro do cliente, remaneje-os para as posições corretas descritas nos grupos (Grupo B, C, E, H, I, M, N, Q, S, W, X, YA, Z).
- Não recalcule nenhum valor. Apenas garanta que o dado certo esteja na coluna/posição certa do pipe (|).
- Se houver múltiplas notas (NOTAFISCAL|N com N > 1), processe apenas a primeira ou organize de forma que respeite os blocos A a Z de forma estrita.

Retorne APENAS o conteúdo do novo arquivo TXT corrigido. Não adicione nenhuma saudação, explicação ou formatação markdown (sem ```txt). Comece direto com NOTAFISCAL|1.
"""

if arquivo_enviado is not None:
    # Lendo o TXT mal formatado do cliente
    conteudo_cliente = arquivo_enviado.getvalue().decode("utf-8")
    
    st.subheader("Conteúdo Original do Cliente (Para Análise)")
    st.text_area("O que o cliente enviou:", conteudo_cliente, height=200, disabled=True)
    
    if st.button("🪄 Corrigir Posições e Estrutura com IA", type="primary"):
        if not api_key:
            st.error("❌ Por favor, insira sua Gemini API Key na barra lateral esquerda para prosseguir gratuitamente.")
        else:
            with st.spinner("A IA está interpretando o arquivo e reposicionando os campos..."):
                try:
                    # Inicializa o cliente oficial do Google GenAI
                    client = genai.Client(api_key=api_key)
                    
                    # Faz a chamada ao modelo ideal para textos e códigos (Gemini 2.5 Flash)
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=f"Aqui está o TXT com problemas do cliente:\n\n{conteudo_cliente}",
                        config=types.GenerateContentConfig(
                            system_instruction=FONTE_CONHECIMENTO,
                            temperature=0.1, # Temperatura baixa para a IA ser extremamente literal e precisa
                        )
                    )
                    
                    txt_corrigido = response.text.strip()
                    
                    st.success("✅ Arquivo interpretado e corrigido com sucesso!")
                    
                    # Exibe o resultado interpretado na tela
                    st.text_area("TXT com campos reposicionados corretamente:", txt_corrigido, height=300)
                    
                    # Permite baixar o arquivo limpo e funcional
                    st.download_button(
                        label="📥 Baixar TXT Corrigido",
                        data=txt_corrigido,
                        file_name=f"ESTRUTURADO_{arquivo_enviado.name}",
                        mime="text/plain"
                    )
                    
                except Exception as e:
                    st.error(f"Erro ao processar com a IA: {e}")
