import json
from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    withholding_amount = fields.Monetary(
        string="Valor da Retenção",
        compute="_compute_withholding_amount",
        store=True,
        readonly=True
    )
    net_amount = fields.Monetary(
        string="Líquido a Pagar",
        compute="_compute_net_amount",
        store=True,
        readonly=True
    )
    withholding_by_group = fields.Text(
        string="Resumo de Retenções (JSON)",
        compute='_compute_withholding_by_group',
        help='Utilizado para mostrar os totais de retenção agrupados no relatório.'
    )

    @api.depends('order_line.price_subtotal', 'order_line.withholding_tax_id')
    def _compute_withholding_by_group(self):
        for order in self:
            withholding_groups = {}
            for line in order.order_line.filtered(lambda l: l.withholding_tax_id):
                tax = line.withholding_tax_id
                if tax.id not in withholding_groups:
                    withholding_groups[tax.id] = {'base': 0.0, 'amount': 0.0, 'name': tax.name, 'code': tax.code}

                base_amount = line.price_subtotal
                if tax.tax_type == 'iva':
                    vat_amount = line.price_tax
                    wht_amount = vat_amount * (tax.percentage / 100)
                else:
                    wht_amount = base_amount * (tax.percentage / 100)

                withholding_groups[tax.id]['base'] += base_amount
                withholding_groups[tax.id]['amount'] += wht_amount

            grouped_data = [
                {
                    'code': group['code'],
                    'name': group['name'],
                    'base': group['base'],
                    'amount': group['amount']
                }
                for tax_id, group in withholding_groups.items()
            ]
            order.withholding_by_group = json.dumps(grouped_data)

    def get_wht_groups_for_report(self):
        self.ensure_one()
        if not self.withholding_by_group:
            return []
        
        groups = json.loads(self.withholding_by_group)
        report_data = []
        for group in groups:
            report_data.append([
                group.get('name', ''),
                group.get('base', 0.0),
                group.get('amount', 0.0)
            ])
        return report_data

    @api.depends('order_line.price_subtotal', 'order_line.withholding_tax_id')
    def _compute_withholding_amount(self):
        for order in self:
            withholding_amount = 0.0
            for line in order.order_line:
                if line.withholding_tax_id:
                    tax = line.withholding_tax_id
                    if tax.tax_type == 'iva':
                        vat_amount = line.price_tax
                        withholding_amount += vat_amount * (tax.percentage / 100)
                    else:
                        withholding_amount += line.price_subtotal * (tax.percentage / 100)
            order.withholding_amount = withholding_amount

    @api.depends('amount_total', 'withholding_amount')
    def _compute_net_amount(self):
        for order in self:
            order.net_amount = abs(order.amount_total - order.withholding_amount)

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        return invoice_vals


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    withholding_tax_id = fields.Many2one(
        'withholding.tax',
        string="Retenção na Fonte",
        domain="[('company_id', '=', company_id)]"
    )
    withholding_amount = fields.Monetary(
        string="Valor Retido",
        compute="_compute_withholding_amount",
        store=True
    )

    @api.depends('price_subtotal', 'price_tax', 'withholding_tax_id')
    def _compute_withholding_amount(self):
        for line in self:
            amount = 0.0
            if line.withholding_tax_id and line.price_subtotal:
                tax = line.withholding_tax_id
                if tax.tax_type == 'iva':
                    amount = line.price_tax * (tax.percentage / 100.0)
                else:
                    amount = line.price_subtotal * (tax.percentage / 100.0)
            line.withholding_amount = amount

    def _prepare_invoice_line(self, **optional_values):
        res = super()._prepare_invoice_line(**optional_values)
        if self.withholding_tax_id:
            res['withholding_tax_id'] = self.withholding_tax_id.id
        return res

    def get_line_withholding(self):
        self.ensure_one()
        if not self.withholding_tax_id:
            return 0.0
        tax = self.withholding_tax_id
        if tax.tax_type == 'iva':
            return self.price_tax * (tax.percentage / 100)
        return self.price_subtotal * (tax.percentage / 100)