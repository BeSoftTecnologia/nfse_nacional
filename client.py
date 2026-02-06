"""
Classe principal para comunicação com o Portal Nacional de NFSe.
Mantém compatibilidade com a interface do nfsepmpf.
"""

import os
from datetime import datetime
from lxml import etree as ET
from .builder import build_nfse_xml, build_cancelamento_xml
from .signer import assinar_xml
from .transmitter import enviar_nfse_pkcs12, enviar_cancelamento_pkcs12, consultar_nfse, URL_PRODUCAO
from .utils import sanitize_document, to_float, gerar_dpsXmlGZipB64, ctn_to_6digits, remove_accents


class NFSeThema:
    """
    Classe para envio de NFS-e no novo padrão nacional.
    Recebe os mesmos dados em rps_fields que a versão antiga,
    mas gera XML no novo padrão usando as funções do backend.
    """

    def __init__(self, pfx_file=None, pfx_passwd=None, target='production', logger=None):
        """
        Inicializa a classe NFSeThema.
        
        Args:
            pfx_file: Caminho para o arquivo .pfx do certificado
            pfx_passwd: Senha do certificado
            target: 'production' ou 'test' (não usado no novo padrão, mas mantido para compatibilidade)
            logger: Logger opcional para registro de eventos
        """
        self.pfx_file = pfx_file
        self.pfx_passwd = pfx_passwd
        self.target = target
        self.rps_batch = []
        self.cancel_batch = []
        self.logger = logger

    def clear_rps_batch(self):
        """Limpa o lote de RPS."""
        self.rps_batch = []

    def clear_cancel_batch(self):
        """Limpa o lote de cancelamentos."""
        self.cancel_batch = []

    def _converter_rps_fields_para_novo_formato(self, rps_fields):
        """
        Converte os campos rps_fields (formato antigo) para o formato esperado
        pelas funções do backend (emitter, client, service).
        """
        # --- Emissor (Prestador) ---
        doc_prest = sanitize_document(rps_fields.get('nf.prestador.documento', ''))
        emitter = {
            'cnpj' if len(doc_prest) == 14 else 'cpf': doc_prest,
            'codigoIbge': str(rps_fields.get('nf.codigo_municipio', '')).zfill(7),
            'email': rps_fields.get('nf.prestador.email', ''),
        }
        
        # Regime tributário - mapeia do formato antigo para o novo
        regime_antigo = (rps_fields.get('nf.regime_especial_tributacao') or '').strip().lower()
        optante_simples = str(rps_fields.get('nf.optante_simples', '2')).strip()
        
        # Verifica se é MEI
        if 'mei' in regime_antigo:
            emitter['regimeTributacao'] = 'MEI'
        # Se optante_simples == '1', é Simples Nacional
        elif optante_simples == '1':
            emitter['regimeTributacao'] = 'Simples Nacional'
        # Caso contrário, não é optante
        else:
            emitter['regimeTributacao'] = 'Não Optante'
        
        # Inscrição municipal (se houver)
        if rps_fields.get('nf.prestador.inscricao_municipal'):
            emitter['inscricaoMunicipal'] = rps_fields.get('nf.prestador.inscricao_municipal')

        # --- Cliente (Tomador) ---
        doc_toma = sanitize_document(rps_fields.get('nf.tomador.documento', ''))
        
        # Se não tiver documento, pode ser não identificado
        if not doc_toma:
            client = {'nao_identificado': True}
        else:
            client = {
                'cnpj' if len(doc_toma) == 14 else 'cpf': doc_toma,
                'nome': remove_accents(rps_fields.get('nf.tomador.razao_social', '') or '')[:115],
            }
            
            # Inscrições
            if rps_fields.get('nf.tomador.inscricao_municipal'):
                client['inscricaoMunicipal'] = rps_fields.get('nf.tomador.inscricao_municipal')
            if rps_fields.get('nf.tomador.inscricao_estadual'):
                client['inscricaoEstadual'] = rps_fields.get('nf.tomador.inscricao_estadual')
            
            # Endereço (só adiciona se tiver IBGE válido - 7 dígitos)
            # Se não tiver cid_ibge, não envia endereço do tomador
            codigo_municipio_raw = rps_fields.get('nf.tomador.codigo_municipio', '').strip()
            if codigo_municipio_raw and len(codigo_municipio_raw) >= 7:
                # Garante que tem pelo menos 7 dígitos
                codigo_municipio_clean = ''.join(c for c in codigo_municipio_raw if c.isdigit())
                if len(codigo_municipio_clean) >= 7:
                    client['codigoIbge'] = codigo_municipio_clean.zfill(7)
                    
                    # Só adiciona outros campos de endereço se tiver IBGE válido
                    cep_raw = sanitize_document(rps_fields.get('nf.tomador.cep', ''))
                    if cep_raw and len(cep_raw) == 8:
                        client['cep'] = cep_raw
                    
                    if rps_fields.get('nf.tomador.logradouro'):
                        client['logradouro'] = remove_accents(rps_fields.get('nf.tomador.logradouro', '') or '')[:125]
                        client['numero'] = rps_fields.get('nf.tomador.numero_logradouro', 'S/N')
                        if rps_fields.get('nf.tomador.complemento'):
                            client['complemento'] = rps_fields.get('nf.tomador.complemento', '')[:60]
                        client['bairro'] = remove_accents(rps_fields.get('nf.tomador.bairro', 'NAO INFORMADO'))[:60]
                        if rps_fields.get('nf.tomador.uf'):
                            client['uf'] = rps_fields.get('nf.tomador.uf', '')[:2]

        # --- Serviço ---
        # Normaliza código de serviço para 6 dígitos (padrão nacional)
        cod_servico_raw = rps_fields.get('nf.codigo_servico', '')
        cod_servico_normalizado = ctn_to_6digits(cod_servico_raw) or "010101"  # Fallback para código padrão
        
        service = {
            'descricao': remove_accents(rps_fields.get('nf.discriminacao', '') or '')[:1000],
            'valor': to_float(rps_fields.get('nf.total_servicos', 0)) or 0.0,
            'cTribNac': cod_servico_normalizado,
        }

        service['descricao'] = service['descricao'].replace('\r\n', ', ').replace(', ,', ',')
        
        # Alíquota - converte de porcentagem para decimal se necessário
        aliq_raw = rps_fields.get('nf.aliquota', '')
        if aliq_raw:
            aliq_val = to_float(aliq_raw)
            if aliq_val and aliq_val > 1:
                aliq_val = aliq_val / 100.0
            service['aliquota'] = aliq_val if aliq_val else None
        else:
            service['aliquota'] = None
        
        # ISS Retido - converte formato antigo (1/2) para novo (S/N)
        iss_retido_antigo = rps_fields.get('nf.iss_retido', '2')
        service['issRetido'] = 'S' if str(iss_retido_antigo).strip() == '1' else 'N'

        # --- DPS (número e série) ---
        numero_dps = int(rps_fields.get('rps.numero', 1))
        serie_dps = rps_fields.get('rps.serie', '1')
        
        # --- Competência - converte data de emissão para formato AAAA-MM-DD ---
        data_emissao_str = rps_fields.get('rps.data.emissao', '')
        if data_emissao_str:
            try:
                # Remove timezone e frações de segundo se houver
                data_clean = data_emissao_str.split('.')[0].split('+')[0].split('Z')[0].strip()
                # Tenta vários formatos
                competencia = None
                for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y']:
                    try:
                        dt = datetime.strptime(data_clean, fmt)
                        competencia = dt.strftime('%Y-%m-%d')
                        break
                    except:
                        continue
                if not competencia:
                    competencia = datetime.now().strftime('%Y-%m-%d')
            except:
                competencia = datetime.now().strftime('%Y-%m-%d')
        else:
            competencia = datetime.now().strftime('%Y-%m-%d')

        return {
            'emitter': emitter,
            'client': client,
            'service': service,
            'numero_dps': numero_dps,
            'serie_dps': serie_dps,
            'competencia': competencia,
            'data_emissao': data_emissao_str if data_emissao_str else None,
        }

    def add_rps(self, rps_fields):
        """
        Adiciona um RPS ao lote.
        
        Args:
            rps_fields: Dicionário com os campos do RPS no formato antigo
            
        Returns:
            ElementTree: XML da DPS gerada (sem assinatura ainda) - compatível com interface antiga
        """
        if self.logger:
            self.logger.info('[NFSe Nacional] Iniciando geração de XML da DPS')
            self.logger.info('[NFSe Nacional] Número RPS: %s, Série: %s' % (
                rps_fields.get('rps.numero', 'N/A'),
                rps_fields.get('rps.serie', 'N/A')
            ))
        
        # Converte para o novo formato
        dados = self._converter_rps_fields_para_novo_formato(rps_fields)
        
        if self.logger:
            self.logger.info('[NFSe Nacional] Dados convertidos - Prestador: %s, Tomador: %s, Valor: %s' % (
                dados['emitter'].get('cnpj') or dados['emitter'].get('cpf', 'N/A'),
                dados['client'].get('cnpj') or dados['client'].get('cpf', 'N/A') if not dados['client'].get('nao_identificado') else 'Não identificado',
                dados['service'].get('valor', 0)
            ))
        
        # Gera o XML usando a função do backend
        xml_dps = build_nfse_xml(
            emitter=dados['emitter'],
            client=dados['client'],
            service=dados['service'],
            numero_dps=dados['numero_dps'],
            serie_dps=dados['serie_dps'],
            competencia=dados['competencia'],
            data_emissao=dados['data_emissao'],
        )
        
        if self.logger:
            self.logger.info('[NFSe Nacional] XML da DPS gerado com sucesso (tamanho: %d caracteres)' % len(xml_dps))
        
        # Armazena o XML (ainda sem assinatura) no lote
        self.rps_batch.append({
            'xml': xml_dps,
            'rps_fields': rps_fields,
            'dados': dados,
        })
        
        # Retorna como ElementTree para compatibilidade
        return ET.fromstring(xml_dps.encode('utf-8'))

    def send_batch(self, batch_fields=None):
        """
        Assina e envia o lote de RPS para o sistema nacional.
        
        Args:
            batch_fields: Dicionário com campos do lote (opcional, mantido para compatibilidade)
            
        Returns:
            tuple: (result, errors) onde result é um dicionário e errors é um dicionário
        """
        if not self.pfx_file or not os.path.exists(self.pfx_file):
            raise ValueError("Certificado PFX não encontrado ou não especificado")
        
        if not self.pfx_passwd:
            raise ValueError("Senha do certificado não especificada")
        
        if not self.rps_batch:
            return ({}, {'error': 'Nenhum RPS no lote'})
        
        # No novo padrão, envia um por vez (não há lote)
        # Mas mantemos compatibilidade retornando no formato esperado
        result = {}
        errors = {}
        
        # Pega o primeiro RPS do lote
        item = self.rps_batch[0]
        
        try:
            if self.logger:
                self.logger.info('[NFSe Nacional] Iniciando envio de DPS para o Portal Nacional')
            
            # Assina o XML (DPS no padrão nacional)
            if self.logger:
                self.logger.info('[NFSe Nacional] Assinando XML da DPS com certificado')
            xml_signed = assinar_xml(
                xml_input=item['xml'],
                pfx_path=self.pfx_file,
                pfx_password=self.pfx_passwd,
                tag_to_sign="infDPS",
                logger=self.logger
            )
            
            # Garante que xml_signed é string
            if isinstance(xml_signed, bytes):
                xml_signed = xml_signed.decode('utf-8')
            
            if self.logger:
                self.logger.info('[NFSe Nacional] XML assinado com sucesso (tamanho: %d caracteres)' % len(xml_signed))
            
            # Verifica se o XML está no padrão nacional (deve conter <DPS> e namespace)
            if '<DPS' not in xml_signed or 'http://www.sped.fazenda.gov.br/nfse' not in xml_signed:
                error_msg = "XML não está no padrão nacional. Deve conter <DPS> com namespace correto."
                if self.logger:
                    self.logger.error('[NFSe Nacional] %s' % error_msg)
                raise ValueError(error_msg)
            
            # Compacta e codifica em base64
            if self.logger:
                self.logger.info('[NFSe Nacional] Compactando e codificando DPS em base64')
            dps_b64 = gerar_dpsXmlGZipB64(xml_signed)
            
            if self.logger:
                self.logger.info('[NFSe Nacional] DPS compactada e codificada (tamanho base64: %d caracteres)' % len(dps_b64))
                self.logger.info('[NFSe Nacional] Enviando DPS para Portal Nacional: %s' % URL_PRODUCAO)
            
            # Envia para o sistema nacional (Portal Nacional de NFSe)
            response = enviar_nfse_pkcs12(
                dps_b64=dps_b64,
                pfx_path=self.pfx_file,
                pfx_password=self.pfx_passwd,
                logger=self.logger
            )
            
            if self.logger:
                self.logger.info('[NFSe Nacional] Resposta recebida do Portal Nacional - Status HTTP: %s' % response.get('status', 'N/A'))
            
            # No novo padrão, o portal retorna chaveAcesso e idDps, não protocolo
            # Retornamos os dados diretamente para o código processar
            chave_acesso = response.get('chave_acesso', '')
            id_dps = response.get('id_dps', '')
            xml_nfse = response.get('xml_nfse', '')
            
            # Verifica se há erros na resposta (mesmo com status 200/201)
            mensagem_erro = response.get('mensagem_erro')
            erros = response.get('erros', [])
            
            if mensagem_erro or (response.get('status') not in (200, 201)):
                # Erro: retorna XML com mensagem de erro
                error_msg = mensagem_erro or response.get('body', 'Erro desconhecido')
                if self.logger:
                    self.logger.error('[NFSe Nacional] Erro ao enviar DPS - Status HTTP: %s' % response.get('status', 'N/A'))
                    self.logger.error('[NFSe Nacional] Mensagem de erro: %s' % error_msg[:500])
                
                root = ET.Element('EnviarLoteRpsResposta')
                ET.SubElement(root, 'Protocolo').text = 'ERRO'
                lista_msg = ET.SubElement(root, 'ListaMensagemRetorno')
                msg = ET.SubElement(lista_msg, 'MensagemRetorno')
                ET.SubElement(msg, 'Codigo').text = 'ERRO'
                ET.SubElement(msg, 'Mensagem').text = error_msg[:500]
                xml_str = ET.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8')
                result['ws.response'] = xml_str
                errors['error'] = error_msg
                # Salva erros para uso posterior
                result['erros'] = erros
                result['mensagem_erro'] = mensagem_erro
            elif response.get('status') in (200, 201):
                if self.logger:
                    self.logger.info('[NFSe Nacional] DPS aceita pelo Portal Nacional - Status: %s' % response.get('status'))
                    if chave_acesso:
                        self.logger.info('[NFSe Nacional] Chave de acesso recebida: %s' % chave_acesso)
                    if id_dps:
                        self.logger.info('[NFSe Nacional] ID DPS recebido: %s' % id_dps)
                    if xml_nfse:
                        self.logger.info('[NFSe Nacional] XML da NFSe recebido (tamanho: %d caracteres)' % len(xml_nfse))
                
                # Sucesso: retorna dados no formato esperado
                # Armazena chave_acesso e id_dps diretamente no result para uso posterior
                result['chave_acesso'] = chave_acesso
                result['id_dps'] = id_dps
                result['xml_nfse'] = xml_nfse
                # XML assinado que foi enviado ao portal nacional (DPS no padrão nacional)
                # Garante que é string
                if isinstance(xml_signed, bytes):
                    result['xml_enviado'] = xml_signed.decode('utf-8')
                else:
                    result['xml_enviado'] = str(xml_signed)
                
                # Cria XML no formato antigo para compatibilidade (usa chave_acesso como protocolo)
                root = ET.Element('EnviarLoteRpsResposta')
                protocolo_elem = ET.SubElement(root, 'Protocolo')
                # No novo padrão, protocolo_lote armazena a chave de acesso
                protocolo_elem.text = str(chave_acesso or id_dps or 'PROCESSADO')
                
                # Se tiver XML da NFSe, extrai informações adicionais
                if xml_nfse:
                    try:
                        nfse_root = ET.fromstring(xml_nfse.encode('utf-8'))
                        # Tenta encontrar número da NFSe com diferentes namespaces
                        numero_nf = None
                        for ns in ['{http://www.sped.fazenda.gov.br/nfse}', '']:
                            numero_nf = nfse_root.find(f'.//{ns}nNFSe')
                            if numero_nf is not None:
                                break
                        if numero_nf is not None and numero_nf.text:
                            ET.SubElement(root, 'NumeroNFSe').text = numero_nf.text
                    except Exception:
                        pass
                
                xml_str = ET.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8')
                result['ws.response'] = xml_str
            else:
                # Erro: retorna XML com mensagem de erro
                error_msg = response.get('body', 'Erro desconhecido')
                if self.logger:
                    self.logger.error('[NFSe Nacional] Erro ao enviar DPS - Status HTTP: %s' % response.get('status', 'N/A'))
                    self.logger.error('[NFSe Nacional] Mensagem de erro: %s' % error_msg[:500])
                
                root = ET.Element('EnviarLoteRpsResposta')
                ET.SubElement(root, 'Protocolo').text = 'ERRO'
                lista_msg = ET.SubElement(root, 'ListaMensagemRetorno')
                msg = ET.SubElement(lista_msg, 'MensagemRetorno')
                ET.SubElement(msg, 'Codigo').text = 'ERRO'
                ET.SubElement(msg, 'Mensagem').text = error_msg[:500]
                xml_str = ET.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8')
                result['ws.response'] = xml_str
                errors['error'] = error_msg
                
        except Exception as e:
            error_msg = str(e)
            if self.logger:
                self.logger.error('[NFSe Nacional] Exceção ao processar envio de DPS: %s' % error_msg)
            errors['error'] = error_msg
        
        return (result, errors)

    def get_batch_status(self, params):
        """
        Consulta o status de uma NFSe pela chave de acesso.
        No novo padrão não há "lote", apenas consulta individual.
        
        Args:
            params: Dicionário com parâmetros
                - 'lote.protocolo': Chave de acesso (armazenada em protocolo_lote)
                - 'chave_acesso': Chave de acesso direta (alternativa)
            
        Returns:
            tuple: (result, error) onde result contém 'ws.response' com XML
        """
        if self.logger:
            self.logger.info('[NFSe Nacional] Iniciando consulta de status da NFSe')
        
        result = {}
        error = {}
        
        # Obtém chave de acesso (no novo padrão, protocolo_lote armazena a chave de acesso)
        protocolo = params.get('lote.protocolo', '')
        chave_acesso = params.get('chave_acesso', protocolo)
        
        if not chave_acesso:
            error_msg = 'Chave de acesso não fornecida. No novo padrão, é necessário a chave de acesso para consultar.'
            if self.logger:
                self.logger.error('[NFSe Nacional] %s' % error_msg)
            error['error'] = error_msg
            return (result, error)
        
        if self.logger:
            self.logger.info('[NFSe Nacional] Consultando NFSe com chave de acesso: %s' % chave_acesso)
        
        if self.pfx_file and self.pfx_passwd:
            try:
                response = consultar_nfse(chave_acesso, self.pfx_file, self.pfx_passwd, logger=self.logger)
                if response:
                    if self.logger:
                        self.logger.info('[NFSe Nacional] Resposta recebida da consulta - Status: %s' % response.get('status', 'N/A'))
                    # Se tiver XML, parseia para extrair informações
                    xml_resp = response.get('xml', response.get('body', ''))
                    if xml_resp:
                        if self.logger:
                            self.logger.info('[NFSe Nacional] XML da consulta recebido (tamanho: %d caracteres)' % len(xml_resp))
                        # Cria XML no formato antigo esperado
                        root = ET.Element('ConsultarSituacaoLoteRpsResposta')
                        # Situação 4 = Processado com sucesso
                        ET.SubElement(root, 'Situacao').text = '4'
                        
                        # Lista de mensagens vazia
                        lista_msg = ET.SubElement(root, 'ListaMensagemRetorno')
                        
                        result['ws.response'] = ET.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8')
                        if self.logger:
                            self.logger.info('[NFSe Nacional] Consulta concluída com sucesso')
                    else:
                        error_msg = 'Resposta vazia do Portal Nacional'
                        if self.logger:
                            self.logger.error('[NFSe Nacional] %s' % error_msg)
                        error['error'] = error_msg
                else:
                    error_msg = 'NFSe não encontrada no Portal Nacional'
                    if self.logger:
                        self.logger.error('[NFSe Nacional] %s' % error_msg)
                    error['error'] = error_msg
            except Exception as e:
                error_msg = f'Erro ao consultar Portal Nacional: {str(e)}'
                if self.logger:
                    self.logger.error('[NFSe Nacional] %s' % error_msg)
                error['error'] = error_msg
        else:
            error_msg = 'Certificado não configurado'
            if self.logger:
                self.logger.error('[NFSe Nacional] %s' % error_msg)
            error['error'] = error_msg
        
        return (result, error)

    def get_nfse_by_rps(self, params):
        """
        Consulta uma NFSe pelo RPS.
        No novo padrão, precisamos da chave de acesso, mas mantemos compatibilidade.
        
        Args:
            params: Dicionário com parâmetros do RPS
            
        Returns:
            tuple: (result, error) onde result contém 'ws.response' com XML
        """
        if self.logger:
            self.logger.info('[NFSe Nacional] Iniciando consulta de NFSe por RPS')
        
        result = {}
        error = {}
        
        # Tenta obter chave de acesso (pode vir como protocolo no sistema antigo)
        chave_acesso = params.get('chave_acesso') or params.get('lote.protocolo')
        
        if not chave_acesso:
            error_msg = 'Chave de acesso não fornecida. No novo padrão, é necessário a chave de acesso para consultar.'
            if self.logger:
                self.logger.error('[NFSe Nacional] %s' % error_msg)
            error['error'] = error_msg
            return (result, error)
        
        if self.logger:
            self.logger.info('[NFSe Nacional] Consultando NFSe por RPS com chave de acesso: %s' % chave_acesso)
        
        if self.pfx_file and self.pfx_passwd:
            try:
                response = consultar_nfse(chave_acesso, self.pfx_file, self.pfx_passwd, logger=self.logger)
                if response:
                    if self.logger:
                        self.logger.info('[NFSe Nacional] Resposta recebida da consulta por RPS - Status: %s' % response.get('status', 'N/A'))
                    xml_resp = response.get('xml', response.get('body', ''))
                    if xml_resp:
                        if self.logger:
                            self.logger.info('[NFSe Nacional] XML da consulta por RPS recebido (tamanho: %d caracteres)' % len(xml_resp))
                        # Tenta parsear o XML do novo padrão e converter para formato antigo
                        try:
                            nfse_root = ET.fromstring(xml_resp.encode('utf-8'))
                            
                            # Extrai número da NFSe
                            numero_nf = nfse_root.find('.//{http://www.sped.fazenda.gov.br/nfse}nNFSe')
                            numero_nf_text = numero_nf.text if numero_nf is not None and numero_nf.text else ''
                            
                            if self.logger and numero_nf_text:
                                self.logger.info('[NFSe Nacional] Número da NFSe extraído: %s' % numero_nf_text)
                            
                            # Cria XML no formato antigo esperado
                            root = ET.Element('ConsultarNfseRpsResposta')
                            comp_nfse = ET.SubElement(root, 'CompNfse')
                            nfse_elem = ET.SubElement(comp_nfse, 'Nfse')
                            inf_nfse = ET.SubElement(nfse_elem, 'InfNfse')
                            ET.SubElement(inf_nfse, 'Numero').text = numero_nf_text
                            
                            result['ws.response'] = ET.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8')
                            if self.logger:
                                self.logger.info('[NFSe Nacional] Consulta por RPS concluída com sucesso')
                        except Exception as e:
                            if self.logger:
                                self.logger.error('[NFSe Nacional] Erro ao parsear XML da consulta: %s' % str(e))
                            # Se não conseguir parsear, retorna o XML original
                            result['ws.response'] = xml_resp
                    else:
                        error_msg = 'Resposta vazia'
                        if self.logger:
                            self.logger.error('[NFSe Nacional] %s' % error_msg)
                        error['error'] = error_msg
                else:
                    error_msg = 'NFSe não encontrada'
                    if self.logger:
                        self.logger.error('[NFSe Nacional] %s' % error_msg)
                    error['error'] = error_msg
            except Exception as e:
                error_msg = str(e)
                if self.logger:
                    self.logger.error('[NFSe Nacional] Exceção ao consultar por RPS: %s' % error_msg)
                error['error'] = error_msg
        else:
            error_msg = 'Certificado não configurado'
            if self.logger:
                self.logger.error('[NFSe Nacional] %s' % error_msg)
            error['error'] = error_msg
        
        return (result, error)

    def add_to_cancel(self, nf_fields):
        """
        Adiciona uma NFSe ao lote de cancelamento.
        
        Args:
            nf_fields: Dicionário com campos da NFSe a ser cancelada
                - 'nf.prestador.documento': CNPJ do prestador (obrigatório)
                - 'nf.chave_acesso' ou 'chave_acesso': Chave de acesso da nota (obrigatório)
                - 'nf.justificativa' ou 'justificativa': Justificativa do cancelamento
                - 'nf.cancela.id': Chave de acesso alternativa (compatibilidade)
        
        Returns:
            ElementTree: XML do cancelamento gerado
        """
        if self.logger:
            self.logger.info('[NFSe Nacional] Iniciando preparação de cancelamento')
        
        # Extrai dados necessários
        emitter_cnpj = nf_fields.get('nf.prestador.documento', '')
        chave_acesso = nf_fields.get('nf.chave_acesso') or nf_fields.get('chave_acesso')
        justificativa = nf_fields.get('nf.justificativa') or nf_fields.get('justificativa', 'Erro na emissão')
        
        # Se não tiver chave de acesso, tenta usar protocolo como chave (compatibilidade)
        # No novo padrão, protocolo_lote armazena a chave de acesso
        if not chave_acesso:
            protocolo = nf_fields.get('nf.cancela.id') or nf_fields.get('protocolo')
            if protocolo:
                chave_acesso = protocolo
            else:
                error_msg = "Chave de acesso não fornecida. No novo padrão do Portal Nacional, é necessário a chave de acesso (armazenada em protocolo_lote) para cancelar."
                if self.logger:
                    self.logger.error('[NFSe Nacional] %s' % error_msg)
                raise ValueError(error_msg)
        
        if self.logger:
            self.logger.info('[NFSe Nacional] Gerando XML de cancelamento - Chave de acesso: %s, Prestador: %s' % (chave_acesso, emitter_cnpj))
        
        # Gera XML de cancelamento
        xml_cancel = build_cancelamento_xml(
            emitter_cnpj=emitter_cnpj,
            chave_acesso_nota=chave_acesso,
            justificativa=justificativa,
        )
        
        if self.logger:
            self.logger.info('[NFSe Nacional] XML de cancelamento gerado com sucesso (tamanho: %d caracteres)' % len(xml_cancel))
        
        # Armazena no lote
        self.cancel_batch.append({
            'xml': xml_cancel,
            'nf_fields': nf_fields,
            'chave_acesso': chave_acesso,
        })
        
        # Retorna como ElementTree para compatibilidade
        return ET.fromstring(xml_cancel.encode('utf-8'))

    def cancel(self, strict=True, raw_response=False):
        """
        Envia o cancelamento para o portal nacional.
        
        Args:
            strict: Mantido para compatibilidade (não usado)
            raw_response: Mantido para compatibilidade (não usado)
            
        Returns:
            tuple: (result, errors) onde result é uma lista e errors é uma lista
        """
        if not self.pfx_file or not os.path.exists(self.pfx_file):
            raise ValueError("Certificado PFX não encontrado ou não especificado")
        
        if not self.pfx_passwd:
            raise ValueError("Senha do certificado não especificada")
        
        if not self.cancel_batch:
            error_msg = 'Nenhum cancelamento no lote'
            if self.logger:
                self.logger.error('[NFSe Nacional] %s' % error_msg)
            return ([], [{'error': error_msg}])
        
        if self.logger:
            self.logger.info('[NFSe Nacional] Processando %d cancelamento(s)' % len(self.cancel_batch))
        
        results = []
        errors = []
        
        for item in self.cancel_batch:
            chave_acesso = item.get('chave_acesso', 'N/A')
            if self.logger:
                self.logger.info('[NFSe Nacional] Processando cancelamento - Chave de acesso: %s' % chave_acesso)
            
            try:
                # Assina o XML
                if self.logger:
                    self.logger.info('[NFSe Nacional] Assinando XML de cancelamento')
                xml_signed = assinar_xml(
                    xml_input=item['xml'],
                    pfx_path=self.pfx_file,
                    pfx_password=self.pfx_passwd,
                    tag_to_sign="infPedReg",
                    logger=self.logger
                )
                
                if self.logger:
                    self.logger.info('[NFSe Nacional] XML de cancelamento assinado (tamanho: %d caracteres)' % len(xml_signed))
                
                # Compacta e codifica em base64
                if self.logger:
                    self.logger.info('[NFSe Nacional] Compactando e codificando evento de cancelamento em base64')
                evento_b64 = gerar_dpsXmlGZipB64(xml_signed)
                
                if self.logger:
                    self.logger.info('[NFSe Nacional] Enviando cancelamento para Portal Nacional')
                
                # Envia para o portal nacional
                response = enviar_cancelamento_pkcs12(
                    chave_acesso=item['chave_acesso'],
                    evento_b64_gzip=evento_b64,
                    pfx_path=self.pfx_file,
                    pfx_password=self.pfx_passwd,
                    logger=self.logger
                )
                
                if self.logger:
                    self.logger.info('[NFSe Nacional] Resposta do cancelamento recebida - Status HTTP: %s' % (response.status_code if hasattr(response, 'status_code') else 'N/A'))
                
                # Formata resposta no formato esperado
                if response.status_code in (200, 201):
                    try:
                        xml_resp = response.text
                        # Cria XML no formato antigo esperado
                        root = ET.Element('CancelarNfseResposta')
                        cancelamento = ET.SubElement(root, 'Cancelamento')
                        ET.SubElement(cancelamento, 'Confirmacao')
                        
                        # Lista de mensagens vazia
                        lista_msg = ET.SubElement(root, 'ListaMensagemRetorno')
                        
                        results.append({
                            'ws.response': ET.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8'),
                        })
                    except Exception as e:
                        # Fallback: XML simples
                        root = ET.Element('CancelarNfseResposta')
                        cancelamento = ET.SubElement(root, 'Cancelamento')
                        ET.SubElement(cancelamento, 'Confirmacao')
                        lista_msg = ET.SubElement(root, 'ListaMensagemRetorno')
                        results.append({
                            'ws.response': ET.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8'),
                        })
                else:
                    # Em caso de erro, cria XML com mensagem de erro
                    root = ET.Element('CancelarNfseResposta')
                    lista_msg = ET.SubElement(root, 'ListaMensagemRetorno')
                    msg_ret = ET.SubElement(lista_msg, 'MensagemRetorno')
                    ET.SubElement(msg_ret, 'Codigo').text = 'ERRO'
                    ET.SubElement(msg_ret, 'Mensagem').text = response.text or 'Erro ao cancelar NFSe'
                    
                    errors.append({
                        'error': ET.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8'),
                    })
                    
            except Exception as e:
                errors.append({
                    'error': str(e),
                })
        
        return (results, errors)

