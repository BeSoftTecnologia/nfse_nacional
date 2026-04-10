"""
Funções utilitárias para processamento de NFSe no padrão nacional.
"""

import re
import gzip
import base64
from typing import Optional, Union
import unicodedata


def sanitize_document(value: str) -> str:
    """
    Remove caracteres não numéricos de um documento (CPF/CNPJ).
    
    Args:
        value: String com documento
        
    Returns:
        String apenas com dígitos
    """
    return re.sub(r"\D", "", value) if value else value


def remove_accents(input_str: str) -> str:
    """
    Remove acentuações de uma string.
    
    Args:
        input_str: String com acentuações
        
    Returns:
        String sem acentuações
    """
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    only_ascii = nfkd_form.encode('ASCII', 'ignore')
    return only_ascii.decode()


def to_float(v):
    """
    Converte um valor para float, tratando diferentes formatos.
    
    Args:
        v: Valor a ser convertido (pode ser string, int, float)
        
    Returns:
        float ou None se não for possível converter
    """
    if v is None or v == "":
        return None
    s = str(v).strip().replace("%", "").replace(" ", "")
    # Trata formato brasileiro (1.234,56)
    if s.count(",") == 1 and s.count(".") > 1:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s.replace(",", "."))
    except Exception:
        return None


def ctn_to_6digits(cod: Optional[str]) -> Optional[str]:
    """
    Converte código de serviço (CTN) para formato de 6 dígitos.
    Aceita formatos como "1.05", "0105", "1.05.01", etc.
    
    Args:
        cod: Código de serviço em qualquer formato
        
    Returns:
        Código normalizado com 6 dígitos ou None se inválido
    """
    if not cod:
        return None
    s = str(cod).strip()
    # Remove descrição se houver (ex: "1.05 - Descrição")
    if " - " in s:
        s = s.split(" - ", 1)[0].strip()
    # Tenta formato com pontos (ex: "1.05.01" ou "1.05")
    m = re.match(r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{1,2}))?$", s)
    if m:
        a, b, c = m.groups()
        if c:
            return f"{a.zfill(2)}{b.zfill(2)}{c.zfill(2)}"
        else:
            # Se só tem 2 grupos, assume terceiro como "01"
            return f"{a.zfill(2)}{b.zfill(2)}01"
    # Remove todos os não-dígitos e normaliza
    digits = re.sub(r"\D", "", s)
    # Se tiver 4 dígitos, adiciona "01" no final para completar 6
    if len(digits) == 4:
        digits = digits + "01"
    # Se tiver 5 dígitos, adiciona "0" no início
    elif len(digits) == 5:
        digits = "0" + digits
    return digits if len(digits) == 6 else None


def normalize_cst_pis_cofins(raw: Optional[str]) -> Optional[str]:
    """
    Extrai o CST PIS/COFINS (2 dígitos: 00–09) do valor informado no payload.
    Aceita \"01\", \"01 - Operação tributável...\", etc.
    """
    if raw is None or raw == "":
        return None
    s = str(raw).strip()
    if " - " in s:
        s = s.split(" - ", 1)[0].strip()
    m = re.match(r"^(\d{2})\b", s)
    if m:
        return m.group(1)
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 2:
        return digits[:2]
    return None


def normalize_tp_ret_pis_cofins(raw: Optional[str]) -> Optional[str]:
    """
    Normaliza tpRetPisCofins (1 dígito: 0–9 conforme NT007 / portal nacional).
    """
    if raw is None or raw == "":
        return None
    s = str(raw).strip()
    if s.isdigit() and len(s) == 1 and "0" <= s <= "9":
        return s
    m = re.match(r"^(\d)", s)
    return m.group(1) if m and m.group(1) in "0123456789" else None


def normalize_codigo_nbs(cod: Optional[str]) -> Optional[str]:
    """
    Normaliza o código NBS (Nomenclatura Brasileira de Serviços) para o layout da DPS.
    Remove pontuação e caracteres não numéricos (ex.:1.1406.11.00 → 114061100).
    """
    if not cod:
        return None
    s = str(cod).strip()
    if " - " in s:
        s = s.split(" - ", 1)[0].strip()
    digits = re.sub(r"\D", "", s)
    return digits or None


def gerar_dpsXmlGZipB64(xml_input: Union[str, bytes]) -> str:
    """
    Compacta um XML e codifica em Base64 (formato exigido pelo portal nacional).
    Aceita bytes diretamente para evitar decode após assinatura.
    
    Args:
        xml_input: XML como string ou bytes (preferir bytes do signer)
        
    Returns:
        String Base64 do XML compactado com GZIP
    """
    xml_bytes = xml_input if isinstance(xml_input, bytes) else xml_input.encode("utf-8")
    compressed_data = gzip.compress(xml_bytes)
    return base64.b64encode(compressed_data).decode("utf-8")

