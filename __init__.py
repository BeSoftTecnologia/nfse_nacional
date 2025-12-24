"""
Módulo para comunicação com o Portal Nacional de NFSe.
Substitui o package nfsepmpf mantendo compatibilidade com a interface existente.
"""

from .client import NFSeThema
from .xml import load_fromstring, dump_tostring

__all__ = ['NFSeThema', 'load_fromstring', 'dump_tostring']

