"""
Funções para comunicação com a API do Portal Nacional de NFSe.
"""

from lxml import etree as ET
from requests_pkcs12 import post as pkcs12_post, get as pkcs12_get
from requests.exceptions import RequestException
import base64
import gzip
from typing import Optional

URL_PRODUCAO = "https://sefin.nfse.gov.br/SefinNacional/nfse"


def _extrair_xml_nfse_da_consulta(data: dict, logger=None) -> Optional[str]:
    """Extrai o XML autorizado da NFS-e a partir da resposta de consultar_nfse."""
    if not isinstance(data, dict):
        return None

    gz_b64 = data.get("nfseXmlGZipB64") or data.get("nfseXmlGzipB64")
    if gz_b64:
        try:
            return gzip.decompress(base64.b64decode(gz_b64)).decode("utf-8", errors="replace")
        except Exception as e:
            if logger:
                logger.error('[NFSe Nacional] Erro ao descompactar XML da consulta: %s' % str(e))

    xml_str = data.get("xml") or data.get("body")
    if not xml_str or not isinstance(xml_str, str):
        return None

    xml_str = xml_str.strip()
    if not xml_str:
        return None

    # Resposta já é o XML da NFSe (ou envelope contendo <NFSe>)
    try:
        root = ET.fromstring(xml_str.encode("utf-8"))
        if root.tag.endswith("NFSe") or root.tag == "NFSe":
            return xml_str
        ns = {"ns": root.nsmap.get(None)} if root.nsmap and None in root.nsmap else {}
        nfse_el = root.find(".//ns:NFSe", ns) if ns else root.find(".//{http://www.sped.fazenda.gov.br/nfse}NFSe")
        if nfse_el is None:
            nfse_el = root.find(".//NFSe")
        if nfse_el is not None:
            return ET.tostring(nfse_el, encoding="utf-8").decode("utf-8")
    except Exception as e:
        if logger:
            logger.error('[NFSe Nacional] Erro ao parsear XML da consulta: %s' % str(e))
        return None

    return xml_str


def baixar_danfse_pdf(chave_acesso: str, pfx_path: str, pfx_password: str, logger=None) -> Optional[str]:
    """
    Gera o DANFSe (PDF) localmente a partir do XML autorizado da NFS-e.

    Consulta a nota no Portal Nacional pela chave de acesso e renderiza o PDF
    com brazilfiscalreport (API ADN de download foi descontinuada — NT 008/2026).

    Args:
        chave_acesso: Chave de acesso da NFSe
        pfx_path: Caminho para o certificado .pfx
        pfx_password: Senha do certificado
        logger: Logger opcional para registro de eventos

    Returns:
        PDF em base64 ou None se não disponível
    """
    if logger:
        logger.info('[NFSe Nacional] Gerando DANFSe localmente - Chave: %s' % chave_acesso)

    try:
        data = consultar_nfse(chave_acesso, pfx_path, pfx_password, logger=logger)
        if not data:
            if logger:
                logger.error('[NFSe Nacional] Consulta da NFSe retornou vazio; DANFSe indisponível')
            return None

        xml_nfse = _extrair_xml_nfse_da_consulta(data, logger=logger)
        if not xml_nfse:
            if logger:
                logger.error('[NFSe Nacional] XML da NFSe não encontrado na consulta; DANFSe indisponível')
            return None

        if logger:
            logger.info('[NFSe Nacional] XML obtido (tamanho: %d caracteres); renderizando PDF' % len(xml_nfse))

        from brazilfiscalreport.danfse import Danfse

        danfse = Danfse(xml=xml_nfse)
        pdf_bytes = bytes(danfse.output())
        if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
            if logger:
                logger.error('[NFSe Nacional] Geração do DANFSe não produziu um PDF válido')
            return None

        pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
        if logger:
            logger.info('[NFSe Nacional] DANFSe gerado com sucesso (tamanho base64: %d caracteres)' % len(pdf_b64))
        return pdf_b64

    except Exception as e:
        if logger:
            logger.error('[NFSe Nacional] Erro ao gerar DANFSe: %s' % str(e))

    return None


def enviar_nfse_pkcs12(dps_b64: str, pfx_path: str, pfx_password: str, logger=None):
    """
    Envia uma DPS para o portal nacional.
    
    Args:
        dps_b64: DPS compactada e codificada em Base64
        pfx_path: Caminho para o certificado .pfx
        pfx_password: Senha do certificado
        logger: Logger opcional para registro de eventos
        
    Returns:
        Dicionário com resposta da API
    """
    if logger:
        logger.info('[NFSe Nacional] Enviando requisição HTTP POST para: %s' % URL_PRODUCAO)
        logger.info('[NFSe Nacional] Tamanho do payload (dps_b64): %d caracteres' % len(dps_b64))
    
    payload = {"dpsXmlGZipB64": dps_b64}
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    try:
        resp = pkcs12_post(
            URL_PRODUCAO,
            json=payload,
            headers=headers,
            pkcs12_filename=pfx_path,
            pkcs12_password=pfx_password,
            timeout=30,
            verify=True,
        )
        
        if logger:
            logger.info('[NFSe Nacional] Resposta HTTP recebida - Status: %s' % resp.status_code)
    except Exception as e:
        if logger:
            logger.error('[NFSe Nacional] Erro na requisição HTTP: %s' % str(e))
        raise

    xml_resp = resp.text or ""
    pdf_base64 = None
    xml_nfse = None
    id_dps = None
    chave_acesso = None

    # --- 1) tenta tratar como JSON (caso 201/400 estruturado) ---
    data = None
    try:
        data = resp.json()
        if logger:
            logger.info('[NFSe Nacional] Resposta parseada como JSON')
    except Exception:
        if logger:
            logger.info('[NFSe Nacional] Resposta não é JSON, tentando parsear como XML')
        data = None

    if isinstance(data, dict):
        id_dps = data.get("idDps") or data.get("idDPS")
        chave_acesso = data.get("chaveAcesso")
        
        # Verifica se há erros mesmo com status 200/201
        erros = data.get("erros") or []
        mensagem_erro = None
        if erros:
            # Formata mensagens de erro
            mensagens = []
            for erro in erros:
                if isinstance(erro, dict):
                    codigo = erro.get("Codigo", erro.get("codigo", ""))
                    descricao = erro.get("Descricao", erro.get("descricao", ""))
                    complemento = erro.get("Complemento", erro.get("complemento", ""))
                    if codigo and descricao:
                        msg = f"{codigo}: {descricao}"
                        if complemento:
                            msg += f" - {complemento}"
                        mensagens.append(msg)
                elif isinstance(erro, str):
                    mensagens.append(erro)
            if mensagens:
                mensagem_erro = " | ".join(mensagens)
                if logger:
                    logger.error('[NFSe Nacional] Erros encontrados na resposta: %s' % mensagem_erro)
        
        if logger:
            if id_dps:
                logger.info('[NFSe Nacional] ID DPS recebido: %s' % id_dps)
            if chave_acesso:
                logger.info('[NFSe Nacional] Chave de acesso recebida: %s' % chave_acesso)

        # XML da NFS-e vem em GZIP Base64
        gz_b64 = data.get("nfseXmlGZipB64") or data.get("nfseXmlGzipB64")
        if gz_b64:
            try:
                xml_nfse = gzip.decompress(base64.b64decode(gz_b64)).decode("utf-8", errors="replace")
                if logger:
                    logger.info('[NFSe Nacional] XML da NFSe extraído do GZIP (tamanho: %d caracteres)' % len(xml_nfse))
            except Exception as e:
                if logger:
                    logger.error('[NFSe Nacional] Erro ao descompactar XML da NFSe: %s' % str(e))

        # Se há erros, retorna erro mesmo com status 200/201
        if mensagem_erro:
            return {
                "status": resp.status_code,
                "body": xml_resp,
                "xml_nfse": xml_nfse,
                "pdf_base64": None,
                "id_dps": id_dps,
                "chave_acesso": chave_acesso,
                "erros": erros,
                "mensagem_erro": mensagem_erro,
            }

        # Se a nota foi aceita, gera o DANFSe localmente a partir do XML consultado
        if resp.status_code in (200, 201) and chave_acesso:
            if logger:
                logger.info('[NFSe Nacional] Gerando DANFSe localmente')
            pdf_base64 = baixar_danfse_pdf(chave_acesso, pfx_path, pfx_password, logger=logger)
            if pdf_base64 and logger:
                logger.info('[NFSe Nacional] DANFSe gerado com sucesso')

        return {
            "status": resp.status_code,
            "body": xml_resp,
            "xml_nfse": xml_nfse,
            "pdf_base64": pdf_base64,
            "id_dps": id_dps,
            "chave_acesso": chave_acesso,
        }

    # --- 2) fallback XML (resposta pura) ---
    try:
        root = ET.fromstring(xml_resp.encode("utf-8"))
        ns = {"ns": root.nsmap.get(None)} if None in root.nsmap else {}

        pdf_el = root.find(".//ns:pdfBase64", ns)
        nfse_el = root.find(".//ns:NFSe", ns)

        if pdf_el is not None and pdf_el.text:
            pdf_base64 = pdf_el.text.strip()
        if nfse_el is not None:
            xml_nfse = ET.tostring(nfse_el, encoding="utf-8").decode("utf-8")

        # Gera DANFSe localmente se tiver chave e ainda não houver PDF
        if chave_acesso and not pdf_base64:
            if logger:
                logger.info('[NFSe Nacional] Gerando DANFSe via fallback XML')
            pdf_base64 = baixar_danfse_pdf(chave_acesso, pfx_path, pfx_password, logger=logger)

    except Exception as e:
        if logger:
            logger.error('[NFSe Nacional] Erro ao parsear resposta XML: %s' % str(e))

    return {
        "status": resp.status_code,
        "body": xml_resp,
        "xml_nfse": xml_nfse,
        "pdf_base64": pdf_base64,
        "id_dps": id_dps,
        "chave_acesso": chave_acesso,
        "erros": [],
        "mensagem_erro": None,
    }


def enviar_cancelamento_pkcs12(chave_acesso: str, evento_b64_gzip: str, pfx_path: str, pfx_password: str, logger=None):
    """
    Envia um Pedido de Evento (Cancelamento) para a API Nacional.
    
    Args:
        chave_acesso: Chave de acesso da nota a ser cancelada
        evento_b64_gzip: XML do evento compactado e codificado em Base64
        pfx_path: Caminho para o certificado .pfx
        pfx_password: Senha do certificado
        logger: Logger opcional para registro de eventos
        
    Returns:
        Resposta da requisição
    """
    url = f"{URL_PRODUCAO}/{chave_acesso}/eventos"
    
    if logger:
        logger.info('[NFSe Nacional] Enviando cancelamento - URL: %s' % url)
        logger.info('[NFSe Nacional] Tamanho do payload (evento_b64_gzip): %d caracteres' % len(evento_b64_gzip))

    payload = {"pedidoRegistroEventoXmlGZipB64": evento_b64_gzip}
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    try:
        resp = pkcs12_post(
            url,
            json=payload,
            headers=headers,
            pkcs12_filename=pfx_path,
            pkcs12_password=pfx_password,
            timeout=30,
            verify=True,
        )
        
        if logger:
            logger.info('[NFSe Nacional] Resposta do cancelamento recebida - Status HTTP: %s' % resp.status_code)
            if hasattr(resp, 'text') and resp.text:
                logger.info('[NFSe Nacional] Resposta do cancelamento (primeiros 500 chars): %s' % resp.text[:500])

        return resp

    except RequestException as e:
        raise e


def consultar_nfse(chave_acesso: str, pfx_path: str, pfx_password: str, logger=None):
    """
    Consulta uma NFSe pelo portal nacional usando a chave de acesso.
    
    Args:
        chave_acesso: Chave de acesso da NFSe
        pfx_path: Caminho para o certificado .pfx
        pfx_password: Senha do certificado
        logger: Logger opcional para registro de eventos
        
    Returns:
        Dicionário com dados da NFSe ou None
    """
    url = f"{URL_PRODUCAO}/{chave_acesso}"
    
    if logger:
        logger.info('[NFSe Nacional] Consultando NFSe - URL: %s' % url)

    try:
        resp = pkcs12_get(
            url,
            pkcs12_filename=pfx_path,
            pkcs12_password=pfx_password,
            timeout=30,
            verify=True,
        )
        
        if logger:
            logger.info('[NFSe Nacional] Resposta da consulta recebida - Status HTTP: %s' % resp.status_code)

        if resp.status_code == 200:
            # Tenta parsear como JSON
            try:
                data = resp.json()
                if logger:
                    logger.info('[NFSe Nacional] Resposta parseada como JSON')
                return data
            except Exception:
                # Tenta parsear como XML
                try:
                    root = ET.fromstring(resp.content)
                    xml_str = ET.tostring(root, encoding="utf-8").decode("utf-8")
                    if logger:
                        logger.info('[NFSe Nacional] Resposta parseada como XML (tamanho: %d caracteres)' % len(xml_str))
                    return {"xml": xml_str}
                except Exception as e:
                    if logger:
                        logger.error('[NFSe Nacional] Erro ao parsear resposta: %s' % str(e))
                    return {"body": resp.text}
        else:
            if logger:
                logger.error('[NFSe Nacional] NFSe não encontrada - Status HTTP: %s' % resp.status_code)
            return None
    except Exception as e:
        if logger:
            logger.error('[NFSe Nacional] Erro ao consultar NFSe: %s' % str(e))
        return None

