"""
Função para assinatura de XML no padrão nacional de NFSe.
"""

import base64
import hashlib
from lxml import etree as ET
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from typing import Union

NS_NFSE = "http://www.sped.fazenda.gov.br/nfse"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"


def assinar_xml(
        xml_input: Union[str, bytes],
        pfx_path: str,
        pfx_password: str,
        tag_to_sign: str = "infDPS",
        logger=None
) -> str:
    """
    Assina a tag especificada do XML (formato Enveloped),
    conforme padrão NFS-e Nacional (Sefin Nacional).
    
    Args:
        xml_input: XML como string ou bytes
        pfx_path: Caminho para o arquivo .pfx do certificado
        pfx_password: Senha do certificado
        tag_to_sign: Tag a ser assinada (padrão: "infDPS" ou "infPedReg")
        logger: Logger opcional para registro de eventos
        
    Returns:
        XML assinado como string
    """
    if logger:
        logger.info('[NFSe Nacional] Iniciando assinatura de XML - Tag: %s' % tag_to_sign)
    
    # === 1) Carrega chave privada e certificado do PFX ===
    if logger:
        logger.info('[NFSe Nacional] Carregando certificado PFX: %s' % pfx_path)
    
    with open(pfx_path, "rb") as f:
        pfx_data = f.read()
    private_key, certificate, additional_certs = pkcs12.load_key_and_certificates(
        pfx_data, pfx_password.encode() if pfx_password else None
    )

    if private_key is None or certificate is None:
        error_msg = "PFX inválido: sem chave privada ou certificado."
        if logger:
            logger.error('[NFSe Nacional] %s' % error_msg)
        raise ValueError(error_msg)
    
    if logger:
        logger.info('[NFSe Nacional] Certificado carregado com sucesso')

    cert_b64 = base64.b64encode(certificate.public_bytes(Encoding.DER)).decode()

    # === 2) Carrega o XML ===
    if isinstance(xml_input, bytes):
        root = ET.fromstring(xml_input)
    else:
        root = ET.fromstring(xml_input.encode("utf-8"))

    ns_nfse = {"ns": NS_NFSE}

    # === 3) Localiza o elemento a ser assinado ===
    if logger:
        logger.info('[NFSe Nacional] Localizando elemento para assinatura: %s' % tag_to_sign)
    
    target_element = root.find(f"ns:{tag_to_sign}", ns_nfse)
    if target_element is None:
        error_msg = f"Elemento <{tag_to_sign}> não encontrado."
        if logger:
            logger.error('[NFSe Nacional] %s' % error_msg)
        raise ValueError(error_msg)

    inf_id = target_element.get("Id")
    if not inf_id:
        error_msg = f"Atributo Id ausente em <{tag_to_sign}>."
        if logger:
            logger.error('[NFSe Nacional] %s' % error_msg)
        raise ValueError(error_msg)
    
    if logger:
        logger.info('[NFSe Nacional] Elemento encontrado com ID: %s' % inf_id)

    # === 4) Canonicaliza e calcula o DigestValue ===
    if logger:
        logger.info('[NFSe Nacional] Canonicalizando e calculando digest')
    
    target_bytes = ET.tostring(target_element, encoding="utf-8")
    target_c14n = ET.tostring(
        ET.fromstring(target_bytes),
        method="c14n",
        exclusive=False,
        with_comments=False,
    )

    digest = hashlib.sha1(target_c14n).digest()
    digest_b64 = base64.b64encode(digest).decode("utf-8")
    
    if logger:
        logger.info('[NFSe Nacional] Digest calculado: %s' % digest_b64[:20] + '...')

    # === 5) Monta a estrutura de assinatura ===
    nsmap = {None: NS_DS}
    Signature = ET.Element("{%s}Signature" % NS_DS, nsmap=nsmap)

    SignedInfo = ET.SubElement(Signature, "{%s}SignedInfo" % NS_DS)
    ET.SubElement(
        SignedInfo,
        "{%s}CanonicalizationMethod" % NS_DS,
        Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315",
    )
    ET.SubElement(
        SignedInfo,
        "{%s}SignatureMethod" % NS_DS,
        Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1",
    )

    Reference = ET.SubElement(SignedInfo, "{%s}Reference" % NS_DS, URI=f"#{inf_id}")
    Transforms = ET.SubElement(Reference, "{%s}Transforms" % NS_DS)
    ET.SubElement(
        Transforms,
        "{%s}Transform" % NS_DS,
        Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature",
    )
    ET.SubElement(
        Transforms,
        "{%s}Transform" % NS_DS,
        Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315",
    )
    ET.SubElement(
        Reference,
        "{%s}DigestMethod" % NS_DS,
        Algorithm="http://www.w3.org/2000/09/xmldsig#sha1",
    )
    ET.SubElement(Reference, "{%s}DigestValue" % NS_DS).text = digest_b64

    # === 6) Canonicaliza SignedInfo e assina ===
    if logger:
        logger.info('[NFSe Nacional] Canonicalizando SignedInfo e gerando assinatura digital')
    
    signedinfo_bytes = ET.tostring(SignedInfo, encoding="utf-8")
    signedinfo_c14n_element = ET.fromstring(signedinfo_bytes)
    c14n_signed = ET.tostring(
        signedinfo_c14n_element, method="c14n", exclusive=False, with_comments=False
    )

    signature_raw = private_key.sign(c14n_signed, padding.PKCS1v15(), hashes.SHA1())
    signature_b64 = base64.b64encode(signature_raw).decode("utf-8")
    
    if logger:
        logger.info('[NFSe Nacional] Assinatura digital gerada: %s...' % signature_b64[:20])

    # === 7) Insere SignatureValue e KeyInfo ===
    ET.SubElement(Signature, "{%s}SignatureValue" % NS_DS).text = signature_b64

    KeyInfo = ET.SubElement(Signature, "{%s}KeyInfo" % NS_DS)
    X509Data = ET.SubElement(KeyInfo, "{%s}X509Data" % NS_DS)
    ET.SubElement(X509Data, "{%s}X509Certificate" % NS_DS).text = cert_b64

    # === 8) Adiciona <ds:Signature> após a tag assinada ===
    if logger:
        logger.info('[NFSe Nacional] Inserindo assinatura no XML')
    
    target_element.addnext(Signature)

    # === 9) Retorna XML final ===
    xml_signed = ET.tostring(root, pretty_print=False, encoding="utf-8", xml_declaration=True)
    xml_final = xml_signed.decode("utf-8")
    
    if logger:
        logger.info('[NFSe Nacional] XML assinado com sucesso (tamanho final: %d caracteres)' % len(xml_final))
    
    return xml_final

