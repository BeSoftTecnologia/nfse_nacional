"""
Setup script para nfse_nacional - Biblioteca para comunicação com o Portal Nacional de NFSe.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Lê o README para usar como long_description
readme_file = Path(__file__).parent / "README.md"
long_description = ""
if readme_file.exists():
    long_description = readme_file.read_text(encoding="utf-8")

setup(
    name="nfse-nacional",
    version="1.0.0",
    description="Biblioteca Python para comunicação com o Portal Nacional de NFSe",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="BeSoft Tecnologia",
    author_email="contato@besoft.com.br",
    url="https://repo.besoft.com.br/BeSoft/nfse_nacional",
    # O pacote está na pasta atual (nfse_nacional)
    # Quando instalado, será importado como: from nfse_nacional import NFSeThema
    packages=["nfse_nacional"],
    package_dir={"nfse_nacional": "."},
    python_requires=">=3.8",
    install_requires=[
        "lxml>=4.6.0",
        "requests-pkcs12>=1.27",
        "cryptography>=3.4.0",
    ],
    # Exclui explicitamente dependências não utilizadas que podem causar conflitos
    # O google-api-python-client não é usado neste pacote
    dependency_links=[],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=22.0.0",
            "flake8>=5.0.0",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Office/Business :: Financial :: Accounting",
    ],
    keywords="nfse nota-fiscal servico portal-nacional",
    include_package_data=True,
    zip_safe=False,
)

