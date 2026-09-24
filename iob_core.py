"""Núcleo do corretor de TXT NF-e v4.00 (IOB Emissor).

Código resolve o que é regra fixa. IA só valida posições e sugere ajustes
pontuais (patches por linha) — nunca reescreve a nota inteira.
"""
import json
import time
from decimal import Decimal, ROUND_HALF_UP

# ---------------------------------------------------------------- utilidades
def D(v):
    try:
        return Decimal(str(v).strip().replace(",", ".")) if str(v).strip() else Decimal(0)
    except Exception:
        return Decimal(0)


def fmt(d):
    return f"{Decimal(d).quantize(Decimal('0.01'), ROUND_HALF_UP):.2f}"


def g(p, i):
    return D(p[i]) if i is not None and i < len(p) else Decimal(0)


def pad(p, n):
    return p + [""] * (n - len(p))


# ---------------------------------------------------------------- constantes
# posições (índice após split("|"), [0] = tag) conforme modelo IOB enviado
ICMS_IDX = {  # tag: (vBC, vICMS, vBCST, vICMSST, vFCP, vFCPST)
    "N02": (4, 6, None, None, 8, None),
    "N03": (4, 6, 13, 15, 9, 18),
    "N05": (None, None, 6, 8, None, None),
    "N07": (5, 10, None, None, None, None),
    "N09": (4, 7, 11, 13, None, None),
    "N10": (4, 7, 11, 13, None, None),
}
TAGS_ICMS = {"N02", "N03", "N04", "N05", "N06", "N07", "N08", "N09", "N10"}
TAGS_INVALIDAS = {"W04c", "W04e", "W04g", "E03a"}
MAX_CAMPOS = {"I18": 11, "I25": 5}  # campos após a tag


# ---------------------------------------------------------------- separação
def separar_lote(texto):
    """Quebra lote em notas. Nova nota começa em NOTAFISCAL| ou em 2º 'A|'."""
    blocos, atual, tem_a = [], [], False
    for raw in texto.splitlines():
        ln = raw.strip()
        if not ln:
            continue
        up = ln.upper()
        if up.startswith("NOTAFISCAL") or (ln.startswith("A|") and tem_a):
            if atual:
                blocos.append(atual)
            atual, tem_a = [], False
        if ln.startswith("A|"):
            tem_a = True
        atual.append(ln)
    if atual:
        blocos.append(atual)
    return blocos


# ---------------------------------------------------------------- detecção
def detectar_importacao(linhas):
    """Parceiro no exterior (UF EX / país != 1058 / E03a) ou CFOP 3xxx."""
    for l in linhas:
        p = l.split("|")
        p = pad(p, 12)
        if p[0] == "E03a":
            return True
        if p[0] == "E05" and (p[7].upper() == "EX" or (p[9].strip() and p[9].strip() != "1058")):
            return True
        if p[0] == "I" and p[6].startswith("3"):
            return True
    return False


def cnpj_emitente(linhas):
    for l in linhas:
        p = l.split("|")
        if p[0] == "C02" and len(p) > 1:
            return p[1]
    return ""


# ---------------------------------------------------------------- correção
def corrigir_nota(linhas_in):
    log = []
    L = [l.rstrip() for l in linhas_in if l.strip()]
    importacao = detectar_importacao(L)
    cnpj_emit = cnpj_emitente(L)
    if importacao:
        log.append("Detectada nota de importação/parceiro exterior.")

    # 1) cabeçalho
    if not L or L[0].strip() != "NOTAFISCAL|1":
        log.append("Cabeçalho ajustado para NOTAFISCAL|1.")
    L = [l for l in L if not l.upper().startswith("NOTAFISCAL")]

    out = ["NOTAFISCAL|1"]
    vprod_item = Decimal(0)
    for l in L:
        p = l.split("|")
        tag = p[0]

        # 5) linhas N vazias
        if tag == "N" and not any(x.strip() for x in p[1:]):
            log.append("Removida linha 'N' vazia.")
            continue
        # 10) + 8) grupos inexistentes
        if tag in TAGS_INVALIDAS:
            log.append(f"Removida linha inválida {tag}.")
            continue
        # 6) M||
        if tag == "M" and l.strip() == "M||":
            out.append("M|")
            log.append("M|| → M|.")
            continue

        if tag == "B":
            p = list(p)
            if len(p) > 12 and p[11].isdigit() and len(p[11]) == 7 and p[12] == p[11]:
                del p[12]
                log.append("cMunFG duplicado removido na linha B.")
            p = pad(p, 25)
            antes = "|".join(p)
            p[2] = p[14] = p[21] = p[22] = ""
            p[13] = "1"
            if importacao and p[9] == "0":
                p[9] = "1"
                log.append("tpNF 0 → 1 (entrada de importação).")
            if "|".join(p) != antes:
                log.append("Linha B em modo rascunho (cNF/cDV/dhCont/xJust vazios, tpEmis=1).")
            out.append("|".join(p))
            continue

        if tag == "I":
            p = pad(p, 20)
            vprod_item = D(p[10])

        if tag == "N04" and len(p) > 2 and p[2] == "20":
            p = pad(p, 8)
            orig, modbc, vbc, pred, picms = p[1], p[3], p[4], p[5], p[6]  # ordem IOB
            if not vbc.strip() and vprod_item:
                vbc = fmt(vprod_item * (1 - D(pred) / 100))
            vicms = p[7] if p[7].strip() else fmt(D(vbc) * D(picms) / 100)
            out.append(f"N02|{orig}|00|{modbc}|{vbc}|{picms}|{vicms}||")
            log.append("N04 (CST 20) convertido para N02 (CST 00).")
            continue

        if tag in MAX_CAMPOS:
            lim = MAX_CAMPOS[tag]
            n0 = len(p)
            while len(p) - 1 > lim and p[-1] == "":
                p.pop()
            if len(p) != n0:
                log.append(f"{tag}: pipes excedentes removidos ({n0 - len(p)}).")
            out.append("|".join(p))
            continue

        out.append("|".join(p))

    # 12) orig 1 → 0 em importação
    if importacao:
        for i, l in enumerate(out):
            p = l.split("|")
            if p[0] in TAGS_ICMS and len(p) > 1 and p[1] == "1":
                p[1] = "0"
                out[i] = "|".join(p)
                log.append(f"{p[0]}: orig 1 → 0.")

    # 8) E02 com CNPJ do importador nacional
    if importacao and cnpj_emit:
        idx_e02 = next((i for i, l in enumerate(out) if l.split("|")[0] == "E02"), None)
        if idx_e02 is None:
            idx_e = next((i for i, l in enumerate(out) if l.split("|")[0] == "E"), None)
            if idx_e is not None:
                out.insert(idx_e + 1, f"E02|{cnpj_emit}")
                log.append("Inserida E02 com CNPJ do importador nacional (C02).")
        elif not out[idx_e02].split("|")[1:2] or not out[idx_e02].split("|")[1]:
            out[idx_e02] = f"E02|{cnpj_emit}"
            log.append("E02 vazia preenchida com CNPJ do importador nacional.")

    # 9) W02 recalculada
    t = dict.fromkeys(
        ["vBC", "vICMS", "vBCST", "vST", "vFCP", "vFCPST", "vProd", "vFrete",
         "vSeg", "vDesc", "vOutro", "vIPI", "vPIS", "vCOFINS"], Decimal(0))
    for l in out:
        p = l.split("|")
        tg = p[0]
        if tg == "I":
            p = pad(p, 20)
            t["vProd"] += D(p[10]); t["vFrete"] += D(p[15]); t["vSeg"] += D(p[16])
            t["vDesc"] += D(p[17]); t["vOutro"] += D(p[18])
        elif tg in ICMS_IDX:
            ib, ii, ibs, iis, ifcp, ifcps = ICMS_IDX[tg]
            t["vBC"] += g(p, ib); t["vICMS"] += g(p, ii)
            t["vBCST"] += g(p, ibs); t["vST"] += g(p, iis)
            t["vFCP"] += g(p, ifcp); t["vFCPST"] += g(p, ifcps)
        elif tg == "O07":
            t["vIPI"] += g(p, 2)
        elif tg == "Q02":
            t["vPIS"] += g(p, 4)
        elif tg == "S02":
            t["vCOFINS"] += g(p, 4)
    vnf = (t["vProd"] - t["vDesc"] + t["vST"] + t["vFCPST"] + t["vFrete"]
           + t["vSeg"] + t["vOutro"] + t["vIPI"])
    idx_w = next((i for i, l in enumerate(out) if l.split("|")[0] == "W02"), None)
    vtot_trib = "0.00"
    if idx_w is not None:
        pw = out[idx_w].split("|")
        if len(pw) > 23 and pw[23].strip():
            vtot_trib = pw[23]
    campos = [t["vBC"], t["vICMS"], 0, 0, 0, 0, t["vFCP"], t["vBCST"], t["vST"],
              t["vFCPST"], 0, t["vProd"], t["vFrete"], t["vSeg"], t["vDesc"], 0,
              t["vIPI"], 0, t["vPIS"], t["vCOFINS"], t["vOutro"], vnf]
    calc = [fmt(c) for c in campos] + [vtot_trib]
    if idx_w is not None:
        pw = out[idx_w].split("|")[1:]
        while len(pw) > 23 and pw[-1] == "":
            pw.pop()
        if len(pw) < 23:
            # W02 incompleta: recálculo total
            pw = list(calc)
            log.append("W02 com menos de 23 campos: recalculada por completo.")
        else:
            # valores já preenchidos são preservados; só campos vazios recebem o cálculo
            pw = [v if v.strip() else calc[k] for k, v in enumerate(pw)]
        w02 = "W02|" + "|".join(pw)
        vnf_final = pw[21]
    else:
        w02 = "W02|" + "|".join(calc)
        vnf_final = calc[21]
    if idx_w is not None:
        out[idx_w] = w02
    else:
        pos = next((i for i, l in enumerate(out) if l.split("|")[0] in ("X", "YA")), len(out))
        idx_w_tag = next((i for i, l in enumerate(out) if l == "W"), None)
        out.insert(idx_w_tag + 1 if idx_w_tag is not None else pos, w02)
    vnf = D(vnf_final)
    log.append("W02 com 23 campos (valores existentes preservados; vazios preenchidos).")

    # 11) YA01 higienizada, vPag = vNF
    for i, l in enumerate(out):
        p = l.split("|")
        if p[0] == "YA01":
            p = pad(p, 4)
            ind = p[1] if p[1].strip().isdigit() else "0"
            tpag = p[2] if p[2].strip().isdigit() else "01"
            novo = f"YA01|{ind}|{tpag}|{vnf_final}"
            if novo != l:
                log.append("YA01 higienizada; vPag = vNF.")
            out[i] = novo

    return out, log


def limitar_campos(linhas):
    """Garante I18/I25 sem pipes além do limite (só remove campos vazios do fim)."""
    out, log = [], []
    for l in linhas:
        p = l.split("|")
        lim = MAX_CAMPOS.get(p[0])
        if lim:
            n0 = len(p)
            while len(p) - 1 > lim and p[-1] == "":
                p.pop()
            if len(p) != n0:
                log.append(f"{p[0]}: {n0 - len(p)} pipe(s) excedente(s) removido(s).")
            l = "|".join(p)
        out.append(l)
    return out, log


# ---------------------------------------------------------------- validação
def validar(linhas):
    av = []
    tags = [l.split("|")[0] for l in linhas]
    if not linhas or linhas[0] != "NOTAFISCAL|1":
        av.append("Cabeçalho ≠ NOTAFISCAL|1.")
    if "X" in tags and "X03" not in tags:
        av.append("Grupo X presente mas X03 (transportadora) ausente.")
    for obrig in ("A", "B", "C", "E", "H", "I", "W02", "YA01"):
        if obrig not in tags:
            av.append(f"Registro obrigatório ausente: {obrig}.")
    for i, l in enumerate(linhas, 1):
        p = l.split("|")
        if p[0] == "B":
            if len(p) < 23:
                av.append(f"Linha {i} (B): {len(p)-1} campos, esperado ≥ 22.")
            elif p[2] or p[14] or p[21] or p[22] or p[13] != "1":
                av.append(f"Linha {i} (B): modo rascunho incompleto.")
        if p[0] == "W02" and len(p) - 1 != 23:
            av.append(f"Linha {i} (W02): {len(p)-1} campos, esperado 23.")
        if p[0] == "N04":
            av.append(f"Linha {i}: N04 ainda presente (CST≠20?).")
        if p[0] == "M" and i < len(linhas):
            prox = linhas[i].split("|")[0]
            if prox not in TAGS_ICMS:
                av.append(f"Linha {i}: M não seguida de grupo ICMS (veio {prox}).")
        if p[0] in MAX_CAMPOS and len(p) - 1 > MAX_CAMPOS[p[0]]:
            extra = [x for x in p[1 + MAX_CAMPOS[p[0]]:] if x.strip()]
            av.append(f"Linha {i} ({p[0]}): {len(p)-1} campos, limite {MAX_CAMPOS[p[0]]}"
                      + (f"; conteúdo excedente não vazio: {extra}" if extra else "."))
        if p[0] == "X03" and len(p) - 1 < 5:
            av.append(f"Linha {i} (X03): {len(p)-1} campos, esperado 5.")
        if p[0] in ICMS_IDX:
            vb, vi = g(p, ICMS_IDX[p[0]][0]), g(p, ICMS_IDX[p[0]][1])
            if vb and vi > vb:
                av.append(f"Linha {i} ({p[0]}): vICMS ({fmt(vi)}) > vBC ({fmt(vb)}) — verificar posições.")
    n_h, n_i = tags.count("H"), tags.count("I")
    if n_h != n_i:
        av.append(f"Itens: {n_h} H vs {n_i} I.")
    return av


# ---------------------------------------------------------------- IA (patches)
PROMPT_SISTEMA = """Você é auditor do layout TXT de NF-e v4.00 do IOB Emissor.
O código já aplicou as correções mecânicas. Sua função: validar POSIÇÕES de
campos e interpretar casos ambíguos que o código não resolve.

Convenção: campo N = posição após a tag, separado por '|' (campo 1 = primeiro após a tag).
Posições da linha B: 1 cUF, 2 cNF(vazio), 3 natOp, 4 mod, 5 serie, 6 nNF, 7 dhEmi,
8 dhSaiEnt, 9 tpNF, 10 idDest, 11 cMunFG, 12 tpImp, 13 tpEmis(=1), 14 cDV(vazio),
15 tpAmb, 16 finNFe, 17 indFinal, 18 indPres, 19 procEmi, 20 verProc, 21 dhCont(vazio), 22 xJust(vazio).
Linha I: 1 cProd, 2 cEAN, 3 xProd, 4 NCM, 6 CFOP, 7 uCom, 8 qCom, 9 vUnCom, 10 vProd,
15 vFrete, 16 vSeg, 17 vDesc, 18 vOutro, 19 indTot.
Grupos N04/N09/N10 no IOB: modBC|vBC|pRedBC|pICMS|vICMS (vBC antes de pRedBC).
W02 tem exatamente 23 campos. YA01 = indPag|tPag|vPag (vPag = vNF).
Use o MODELO (se fornecido) como referência de layout correto.

Regras:
- Proponha ajuste SOMENTE se tiver certeza. Na dúvida, use "avisos".
- Não altere valores monetários, totais nem W02/YA01 (código já calculou).
- Cada ajuste mira uma linha pelo número mostrado (1-based).
- 'substituir' mantém a mesma tag. 'remover' e 'inserir_apos' permitidos.
- Máximo 15 ajustes.
Responda SOMENTE JSON:
{"ajustes":[{"linha":int,"acao":"substituir|remover|inserir_apos","novo":"texto da linha","motivo":"curto"}],"avisos":["..."]}"""


def revisar_com_ia(client, model, linhas, avisos_codigo, modelo_ref="", tentativas=3):
    from google.genai import types

    numeradas = "\n".join(f"{i}: {l}" for i, l in enumerate(linhas, 1))
    conteudo = (
        (f"MODELO CORRETO DE REFERÊNCIA:\n{modelo_ref}\n\n" if modelo_ref else "")
        + f"AVISOS DO VALIDADOR DE CÓDIGO:\n{json.dumps(avisos_codigo, ensure_ascii=False)}\n\n"
        + f"NOTA (linhas numeradas):\n{numeradas}"
    )
    for t in range(tentativas):
        try:
            r = client.models.generate_content(
                model=model,
                contents=conteudo,
                config=types.GenerateContentConfig(
                    system_instruction=PROMPT_SISTEMA,
                    temperature=0,
                    response_mime_type="application/json",
                ),
            )
            txt = (r.text or "").strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(txt)
        except Exception as e:  # noqa: BLE001
            pass
            time.sleep(3 * (t + 1))
    return {"ajustes": [], "avisos": [], "erro": True}  # detalhe da exceção descartado de propósito


PROTEGIDAS = {"NOTAFISCAL", "A", "B", "W02", "YA01", "X", "X03"}


def aplicar_patches(linhas, resposta):
    """Aplica ajustes da IA com trava de segurança. Retorna (linhas, log)."""
    log, out = [], list(linhas)
    if resposta.get("erro"):
        return out, log  # falha de API: nada entra no relatório
    ajustes = (resposta.get("ajustes") or [])[:15]
    for a in sorted(ajustes, key=lambda x: -int(x.get("linha", 0))):
        try:
            n = int(a["linha"]) - 1
            acao = a["acao"]
            novo = (a.get("novo") or "").strip()
            motivo = a.get("motivo", "")
            if not 0 <= n < len(out):
                continue
            tag_old = out[n].split("|")[0]
            if acao == "substituir" and novo.split("|")[0] == tag_old and tag_old not in PROTEGIDAS:
                out[n] = novo
            elif acao == "remover" and tag_old not in PROTEGIDAS:
                out.pop(n)
            elif acao == "inserir_apos" and novo and "|" in novo and novo.split("|")[0] not in PROTEGIDAS:
                out.insert(n + 1, novo)
            else:
                log.append(f"IA: ajuste bloqueado na linha {n+1} ({acao}).")
                continue
            log.append(f"IA linha {n+1} [{acao}]: {motivo}")
        except Exception:  # noqa: BLE001
            continue
    for av in resposta.get("avisos") or []:
        log.append(f"IA aviso: {av}")
    return out, log
