# -*- coding: utf-8 -*-
import json
from lxml import etree as et
from odoo import models, api

class WizardSaftWithholding(models.Model):
    _inherit = "wizard.l10n_pt.saft"

    def _write_source_documents(self, start_date, final_date, versao, empresa):
        # Chamar a função original para obter a estrutura XML base
        esource_documents = super(WizardSaftWithholding, self)._write_source_documents(start_date, final_date, versao, empresa)

        # Se a função original não retornar nada (ex: sem faturas), não fazemos nada
        if esource_documents is None:
            return None

        # Encontrar todas as faturas no XML gerado
        invoices_xml = esource_documents.findall('.//Invoice')
        if not invoices_xml:
            return esource_documents

        # Obter todos os números das faturas do XML para uma única pesquisa no Odoo
        # O formato no SAFT é "PREFIXO NUMERO", precisamos de extrair o "NUMERO"
        invoice_numbers_map = {}
        for inv_xml in invoices_xml:
            invoice_no_text = inv_xml.find('InvoiceNo').text
            if invoice_no_text:
                parts = invoice_no_text.split(' ')
                if len(parts) > 1:
                    # Guardamos o texto completo do nó para encontrar o elemento XML mais tarde
                    invoice_numbers_map[parts[-1]] = invoice_no_text

        clean_invoice_numbers = list(invoice_numbers_map.keys())
        if not clean_invoice_numbers:
            return esource_documents

        # Pesquisar todas as faturas de uma vez para otimização
        moves = self.env['account.move'].search([
            ('internal_number', 'in', clean_invoice_numbers),
            ('company_id', '=', empresa)
        ])
        # Criar um dicionário para acesso rápido: {numero_interno: objeto_fatura}
        moves_dict = {move.internal_number: move for move in moves}

        # Iterar novamente sobre os elementos XML para modificá-los
        for internal_number, full_invoice_no in invoice_numbers_map.items():
            # Encontrar o elemento XML correspondente
            invoice_xml = next((inv for inv in invoices_xml if inv.find('InvoiceNo').text == full_invoice_no), None)

            if invoice_xml is not None and internal_number in moves_dict:
                invoice_odoo = moves_dict[internal_number]

                # Adicionar o bloco de retenção se existir
                if invoice_odoo.withholding_amount > 0 and hasattr(invoice_odoo, 'withholding_by_group') and invoice_odoo.withholding_by_group:
                    document_totals_xml = invoice_xml.find('DocumentTotals')
                    if document_totals_xml is not None:
                        try:
                            withholding_data = json.loads(invoice_odoo.withholding_by_group)
                            for wht_tax in withholding_data:
                                ewithholding_tax = et.SubElement(document_totals_xml, "WithholdingTax")
                                et.SubElement(ewithholding_tax, "WithholdingTaxType").text = wht_tax.get('code', '')
                                et.SubElement(ewithholding_tax, "WithholdingTaxDescription").text = wht_tax.get('name', '')
                                et.SubElement(ewithholding_tax, "WithholdingTaxAmount").text = "{:.2f}".format(wht_tax.get('amount', 0.0))
                        except (json.JSONDecodeError, TypeError):
                            # Ignorar se o JSON for inválido ou não for uma string
                            continue

        return esource_documents
