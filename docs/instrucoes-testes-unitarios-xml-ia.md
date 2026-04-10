# Instruções para implementação de testes unitários (XML assinado, sem envio)

Este arquivo é destinado a uma IA ou desenvolvedor que vá **adicionar testes automatizados** que validam o **XML da DPS** gerado pelo package `nfse_nacional`, **sem** qualquer requisição ao ambiente nacional da Receita/SEFIN.

## Objetivo dos testes

- Garantir que o XML contém os elementos e valores esperados após as alterações (NBS, `tribFed`, `totTrib`, etc.).
- Garantir que a **assinatura digital** é aplicada quando há PFX válido (ou mock do assinador, se aplicável).
- Garantir que **nenhum** código de transmissão (`enviar_nfse_pkcs12`, `requests`, etc.) é invocado quando `skip_send=True`.

## Ferramentas recomendadas

- **pytest** como runner.
- **lxml.etree** para parse e XPath (o próprio package já depende de `lxml`).
- Opcional: certificado PFX de **homologação** ou fixture com arquivo em `tests/fixtures/` (não commitar segredos de produção).
- Opcional: **unittest.mock.patch** para interceptar `enviar_nfse_pkcs12` e falhar o teste se for chamado.

## Uso obrigatório de `skip_send`

Todo teste que apenas valida XML deve usar uma das formas:

```python
nfse = NFSeThema(pfx_file=str(pfx_path), pfx_passwd="...", skip_send=True)
# ...
result, errors = nfse.send_batch()
```

ou

```python
nfse = NFSeThema(pfx_file=str(pfx_path), pfx_passwd="...")
result, errors = nfse.send_batch(skip_send=True)
```

### Asserts mínimos no retorno

- `errors == {}`
- `result.get("skip_send") is True`
- `result.get("xml_dps_assinado")` é string não vazia
- `"<DPS" in result["xml_dps_assinado"]` e namespace `http://www.sped.fazenda.gov.br/nfse`
- Presença de assinatura: por exemplo `Signature` no XML (conforme o padrão gerado pelo `signer`)

### Garantir que o portal não foi chamado

```python
from unittest.mock import patch

@patch("nfse_nacional.client.enviar_nfse_pkcs12")
def test_nao_chama_envio_quando_skip_send(mock_enviar, ...):
    mock_enviar.side_effect = AssertionError("Não deve enviar ao portal")
    # ... montar NFSeThema(..., skip_send=True), add_rps, send_batch
    mock_enviar.assert_not_called()
```

Ajuste o caminho do patch conforme o import no projeto consumidor (pode ser `nfse_nacional.transmitter.enviar_nfse_pkcs12` se patchar na origem).

## Estrutura sugerida de arquivos

```
tests/
  conftest.py              # fixture: pfx_path, senha, rps_minimo()
  test_xml_skip_send.py    # fluxo send_batch(skip_send=True)
  test_xml_tribfed.py      # CST, tpRet, vPis, vCofins, vRet*
  test_xml_tottrib.py      # vTotTrib vs pTotTrib vs indTotTrib
  test_xml_cnbs.py         # cNBS opcional
  fixtures/
    README.md              # origem do PFX de homologação
```

## Casos de teste que devem existir

### 1. Baseline (sem tributação extra)

- `rps_fields` mínimo válido (prestador, tomador com endereço, serviço, RPS).
- XML contém `infDPS`, `serv/cServ/cTribNac`, `valores/trib/tribMun`, `totTrib` com `indTotTrib` ou `pTotTribSN` conforme regime — **sem** `tribFed` se nenhum campo novo foi passado.

### 2. Código NBS

- Preencher `nf.codigo_nbs` (com e sem máscara, ex. `1.1406.11.00`).
- Assert: `//cServ/cNBS` texto igual ao esperado normalizado (só dígitos).

### 3. `tribFed` / `piscofins`

- Com `nf.cst_pis_cofins`, `nf.tp_ret_pis_cofins_csll`, `nf.valor_pis`, `nf.valor_cofins`.
- Assert: `//tribFed/piscofins/CST`, `tpRetPisCofins`, `vPis`, `vCofins` com valores formatados em decimal (ex. `16.50`).

### 4. Retenções `vRetCP`, `vRetIRRF`, `vRetCSLL`

- Preencher `nf.valor_inss`, `nf.valor_ir`, `nf.v_ret_csll` (ou `nf.valor_csll`).
- Assert: elementos irmãos de `piscofins` em `tribFed` (ordem pode ser validada com lista de tags filhas).

### 5. CST 00 / 08 / 09

- Quando CST é `00`, `08` ou `09`, o package **não** deve incluir `vBCPisCofins`, `pAliqPis`, `vPis`, etc. (apenas `CST`, e `tpRet` se a regra do package permitir — alinhar com implementação atual).
- Teste de regressão: XML continua válido para o validador que vocês adotarem.

### 6. `totTrib` — percentuais (`pTotTrib`)

- Preencher os três `nf.aprox_tributos_pct_*`.
- Assert: `//totTrib/pTotTrib/pTotTribFed` (e Est/Mun) presentes; **não** deve existir `indTotTrib` no mesmo `totTrib` para esse cenário.

### 7. `totTrib` — valores (`vTotTrib`)

- Preencher os três `nf.aprox_tributos_valor_*`.
- Assert: `//totTrib/vTotTrib/vTotTribFed` etc.

### 8. Conflito modo valor vs percentual

- Preencher ambos os grupos e `nf.aprox_tributos_modo=valor` (ou `percentual`).
- Assert: apenas o bloco esperado aparece no XML.

### 9. `valor_iss` + flag aproximação municipal

- `nf.aprox_tributos_incluir_valor_iss` ativo e `nf.valor_iss` definido.
- Assert: `vTotTribMun` (ou o campo gerado) reflete o valor esperado.

### 10. Regressão `skip_send`

- Com `skip_send=False` em outro teste **opcional** (marcado `integration` ou `slow`), pode-se mockar `enviar_nfse_pkcs12` para retorno fake — **não** é obrigatório para a suíte “só XML”.

## Validação adicional (opcional)

- Carregar um **XSD** oficial da DPS, se disponível no repositório ou URL versionada, e chamar validação após parse do `xml_dps_assinado`. Falhas de XSD devem quebrar o teste com mensagem clara.
- Se XSD não estiver disponível, restringir-se a asserts por XPath e conteúdo.

## Dados sensíveis

- Não commitar PFX/senhas de produção.
- Usar variáveis de ambiente ou secrets do CI (`PFX_TEST_PATH`, `PFX_TEST_PASSWORD`).

## Critério de aceite da suíte

- Todos os testes acima passam localmente e no CI.
- Nenhum teste “só XML” realiza HTTP para domínios do governo.
- `enviar_nfse_pkcs12` permanece **não chamado** nos testes com `skip_send=True` (verificar com mock).
