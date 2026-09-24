import base64
import io
import time
import zipfile
from pathlib import Path

import streamlit as st
from google import genai

from iob_core import (aplicar_patches, corrigir_nota, limitar_campos,
                      revisar_com_ia, separar_lote, validar)

BASE = Path(__file__).parent
ROXO, ROXO_ESCURO, ROSA, ROSA_HOVER, LILAS = "#4F0072", "#3A0055", "#FF005A", "#D9004C", "#F6EFFA"

st.set_page_config(
    page_title="Conversor | IOB",
    page_icon=str(BASE / "icone_iob.png") if (BASE / "icone_iob.png").exists() else None,
    layout="centered",
)

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
html, body, .stApp, [class*="css"] {{ font-family: 'Plus Jakarta Sans', 'Segoe UI', sans-serif; }}
.stApp {{ background: #FFFFFF; }}
#MainMenu, footer, header[data-testid="stHeader"] {{ visibility: hidden; height: 0; }}
.block-container {{ padding-top: 2rem; max-width: 780px; }}

.iob-hero {{ background: {ROXO}; border-radius: 16px; padding: 28px 32px; margin-bottom: 28px; }}
.iob-hero img {{ height: 38px; display: block; margin-bottom: 22px; }}
.iob-hero h1 {{ color: #fff !important; font-size: 34px; font-weight: 800; margin: 0 0 6px 0; padding: 0; letter-spacing: -0.5px; }}
.iob-hero p {{ color: #E9D5F5; font-size: 15px; margin: 0; line-height: 1.5; }}

.iob-step {{ display: flex; align-items: center; gap: 12px; margin: 26px 0 10px; }}
.iob-step span.n {{ background: {ROXO}; color: #fff; width: 28px; height: 28px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px; }}
.iob-step span.t {{ color: {ROXO}; font-weight: 700; font-size: 17px; }}

.iob-box {{ border-radius: 10px; padding: 14px 18px; margin: 12px 0; font-size: 14.5px; line-height: 1.5; }}
.iob-info {{ background: {LILAS}; border-left: 4px solid {ROXO}; color: {ROXO_ESCURO}; }}
.iob-ok {{ background: #EAF7EF; border-left: 4px solid #1E8E4E; color: #14532D; }}
.iob-warn {{ background: #FFF1F5; border-left: 4px solid {ROSA}; color: #7A0030; }}

[data-testid="stFileUploader"] section {{ background: {LILAS}; border: 2px dashed {ROXO}; border-radius: 12px; }}
[data-testid="stFileUploader"] button {{ background: #fff; color: {ROXO}; border: 1.5px solid {ROXO}; border-radius: 8px; font-weight: 600; }}
[data-testid="stFileUploader"] button:hover {{ background: {ROXO}; color: #fff; }}

div.stButton > button, div.stDownloadButton > button {{
  width: 100%; border-radius: 10px; font-weight: 700; font-size: 16px; padding: 0.7rem 1rem;
  border: none; color: #fff; background: {ROSA}; transition: background .15s ease; }}
div.stButton > button:hover, div.stDownloadButton > button:hover {{ background: {ROSA_HOVER}; color: #fff; }}
div.stButton > button:focus:not(:active), div.stDownloadButton > button:focus:not(:active) {{ color: #fff; border: none; box-shadow: 0 0 0 3px rgba(255,0,90,.25); }}
div.stDownloadButton > button {{ background: {ROXO}; }}
div.stDownloadButton > button:hover {{ background: {ROXO_ESCURO}; }}

[data-testid="stMetric"] {{ background: {LILAS}; border-radius: 12px; padding: 14px 18px; }}
[data-testid="stMetricLabel"] p {{ color: {ROXO}; font-weight: 600; }}
[data-testid="stMetricValue"] {{ color: {ROXO_ESCURO}; font-weight: 800; }}

[data-testid="stExpander"] {{ border: 1px solid #E4D3EE; border-radius: 10px; }}
[data-testid="stExpander"] summary p {{ color: {ROXO_ESCURO}; font-weight: 600; }}
[data-testid="stCheckbox"] label p {{ color: {ROXO_ESCURO}; }}
.stProgress > div > div > div > div {{ background-color: {ROSA}; }}
</style>
""", unsafe_allow_html=True)


def caixa(texto, tipo="info"):
    st.markdown(f"<div class='iob-box iob-{tipo}'>{texto}</div>", unsafe_allow_html=True)


def passo(n, titulo):
    st.markdown(f"<div class='iob-step'><span class='n'>{n}</span><span class='t'>{titulo}</span></div>",
                unsafe_allow_html=True)


logo = BASE / "logo_iob.png"
logo_html = (f"<img src='data:image/png;base64,{base64.b64encode(logo.read_bytes()).decode()}' alt='IOB'>"
             if logo.exists() else "")
st.markdown(f"""
<div class='iob-hero'>{logo_html}
<h1>Conversor</h1>
<p>Correção e padronização de lotes TXT de NF-e v4.00 para o IOB Emissor.</p></div>
""", unsafe_allow_html=True)

try:
    CHAVE = st.secrets.get("GEMINI_API_KEY", "")
    MODELO_IA = st.secrets.get("GEMINI_MODEL", "gemini-3.8-flash")
except Exception:  # sem secrets.toml (execução local)
    CHAVE, MODELO_IA = "", "gemini-3.8-flash"
ARQ_MODELO = BASE / "modelo_nfe.txt"
MODELO_REF = ARQ_MODELO.read_text(encoding="utf-8") if ARQ_MODELO.exists() else ""


def ler_texto(dados: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return dados.decode(enc)
        except UnicodeDecodeError:
            continue
    return dados.decode("utf-8", errors="replace")


passo(1, "Enviar arquivo")
arquivo = st.file_uploader("Arquivo de lote (.txt)", type=["txt"], label_visibility="collapsed")
usar_ia = st.checkbox("Validar posições dos campos com IA", value=bool(CHAVE))

if arquivo:
    blocos = separar_lote(ler_texto(arquivo.getvalue()))
    caixa(f"<b>{len(blocos)}</b> nota(s) identificada(s) em <b>{arquivo.name}</b>.")

    passo(2, "Converter")
    if st.button("Converter lote", type="primary"):
        if usar_ia and not CHAVE:
            caixa("Configure o segredo <b>GEMINI_API_KEY</b> ou desmarque a validação por IA.", "warn")
            st.stop()
        client = genai.Client(api_key=CHAVE) if usar_ia else None
        buf, relatorio, resumo, usados, falhas_ia = io.BytesIO(), [], [], set(), 0
        prog, status = st.progress(0), st.empty()

        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for i, bloco in enumerate(blocos):
                status.markdown(f"Processando nota {i+1} de {len(blocos)}...")
                linhas, log = corrigir_nota(bloco)
                if usar_ia:
                    resp = revisar_com_ia(client, MODELO_IA, linhas, validar(linhas), MODELO_REF)
                    falhas_ia += 1 if resp.get("erro") else 0
                    linhas, log_ia = aplicar_patches(linhas, resp)
                    linhas, log_lim = limitar_campos(linhas)
                    log += log_ia + log_lim
                    time.sleep(1.5)
                pend = validar(linhas)

                nnf = next((l.split("|")[6] for l in linhas
                            if l.startswith("B|") and len(l.split("|")) > 6 and l.split("|")[6].isdigit()), None)
                nome = f"NOTA_{nnf}.txt" if nnf else f"NOTA_INDIVIDUAL_{i+1}.txt"
                if nome in usados:
                    nome = nome.replace(".txt", f"_{i+1}.txt")
                usados.add(nome)
                z.writestr(nome, "\n".join(linhas) + "\n")

                relatorio.append(f"=== {nome} ===\n" + "\n".join(f"- {x}" for x in log)
                                 + ("\nPENDÊNCIAS:\n" + "\n".join(f"! {x}" for x in pend) if pend else "\nSem pendências."))
                resumo.append((nome, log, pend))
                prog.progress((i + 1) / len(blocos))
            z.writestr("RELATORIO.txt", "\n\n".join(relatorio))
        status.empty()
        prog.empty()
        st.session_state.update(zip=buf.getvalue(), resumo=resumo, falhas_ia=falhas_ia)

if "zip" in st.session_state:
    resumo = st.session_state["resumo"]
    ok = sum(1 for _, _, p in resumo if not p)

    passo(3, "Resultado")
    c1, c2, c3 = st.columns(3)
    c1.metric("Notas convertidas", len(resumo))
    c2.metric("Sem pendências", ok)
    c3.metric("Com pendências", len(resumo) - ok)

    if st.session_state.get("falhas_ia"):
        caixa(f"A IA não respondeu em {st.session_state['falhas_ia']} nota(s). "
              "Essas foram corrigidas e validadas apenas pelo código.", "info")

    st.download_button("Baixar ZIP corrigido", st.session_state["zip"],
                       file_name="LOTES_IOB_CORRIGIDOS.zip", mime="application/zip")

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    for nome, log, pend in resumo:
        rotulo = f"{nome}  |  {'OK' if not pend else str(len(pend)) + ' pendência(s)'}"
        with st.expander(rotulo):
            st.markdown("\n".join(f"- {x}" for x in log) or "Nenhuma alteração necessária.")
            if pend:
                caixa("<b>Pendências</b><br>" + "<br>".join(pend), "warn")
