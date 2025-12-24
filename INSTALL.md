# Como Instalar nfse-nacional

## Instalação Local (Desenvolvimento)

Para instalar a biblioteca localmente em modo de desenvolvimento:

```bash
cd nfse_nacional
pip install -e .
```

Ou diretamente do diretório:

```bash
pip install -e /caminho/para/nfse_nacional
```

## Instalação a partir de um repositório Git

Se a biblioteca estiver em um repositório Git:

```bash
pip install git+https://github.com/besoft/nfse-nacional.git
```

Para uma branch específica:

```bash
pip install git+https://github.com/besoft/nfse-nacional.git@main
```

## Instalação a partir de um arquivo wheel

Após gerar o wheel:

```bash
python setup.py bdist_wheel
pip install dist/nfse_nacional-1.0.0-py3-none-any.whl
```

## Instalação a partir de um arquivo tar.gz (source distribution)

Após gerar o source distribution:

```bash
python setup.py sdist
pip install dist/nfse-nacional-1.0.0.tar.gz
```

## Uso após instalação

Após a instalação, você pode importar a biblioteca normalmente:

```python
from nfse_nacional import NFSeThema
from nfse_nacional.xml import load_fromstring, dump_tostring
```

## Dependências

A biblioteca requer:
- Python >= 3.8
- lxml >= 4.6.0
- requests-pkcs12 >= 1.27
- cryptography >= 3.4.0

Essas dependências serão instaladas automaticamente ao instalar o pacote.

