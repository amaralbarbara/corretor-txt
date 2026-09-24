import io
import time
import zipfile
from pathlib import Path

import streamlit as st
from google import genai

from iob_core import (aplicar_patches, corrigir_nota, limitar_campos,
                      revisar_com_ia, separar_lote, validar)

st.set_page_config(page_title="Corretor de Lotes TXT - IOB", page_icon="💜", layout="centered")
st.markdown(
    "<style>.stApp{background-color:#fcfaff}h1{color:#4A148C!important;font-weight:800!important}"
    "div.stButton>button:first-child{background:linear-gradient(135deg,#7B1FA2 0%,#4A148C 100%)!important;"
    "color:white!important;border:none!important;border-radius:8px!important;width:100%!important}"
    ".stFileUploader{border:2px dashed #9C27B0!important;background-color:#F3E5F5!important}</style>",
    unsafe_allow_html=True,
)
st.title("💜 Corretor Estrutural de Lotes IOB")
st.caption("Código aplica as regras fixas. IA valida posições e resolve casos ambíguos.")

CHAVE = st.secrets.get("GEMINI_API_KEY", "")
MODELO_IA = st.secrets.get("GEMINI_MODEL", "gemini-3.8-flash")
ARQ_MODELO = Path(__file__).parent / "modelo_nfe.txt"  # opcional: TXT correto de referência
MODELO_REF = ARQ_MODELO.read_text(encoding="utf-8") if ARQ_MODELO.exists() else ""


def ler_texto(dados: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return dados.decode(enc)
        except UnicodeDecodeError:
            continue
    return dados.decode("utf-8", errors="replace")


arquivo = st.file_uploader("Selecione o arquivo de lote (.txt)", type=["txt"])
usar_ia = st.checkbox("Validar posições com IA (Gemini)", value=bool(CHAVE))

if arquivo:
    blocos = separar_lote(ler_texto(arquivo.getvalue()))
    st.info(f"📋 {len(blocos)} nota(s) identificada(s) no lote.")

    if st.button("🪄 Corrigir lote", type="primary"):
        if usar_ia and not CHAVE:
            st.error("Configure o segredo GEMINI_API_KEY ou desmarque a validação por IA.")
            st.stop()
        client = genai.Client(api_key=CHAVE) if usar_ia else None
        buf, relatorio, resumo, usados, falhas_ia = io.BytesIO(), [], [], set(), 0
        prog, status = st.progress(0), st.empty()

        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for i, bloco in enumerate(blocos):
                status.write(f"⚙️ Nota {i+1}/{len(blocos)}...")
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
        st.session_state["zip"], st.session_state["resumo"] = buf.getvalue(), resumo
        st.session_state["falhas_ia"] = falhas_ia

if "zip" in st.session_state:
    ok = sum(1 for _, _, p in st.session_state["resumo"] if not p)
    st.success(f"✅ Concluído. {ok}/{len(st.session_state['resumo'])} nota(s) sem pendências.")
    if st.session_state.get("falhas_ia"):
        st.info(f"IA não respondeu em {st.session_state['falhas_ia']} nota(s); "
                "essas foram corrigidas e validadas só pelo código.")
    for nome, log, pend in st.session_state["resumo"]:
        with st.expander(f"{'✅' if not pend else '⚠️'} {nome} — {len(log)} correção(ões)"):
            st.write("\n".join(f"- {x}" for x in log) or "Nada alterado.")
            if pend:
                st.warning("\n".join(f"- {x}" for x in pend))
    st.download_button("📦 Baixar ZIP corrigido", st.session_state["zip"],
                       file_name="LOTES_IOB_CORRIGIDOS.zip", mime="application/zip")
