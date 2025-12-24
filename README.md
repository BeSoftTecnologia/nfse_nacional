# NFSe Nacional - Implementação para Portal Nacional

Este módulo substitui o package `nfsepmpf` mantendo compatibilidade com a interface existente, mas utilizando o novo padrão do Portal Nacional de NFSe.

## Estrutura

- `client.py`: Classe principal `NFSeThema` compatível com a interface antiga
- `builder.py`: Funções para construir XML no padrão nacional
- `signer.py`: Função para assinar XML com certificado digital
- `transmitter.py`: Funções para comunicação com a API do portal nacional
- `utils.py`: Funções utilitárias (sanitize_document, to_float, gerar_dpsXmlGZipB64)
- `xml.py`: Funções auxiliares de XML para compatibilidade

## Uso

Para usar no lugar do `nfsepmpf`, basta alterar os imports:

```python
# Antes:
from nfsepmpf.xml import load_fromstring, dump_tostring
from nfsepmpf.client import NFSeThema

# Depois:
from nfse.nfse_nacional.xml import load_fromstring, dump_tostring
from nfse.nfse_nacional.client import NFSeThema
```

## Diferenças Importantes do Portal Nacional

### 1. Chave de Acesso (substitui Protocolo)

**IMPORTANTE**: O Portal Nacional **NÃO retorna "protocolo"** como no sistema antigo. Ele retorna:
- `chaveAcesso`: Chave de acesso única da NFSe (identificador principal)
- `idDps`: ID da DPS enviada
- `nfseXmlGZipB64`: XML da NFSe compactado em Base64

A **chave de acesso** é essencial para:
- Consultar uma NFSe
- Cancelar uma NFSe
- Baixar o DANFSe (PDF)

**Armazenamento**: A chave de acesso é armazenada no campo `protocolo_lote` do modelo `NFSe` para compatibilidade com o banco existente. Este campo agora armazena a chave de acesso, não mais um protocolo numérico.

### 2. Fluxo de Emissão

1. **Envio**: O método `send_batch()` envia a DPS para o Portal Nacional
2. **Resposta**: O portal retorna JSON com:
   - `chaveAcesso`: Chave de acesso (armazenada em `protocolo_lote`)
   - `idDps`: ID da DPS
   - `nfseXmlGZipB64`: XML da NFSe (descompactado e armazenado)
3. **Armazenamento**: 
   - `protocolo_lote` = `chaveAcesso`
   - `arquivoxml` = XML da NFSe descompactado

### 3. Fluxo de Consulta

Para consultar uma NFSe, é necessário ter a **chave de acesso** (armazenada em `protocolo_lote`).

O método `get_batch_status()` aceita:
- `lote.protocolo`: Chave de acesso (armazenada em `protocolo_lote`)
- `chave_acesso`: Chave de acesso direta (alternativa)

**Nota**: No novo padrão não há "consulta de lote", apenas consulta individual por chave de acesso.

### 4. Fluxo de Cancelamento

Para cancelar uma NFSe, é necessário:
- `nf.prestador.documento`: CNPJ do prestador
- `nf.chave_acesso` ou `chave_acesso`: Chave de acesso da nota (obtida de `protocolo_lote`)
- `nf.justificativa` ou `justificativa`: Justificativa do cancelamento

**Compatibilidade**: O campo `nf.cancela.id` pode ser usado como chave de acesso se `chave_acesso` não for fornecido.

### 5. Mudanças no Código

O código foi ajustado para:
- Usar `chave_acesso` diretamente quando disponível (prioridade)
- Fallback para parse de XML quando necessário (compatibilidade)
- Armazenar `chave_acesso` em `protocolo_lote` (compatibilidade com banco)

## Dependências

Este módulo requer:
- `lxml`: Para manipulação de XML
- `cryptography`: Para assinatura digital
- `requests-pkcs12`: Para requisições HTTPS com certificado PKCS12

## Notas

- O sistema mantém compatibilidade com o formato de dados antigo (`rps_fields`)
- As respostas são convertidas para o formato XML esperado pelo sistema antigo
- No novo padrão não há conceito de "lote", mas a interface mantém compatibilidade


# Análise de Campos: nfsepmpf vs Novo XML Nacional

## Campos que NÃO estão sendo enviados no novo XML

### Campos do RPS
1. **rps.tipo** - Tipo do RPS (1, 2, 3)
2. **rps.status** - Status do RPS (normalmente '1')
3. **rps.substituido.numero** - Número do RPS substituído (opcional)
4. **rps.substituido.serie** - Série do RPS substituído (opcional)
5. **rps.substituido.tipo** - Tipo do RPS substituído (opcional)

### Campos da Nota Fiscal
6. **nf.natureza_operacao** - Natureza da operação
7. **nf.incentivo_fiscal** - Indicador de incentivador cultural 
8. **nf.valor_deducoes** - Valor das deduções (opcional)
9. **nf.valor_pis** - Valor do PIS (opcional)
10. **nf.valor_cofins** - Valor do COFINS (opcional)
11. **nf.valor_inss** - Valor do INSS (opcional)
12. **nf.valor_IR** - Valor do IR (opcional)
13. **nf.valor_csll** - Valor do CSLL (opcional)
14. **nf.valor_iss** - Valor do ISS (opcional)
15. **nf.valor_outros** - Outras retenções (opcional)
16. **nf.base_calculo** - Base de cálculo do ISS
17. **nf.total_nota_liquido** - Valor líquido da nota (opcional)
18. **nf.valor_iss_retido** - Valor do ISS retido (opcional)
19. **nf.desconto_condicionado** - Desconto condicionado (opcional)
20. **nf.desconto_incondicionado** - Desconto incondicionado (opcional)
21. **nf.codigo_cnae** - Código CNAE (opcional)
22. **nf.codigo_tributacao_municipio** - Código de tributação municipal (opcional)

### Campos do Intermediário
23. **nf.intermediario.razao_social** - Razão social do intermediário (opcional)
24. **nf.intermediario.documento** - CPF/CNPJ do intermediário (opcional)
25. **nf.intermediario.inscricao_municipal** - Inscrição municipal do intermediário (opcional)

### Campos de Construção Civil
26. **nf.construcao_civil.codigo_obra** - Código da obra (opcional)
27. **nf.construcao_civil.art** - ART da obra (opcional)

### Campos do Tomador
28. **nf.tomador.contato.telefone** - Telefone do tomador (opcional)
29. **nf.tomador.contato.email** - Email do tomador (opcional)
30. **nf.tomador.inscricao_estadual** - Inscrição estadual do tomador (convertido mas não enviado no XML)

### Campos do Prestador
31. **nf.prestador.email** - Email do prestador (convertido e enviado no XML, mas NÃO está sendo passado no `nf_data` do `view_nfse.py`)

## Campos que ESTÃO sendo usados (convertidos/mapeados)

### RPS
- ✅ rps.numero → numero_dps
- ✅ rps.serie → serie_dps
- ✅ rps.data.emissao → competencia e data_emissao

### Prestador
- ✅ nf.prestador.documento → emitter.cnpj/cpf
- ✅ nf.prestador.inscricao_municipal → emitter.inscricaoMunicipal
- ✅ nf.codigo_municipio → emitter.codigoIbge
- ✅ nf.optante_simples → emitter.regimeTributacao (convertido)
- ✅ nf.regime_especial_tributacao → emitter.regimeTributacao (convertido)

### Tomador
- ✅ nf.tomador.documento → client.cnpj/cpf
- ✅ nf.tomador.razao_social → client.nome
- ✅ nf.tomador.inscricao_municipal → client.inscricaoMunicipal
- ✅ nf.tomador.logradouro → client.logradouro
- ✅ nf.tomador.numero_logradouro → client.numero
- ✅ nf.tomador.complemento → client.complemento
- ✅ nf.tomador.bairro → client.bairro
- ✅ nf.tomador.codigo_municipio → client.codigoIbge
- ✅ nf.tomador.uf → client.uf
- ✅ nf.tomador.cep → client.cep

### Serviço
- ✅ nf.codigo_servico → service.cTribNac (normalizado para 6 dígitos)
- ✅ nf.discriminacao → service.descricao
- ✅ nf.total_servicos → service.valor
- ✅ nf.aliquota → service.aliquota
- ✅ nf.iss_retido → service.issRetido (convertido de 1/2 para S/N)

## Observações

1. **nf.tomador.inscricao_estadual**: O campo é convertido e armazenado em `client['inscricaoEstadual']`, mas **NÃO está sendo enviado no XML** gerado pelo `build_nfse_xml()`. O código do builder não inclui esse campo no XML do tomador.

2. **nf.prestador.email**: O campo é convertido e armazenado em `emitter['email']`, e o código do `build_nfse_xml()` **envia no XML** (linhas 177-178), mas **NÃO está sendo passado no `nf_data`** do `view_nfse.py` (linha 227-267). Portanto, mesmo que o código suporte, o valor nunca chega porque não é enviado na requisição.

3. **nf.regime_especial_tributacao**: É usado apenas para determinar se é MEI, mas o valor em si não é enviado diretamente.

4. **Campos de valores tributários**: Vários campos de valores (PIS, COFINS, INSS, IR, CSLL, etc.) não são enviados no novo padrão, que foca apenas no valor do serviço e alíquota.

5. **Intermediário e Construção Civil**: Esses campos não são suportados no novo padrão nacional.

6. **Contato do tomador**: Telefone e email do tomador não são enviados no novo padrão.

7. **Descontos**: Descontos condicionados e incondicionados não são enviados no novo padrão.

8. **Base de cálculo**: A base de cálculo não é enviada explicitamente, apenas o valor do serviço e a alíquota.


