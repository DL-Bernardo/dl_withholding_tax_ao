# -*- coding: utf-8 -*-
import json
import re
from lxml import etree as et
from odoo import models, api, _
from odoo.exceptions import ValidationError
from decimal import Decimal
import logging

_logger = logging.getLogger(__name__)

class WizardSaftWithholding(models.Model):
    _inherit = "wizard.l10n_pt.saft"

    def _write_source_documents(self, start_date, final_date, versao, empresa):
        _logger.info("saft :", ' A exportar Source Documents')

        args = [
            ('invoice_date', '>=', start_date),
            ('invoice_date', '<=', final_date),
            ('hash', '!=', False),
            ('company_id', '=', empresa),
            ('state', '!=', 'draft')]
        if self.tipo == 'S':
            args.append(('move_type', 'in', ['in_invoice', 'in_refund']))
            args.append(('journal_id.self_billing', '=', True))
        else:
            args.append(('move_type', 'in', ['out_invoice', 'out_refund']))
        invoices = self.env['account.move'].search(args)

        def extract_number(doc):
            match = re.search(r'/(\d+)$', doc.internal_number or doc.name or '')
            return int(match.group(1)) if match else 0

        # Ordenação correta para SAFT: agrupa por tipo de documento, depois data, depois número
        invoices = sorted(invoices, key=lambda inv: (
            'NC' if inv.move_type == 'out_refund' else inv.journal_id.saft_inv_type or '', # 1. Ordenar pelo tipo de documento correto
            inv.invoice_date,                   # 2. Ordenar por data da fatura
            inv.hash_date or inv.create_date,   # 3. Ordenar por data do sistema/hash
            extract_number(inv)                 # 4. Ordenar pelo número do documento
        ))

        esource_documents = et.Element('SourceDocuments')
        if invoices:
            esales_invoices = et.SubElement(esource_documents, "SalesInvoices")

            enumber_of_entries = et.SubElement(esales_invoices, u"NumberOfEntries")
            etotal_debit = et.SubElement(esales_invoices, u"TotalDebit")
            etotal_credit = et.SubElement(esales_invoices, u"TotalCredit")

            conta_inv = 0
            total_debit = 0
            total_credit = 0

            for invoice in invoices:
                if invoice.date >= start_date and invoice.hash is not None:
                    if final_date is False or invoice.date <= final_date:
                        conta_inv += 1
                        # ... (resto do código da função original) ...
                        # ... (copiado do ficheiro do utilizador) ...
                        einvoice = et.SubElement(esales_invoices, u"Invoice")
                        self._write_invoice(invoice, einvoice, versao)
                        cambio = 1
                        if invoice.company_id.currency_id.id != invoice.currency_id.id:
                            cambio = invoice.cambio
                            if cambio == 0:
                                cambio = 1
                        line_no = 1
                        for invoice_line in self.env['account.move.line'].sudo().search([('move_id', '=', invoice.id)]):
                            if invoice_line.product_id:
                                eline = et.SubElement(einvoice, u"Line")
                                et.SubElement(eline, u"LineNumber").text = str(line_no)
                                line_no += 1
                                if invoice.invoice_origin and invoice.move_type != 'out_refund':
                                    eorder_references = et.SubElement(eline, u"OrderReferences")
                                    eoriginating_on = et.SubElement(eorder_references, u"OriginatingON")
                                    eoriginating_on.text = _(invoice.invoice_origin)[:30]
                                if invoice_line.product_id:
                                    if not invoice_line.product_id.default_code:
                                        raise ValidationError(
                                            _('Product ' + _(invoice_line.product_id.name) +
                                              ' does not have internal reference.'))
                                    et.SubElement(eline, u"ProductCode").text = \
                                        invoice_line.product_id.default_code[:60]
                                prod_descr = (invoice_line.product_id and
                                              invoice_line.product_id.name or invoice_line.name)[:60]
                                et.SubElement(eline, u"ProductDescription").text = prod_descr.ljust(2)
                                et.SubElement(eline, u"Quantity").text = str(invoice_line.quantity)
                                if invoice_line.product_uom_id:
                                    et.SubElement(eline, u"UnitOfMeasure").text = invoice_line.product_uom_id.name
                                if invoice_line.price_subtotal:
                                    amount = round(float(invoice_line.price_subtotal) / cambio, 2)
                                else:
                                    amount = 0
                                if invoice_line.price_unit:
                                    preco_com_desconto = invoice_line.price_unit * (1 - invoice_line.discount / 100)
                                    et.SubElement(eline, u"UnitPrice").text = str(round(preco_com_desconto, 2))
                                else:
                                    et.SubElement(eline, u"UnitPrice").text = '0.00'
                                et.SubElement(eline, u"TaxPointDate").text = str(invoice.date)
                                if (invoice.invoice_origin or invoice.name) and invoice.move_type == 'out_refund':
                                    ereferences = et.SubElement(eline, u"References")
                                    if invoice.invoice_origin:
                                        et.SubElement(ereferences, u"Reference").text = _(invoice.invoice_origin)[:60]
                                    if invoice.reason_cancel:
                                        et.SubElement(ereferences, u"Reason").text = _(invoice.reason_cancel[:50])
                                    if not invoice.reason_cancel and invoice.move_type == 'out_invoice' and invoice.state == 'cancel' and invoice.hash:
                                        raise ValidationError(_('Invoice reason cancel must be defined on invoice numbered' + invoice.internal_number + '.'))
                                et.SubElement(eline, u"Description").text = invoice_line.name[:60]
                                if invoice.move_type == 'out_refund':
                                    et.SubElement(eline, u"DebitAmount").text = str(amount)
                                    if invoice.state != 'cancel':
                                        total_debit += amount
                                elif invoice.move_type == 'out_invoice':
                                    et.SubElement(eline, u"CreditAmount").text = str(amount)
                                    if invoice.state != 'cancel':
                                        total_credit += amount
                                cont = 0
                                for imposto in invoice_line.tax_ids:
                                    if invoice_line.product_id:
                                        cont += 1
                                        if cont == 1:
                                            etax = et.SubElement(eline, u"Tax")
                                            et.SubElement(etax, u"TaxType").text = str(imposto.saft_tax_type)
                                            et.SubElement(etax, u"TaxCountryRegion").text = str(imposto.country_region)
                                            et.SubElement(etax, u"TaxCode").text = str(imposto.saft_tax_code)
                                            et.SubElement(etax, u"TaxPercentage").text = str(int(imposto.amount))
                                            if imposto.saft_tax_type == 'IVA' and imposto.amount == 0.0:
                                                if not imposto.exemption_reason or len(imposto.exemption_reason) < 6:
                                                    raise ValidationError(_('Falta configurar o motivo de isenção (este tem de ter pelo menos 6 caracteres).'))
                                                else:
                                                    et.SubElement(eline, u"TaxExemptionReason").text = str(imposto.exemption_reason)
                                                    if versao not in ["1.03_01"]:
                                                        TaxExemptionCode = imposto.description.split(' ')[0]
                                                        et.SubElement(eline, u"TaxExemptionCode").text = str(TaxExemptionCode)
                                                        if (imposto.exemption_reason and not TaxExemptionCode) or (TaxExemptionCode and not imposto.exemption_reason):
                                                            raise ValidationError(_('Tax exemption code in lack on tax ' + imposto.name + 'define it in order to proceed'))
                                            if imposto.amount == 0.0 and not imposto.exemption_reason:
                                                raise ValidationError(_('Tax exemption reason in lack on tax ' + imposto.name + 'define it in order to proceed'))
                                et.SubElement(eline, u"SettlementAmount").text = str(round(Decimal(((invoice_line.discount / 100) * (invoice_line.price_unit * invoice_line.quantity)) / cambio), 2))

                        edocument_totals = et.SubElement(einvoice, u"DocumentTotals")
                        et.SubElement(edocument_totals, u"TaxPayable").text = invoice.amount_tax and "{:.2f}".format(invoice.amount_tax / cambio) or '0.0'
                        et.SubElement(edocument_totals, u"NetTotal").text = invoice.amount_untaxed and "{:.2f}".format(invoice.amount_untaxed / cambio) or '0.0'
                        et.SubElement(edocument_totals, u"GrossTotal").text = "{:.2f}".format(round(float(invoice.grosstotal()) / cambio, 2))

                        # Bloco para adicionar a informação de Retenção na Fonte
                        if invoice.withholding_amount > 0 and hasattr(invoice, 'withholding_by_group') and invoice.withholding_by_group:
                            try:
                                withholding_data = json.loads(invoice.withholding_by_group)
                                # Criar os elementos a adicionar
                                wht_elements_to_add = []
                                for wht_tax in withholding_data:
                                    ewithholding_tax = et.Element("WithholdingTax")
                                    et.SubElement(ewithholding_tax, "WithholdingTaxType").text = wht_tax.get('code', '')
                                    et.SubElement(ewithholding_tax, "WithholdingTaxDescription").text = wht_tax.get('name', '')
                                    et.SubElement(ewithholding_tax, "WithholdingTaxAmount").text = "{:.2f}".format(wht_tax.get('amount', 0.0))
                                    wht_elements_to_add.append(ewithholding_tax)

                                # Inserir os novos elementos depois do DocumentTotals
                                if wht_elements_to_add:
                                    parent = edocument_totals.getparent()
                                    index = parent.index(edocument_totals)
                                    for i, element in enumerate(wht_elements_to_add, 1):
                                        parent.insert(index + i, element)
                            except (json.JSONDecodeError, TypeError):
                                pass

                        if invoice.currency_id.name != 'AOA':
                            ecurrency = et.SubElement(edocument_totals, u"Currency")
                            et.SubElement(ecurrency, u"CurrencyCode").text = invoice.currency_id.name
                            et.SubElement(ecurrency, u"CurrencyAmount").text = "{:.2f}".format(invoice.grosstotal())
                            et.SubElement(ecurrency, u"ExchangeRate").text = str(round(cambio, 4))

            enumber_of_entries.text = str(conta_inv)
            etotal_debit.text = str(float(round(total_debit,2)))
            etotal_credit.text = str(float(round(total_credit,2)))

        docs_m_o_g = self._write_movement_of_goods()
        if docs_m_o_g:
            esource_documents.append(docs_m_o_g)
        sales = self._sale_orders(start_date, final_date, empresa, esource_documents)
        if sales:
            esource_documents.append(sales)
        if self.tipo in ('I') or (self.comp.cash_vat_scheme_indicator and self.tipo != 'C'):
            docs_p = self._write_payments()
            if docs_p is not None:
                esource_documents.append(docs_p)

        return esource_documents