"""
Localização do USUÁRIO a partir de um CEP (complemento 5.13 — "postos perto de mim").

    geocodificar_cep("01310-200") -> {"ok": True, "lat": -23.56, "lon": -46.65, "descricao": "...", "fonte": "CEP 01310-200"}

- Usa a Google Geocoding API (chave GOOGLE_MAPS_API_KEY no .env / Secrets; nunca no código; nunca impressa).
- Envia ao Google SOMENTE os 8 dígitos do CEP (nenhum outro dado do usuário).
- Não guarda nada em disco: a coordenada vale só para a sessão (termos do Google: no máximo 30 dias).
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request

URL = "https://maps.googleapis.com/maps/api/geocode/json"


def limpar_cep(texto: str) -> str | None:
    """Aceita '01310-200', '01310200' ou '01.310-200'; devolve só os 8 dígitos (ou None se inválido)."""
    digitos = re.sub(r"\D", "", texto or "")
    return digitos if len(digitos) == 8 and digitos != "00000000" else None


def geocodificar_cep(texto: str) -> dict:
    cep = limpar_cep(texto)
    if not cep:
        return {"ok": False, "erro": "CEP inválido: informe 8 dígitos (ex.: 01310-200)."}
    chave = os.getenv("GOOGLE_MAPS_API_KEY")
    if not chave:
        return {"ok": False, "erro": "Busca por CEP indisponível (chave do Google não configurada)."}
    parametros = {"components": f"postal_code:{cep}|country:BR", "region": "br", "key": chave}
    try:
        with urllib.request.urlopen(URL + "?" + urllib.parse.urlencode(parametros), timeout=15) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
    except Exception:                                   # sem internet, timeout... (sem expor detalhes/chave)
        return {"ok": False, "erro": "Não consegui consultar o CEP agora. Tente de novo ou use o botão de localização."}
    if dados.get("status") != "OK" or not dados.get("results"):
        return {"ok": False, "erro": f"CEP {cep[:5]}-{cep[5:]} não encontrado."}
    r = dados["results"][0]
    return {"ok": True, "lat": r["geometry"]["location"]["lat"], "lon": r["geometry"]["location"]["lng"],
            "descricao": r["formatted_address"], "fonte": f"CEP {cep[:5]}-{cep[5:]}"}
