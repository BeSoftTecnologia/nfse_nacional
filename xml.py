"""
Funções auxiliares para manipulação de XML.
Mantém compatibilidade com a interface do nfsepmpf.
"""

from lxml import etree as ET
from typing import Union


def load_fromstring(xml_string: Union[bytes, str]):
    """
    Carrega XML a partir de uma string.
    
    Args:
        xml_string: XML como string ou bytes
        
    Returns:
        ElementTree do lxml
    """
    if isinstance(xml_string, bytes):
        return ET.fromstring(xml_string)
    else:
        return ET.fromstring(xml_string.encode("utf-8"))


def dump_tostring(element, xml_declaration=True, pretty_print=False):
    """
    Converte um elemento XML para string.
    
    Args:
        element: ElementTree ou Element do lxml
        xml_declaration: Incluir declaração XML
        pretty_print: Formatar com indentação
        
    Returns:
        XML como string
    """
    if isinstance(element, ET._ElementTree):
        return ET.tostring(
            element,
            encoding="utf-8",
            xml_declaration=xml_declaration,
            pretty_print=pretty_print
        ).decode("utf-8")
    elif isinstance(element, ET._Element):
        return ET.tostring(
            element,
            encoding="utf-8",
            xml_declaration=xml_declaration,
            pretty_print=pretty_print
        ).decode("utf-8")
    else:
        # Se for string, retorna como está
        return str(element)

