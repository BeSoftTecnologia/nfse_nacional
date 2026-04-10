# Integração do package `nfse_nacional` nos projetos consumidores

Este documento descreve como projetos que já usam (ou passarão a usar) o package devem configurar os novos campos de tributação federal, totais aproximados, código NBS e o **modo sem envio** ao portal (somente XML assinado).

## Dependência e versão

- Fixe a versão do package no `requirements.txt` / `pyproject.toml` após publicar a release que contém estas alterações.
- Garanta que o import continue sendo o mesmo (`from nfse_nacional import NFSeThema` ou equivalente conforme o `package_dir` da instalação).

## Modo apenas gerar XML assinado (`skip_send`)

Útil para **testes automatizados**, homologação de leiaute e validação do XML **sem** chamada HTTP ao ambiente nacional.

### Construtor

```python
nfse = NFSeThema(
    pfx_file="/caminho/certificado.pfx",
    pfx_passwd="senha",
    skip_send=True,  # padrão do envio: não transmitir
)
```

### Por envio (`send_batch`)

```python
result, errors = nfse.send_batch(skip_send=True)
```

- Se `skip_send` for omitido em `send_batch`, usa o valor definido no construtor (`self.skip_send`).
- Com `skip_send=True`, o fluxo **assina** a DPS com o certificado (mesma regra de antes: PFX obrigatório), **não** chama o portal.

### Retorno quando `skip_send=True`

| Chave | Descrição |
|--------|-----------|
| `result['xml_dps_assinado']` | String XML da DPS **assinada** (uso principal). |
| `result['xml_enviado']` | Mesmo conteúdo (compatibilidade com código que já lia essa chave). |
| `result['dps_xml_gzip_b64']` | Payload GZip + Base64 que seria enviado ao webservice (para inspeção ou testes locais). |
| `result['skip_send']` | `True`. |
| `result['ws.response']` | XML sintético com `Protocolo` = `SKIP_SEND` (não é resposta da Receita). |
| `errors` | Dicionário vazio em caso de sucesso. |

**Importante:** não há `chave_acesso`, `id_dps` nem `xml_nfse` nesse modo, pois não houve transmissão.

## Campos opcionais em `rps_fields`

Todos são opcionais; inclua apenas o que o seu cenário fiscal exige.

### NBS

- `nf.codigo_nbs` — normalizado e enviado como `cServ/cNBS` quando informado.

### PIS/COFINS (grupo `tribFed/piscofins`)

- `nf.cst_pis_cofins` — CST (ex.: `01` ou texto com prefixo `01 - ...`).
- `nf.tp_ret_pis_cofins_csll` — um dígito `0`–`9` (portal / NT007).
- `nf.valor_pis`, `nf.valor_cofins` — valores monetários em `vPis` / `vCofins` (apuração própria; ver NT007).
- Opcionais: `nf.v_bc_pis_cofins`, `nf.p_aliquota_pis`, `nf.p_aliquota_cofins`.

### Retenções em `tribFed`

- `nf.valor_inss` → `vRetCP`
- `nf.valor_ir` ou `nf.valor_IR` → `vRetIRRF`
- `nf.v_ret_csll` (prioridade) ou `nf.valor_csll` → `vRetCSLL`  
  Conforme a NT007, `vRetCSLL` pode ser a **soma** das retenções PIS+COFINS+CSLL; o sistema emissor deve calcular e enviar o valor correto.

### Valor aproximado dos tributos (`totTrib`)

Use **ou** percentuais **ou** valores em R$ (não misture sem definir modo).

- Valores: `nf.aprox_tributos_valor_federal`, `nf.aprox_tributos_valor_estadual`, `nf.aprox_tributos_valor_municipal`
- Percentuais: `nf.aprox_tributos_pct_federal`, `nf.aprox_tributos_pct_estadual`, `nf.aprox_tributos_pct_municipal`
- `nf.aprox_tributos_modo`: `valor` ou `percentual` para forçar um dos blocos se ambos estiverem preenchidos por engano.
- `nf.aprox_tributos_incluir_valor_iss` = `1` / `S` / `sim` / `true`: usa `nf.valor_iss` como aproximação **municipal em R$** quando o campo municipal explícito não foi informado.

### ISS

- `nf.valor_iss` **não** gera tag isolada de “valor ISS” na DPS; alíquota e retenção seguem `nf.aliquota` e `nf.iss_retido`. Para aproximação municipal, use os campos de `totTrib` ou o flag com `valor_iss` acima.

## Fluxo sugerido no projeto consumidor

1. Montar `rps_fields` como hoje (prestador, tomador, serviço, RPS, etc.).
2. Acrescentar os novos `nf.*` conforme cadastro fiscal / tela do portal nacional.
3. `add_rps(rps_fields)` — adiciona ao lote (no padrão nacional o envio efetivo é por documento).
4. Em **produção**: `send_batch()` com `skip_send=False` (padrão).
5. Em **CI / testes**: instanciar com `skip_send=True` ou chamar `send_batch(skip_send=True)`, validar `result['xml_dps_assinado']` com asserts ou XSD (ver documento de testes).

## Erros comuns a evitar

- Informar retenção de PIS/COFINS nos mesmos campos de apuração própria (NT007).
- `tpRetPisCofins` incompatível com os valores declarados.
- Preencher simultaneamente percentuais e valores de `totTrib` sem `nf.aprox_tributos_modo`.
- Esperar `chave_acesso` quando `skip_send=True`.

## Referências de leiaute

- Anexo I – DPS (planilhas oficiais no portal NFSe).
- NT007 – PIS/COFINS/CSLL (documentação TecnoSpeed / SERPRO).
