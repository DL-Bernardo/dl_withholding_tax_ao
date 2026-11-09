import json
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class AccountMove(models.Model):
    _inherit = 'account.move'

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
        help='Utilizado para mostrar os totais de retenção agrupados no relatório e para o SAFT.'
    )

    def _compute_withholding_by_group(self):
        for move in self:
            withholding_groups = {}
            for line in move.invoice_line_ids.filtered(lambda l: l.withholding_tax_id):
                tax = line.withholding_tax_id
                if tax not in withholding_groups:
                    withholding_groups[tax] = {'base': 0.0, 'amount': 0.0}

                base_amount = line.price_subtotal
                if tax.tax_type == 'iva':
                    vat_amount = line.price_total - line.price_subtotal
                    wht_amount = vat_amount * (tax.percentage / 100)
                else:
                    wht_amount = base_amount * (tax.percentage / 100)

                withholding_groups[tax]['base'] += base_amount
                withholding_groups[tax]['amount'] += wht_amount

            # Preparar dados para SAFT e relatórios
            grouped_data = [
                {
                    'code': tax.code,
                    'name': tax.name,
                    'base': group['base'],
                    'amount': group['amount']
                }
                for tax, group in withholding_groups.items()
            ]
            move.withholding_by_group = json.dumps(grouped_data)

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

    @api.depends('invoice_line_ids.price_subtotal', 'invoice_line_ids.withholding_tax_id')
    def _compute_withholding_amount(self):
        for move in self:
            withholding_amount = 0.0
            for line in move.invoice_line_ids:
                if line.withholding_tax_id:
                    tax = line.withholding_tax_id
                    if tax.tax_type == 'iva':
                        vat_amount = line.price_total - line.price_subtotal
                        withholding_amount += vat_amount * (tax.percentage / 100)
                    else:
                        withholding_amount += line.price_subtotal * (tax.percentage / 100)
            move.withholding_amount = withholding_amount

    @api.depends('amount_total', 'withholding_amount')
    def _compute_net_amount(self):
        for move in self:
            move.net_amount = abs(move.amount_total - move.withholding_amount)

    def action_post(self):
        res = super().action_post()
        for move in self:
            if move.is_invoice(include_receipts=True) and move.withholding_amount > 0:
                self._create_withholding_entry(move)
        return res

    def certify(self):
        """
        Sobrescreve o método `certify` do módulo `opc_certification_ao`.
        """
        self._compute_amount()
        self._compute_withholding_amount()
        self._compute_net_amount()
        return super().certify()

    def _create_withholding_entry(self, invoice):
        withholding_map = {}
        for line in invoice.invoice_line_ids:
            if line.withholding_tax_id:
                tax = line.withholding_tax_id
                if tax.tax_type == 'iva':
                    vat_amount = line.price_total - line.price_subtotal
                    amount = vat_amount * (tax.percentage / 100)
                else:
                    amount = line.price_subtotal * (tax.percentage / 100)
                    
                if tax in withholding_map:
                    withholding_map[tax] += amount
                else:
                    withholding_map[tax] = amount

        # Identificar se é uma Nota de Crédito/Reembolso
        is_refund = invoice.move_type in ('out_refund', 'in_refund')

        partner = invoice.partner_id
        receivable_account = partner.property_account_receivable_id
        payable_account = partner.property_account_payable_id

        arp_line = self.env['account.move.line']
        for line in invoice.line_ids:
            if line.account_id in (receivable_account, payable_account):
                arp_line = line
                break

        if not arp_line:
            return

        misc_journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', invoice.company_id.id)
        ], limit=1)
        
        if not misc_journal:
            raise UserError(_("Não foi encontrado um diário do tipo 'Operações Diversas'."))

        for tax, amount in withholding_map.items():
            withholding_account = tax.account_id
            if not withholding_account:
                raise UserError(_("A conta contabilística para a retenção '%s' não está definida.") % tax.name)

            move_vals = {
                'move_type': 'entry',
                'partner_id': invoice.partner_id.id,
                'journal_id': misc_journal.id,
                'date': invoice.date,
                'ref': _('Registo de Retenção: %s (%s)') % (invoice.name, tax.name),
                'line_ids': [
                    (0, 0, {
                        'name': _('Valor da Retenção (%s%%)') % tax.percentage,
                        'debit': amount if is_refund else 0.0,
                        'credit': 0.0 if is_refund else amount,
                        'account_id': arp_line.account_id.id,
                        'partner_id': invoice.partner_id.id,
                    }),
                    (0, 0, {
                        'name': _('Provisão para %s') % tax.name,
                        'debit': 0.0 if is_refund else amount,
                        'credit': amount if is_refund else 0.0,
                        'account_id': withholding_account.id,
                        'partner_id': invoice.partner_id.id,
                    }),
                ]
            }
            withholding_move = self.env['account.move'].create(move_vals)
            withholding_move.action_post()

            # RECONCILIAÇÃO SEGURA
            lines_to_reconcile = (arp_line | withholding_move.line_ids.filtered(
                lambda l: l.account_id == arp_line.account_id
            )).filtered(lambda l: not l.reconciled)

            if len(lines_to_reconcile) > 1:
                lines_to_reconcile.reconcile()

    @api.model_create_multi
    def create(self, vals_list):
        if isinstance(vals_list, dict):
            vals_list = [vals_list]
        wht_per_move = []
        for vals in vals_list:
            withholding_values = []
            if 'invoice_line_ids' in vals:
                for line_command in vals.get('invoice_line_ids', []):
                    if line_command and line_command[0] == 0 and isinstance(line_command[2], dict):
                        withholding_values.append(line_command[2].get('withholding_tax_id'))
            wht_per_move.append(withholding_values)

        moves = super(AccountMove, self).create(vals_list)
        for move, withholding_values in zip(moves, wht_per_move):
            product_lines = move.invoice_line_ids.filtered(lambda line: not line.tax_line_id)
            if withholding_values and len(product_lines) == len(withholding_values):
                for i, line in enumerate(product_lines):
                    wht_id = withholding_values[i]
                    if wht_id and not line.withholding_tax_id:
                        line.withholding_tax_id = wht_id
        return moves

    def write(self, vals):
        if 'invoice_line_ids' in vals:
            existing_line_ids = self.invoice_line_ids.ids
            line_updates = {}
            new_line_withholding = []
            for command in vals['invoice_line_ids']:
                if command[0] == 1:
                    if 'withholding_tax_id' in command[2]:
                        line_updates[command[1]] = command[2]['withholding_tax_id']
                elif command[0] == 0:
                    new_line_withholding.append(command[2].get('withholding_tax_id'))

            res = super(AccountMove, self).write(vals)

            if line_updates:
                for line_id, wht_id in line_updates.items():
                    self.env['account.move.line'].browse(line_id).write({'withholding_tax_id': wht_id})
            
            if new_line_withholding:
                self.ensure_one()
                new_lines = self.invoice_line_ids.filtered(lambda l: l.id not in existing_line_ids)
                product_lines = new_lines.filtered(lambda l: not l.tax_line_id and not l.display_type)
                if len(product_lines) == len(new_line_withholding):
                    for i, line in enumerate(product_lines):
                        wht_id = new_line_withholding[i]
                        if wht_id and not line.withholding_tax_id:
                            line.withholding_tax_id = wht_id
            return res
        return super(AccountMove, self).write(vals)

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    withholding_tax_id = fields.Many2one(
        'withholding.tax',
        string="Retenção na Fonte",
        domain="[('company_id', '=', company_id)]"
    )
    wht_valor_exato_fix = fields.Monetary(
        string="Valor Retido Fix",
        compute="_compute_wht_valor_exato_fix",
        currency_field='currency_id',
        store=False
    )

    @api.depends('price_subtotal', 'price_total', 'withholding_tax_id')
    def _compute_wht_valor_exato_fix(self):
        for line in self:
            if line.withholding_tax_id:
                tax = line.withholding_tax_id
                if tax.tax_type == 'iva':
                    vat_amount = line.price_total - line.price_subtotal
                    line.wht_valor_exato_fix = vat_amount * (tax.percentage / 100)
                else:
                    line.wht_valor_exato_fix = line.price_subtotal * (tax.percentage / 100)
            else:
                line.wht_valor_exato_fix = 0.0