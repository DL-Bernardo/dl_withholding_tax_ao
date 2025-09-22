from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class AccountMove(models.Model):
    _inherit = 'account.move'

    withholding_amount = fields.Monetary(
        string="Valor da Retenção",
        compute="_compute_withholding",
        store=True,
        readonly=True
    )
    net_amount = fields.Monetary(
        string="Líquido a Pagar",
        compute="_compute_withholding",
        store=True,
        readonly=True
    )

    withholding_by_group = fields.Binary(
        string="Resumo de Retenções",
        compute='_compute_withholding_by_group',
        help='Utilizado para mostrar os totais de retenção agrupados no relatório.'
    )

    def _compute_withholding_by_group(self):
        for move in self:
            withholding_groups = {}
            for line in move.invoice_line_ids.filtered(lambda l: l.withholding_tax_id):
                tax = line.withholding_tax_id
                if tax not in withholding_groups:
                    withholding_groups[tax] = {'base': 0.0, 'amount': 0.0}

                withholding_groups[tax]['base'] += line.price_subtotal
                withholding_groups[tax]['amount'] += line.price_subtotal * (tax.percentage / 100)

            move.withholding_by_group = [
                (
                    tax.name,
                    group['base'],
                    group['amount']
                )
                for tax, group in withholding_groups.items()
            ]

    @api.depends('invoice_line_ids.price_subtotal', 'invoice_line_ids.withholding_tax_id')
    def _compute_withholding(self):
        for move in self:
            withholding_amount = 0.0
            for line in move.invoice_line_ids:
                if line.withholding_tax_id:
                    withholding_amount += line.price_subtotal * (line.withholding_tax_id.percentage / 100)
            move.withholding_amount = withholding_amount
            move.net_amount = move.amount_total - move.withholding_amount

    def action_post(self):
        res = super().action_post()
        for move in self:
            if move.is_invoice(include_receipts=True) and move.withholding_amount > 0:
                self._create_withholding_entry(move)
        return res

    def certify(self):
        """
        Sobrescreve o método `certify` do módulo `opc_certification_ao`.
        O objetivo é forçar o recálculo dos totais imediatamente antes da
        geração do hash para garantir que os dados estão corretos.
        """
        self._compute_amount()
        self._compute_withholding()
        return super().certify()

    def _create_withholding_entry(self, invoice):
        withholding_map = {}
        for line in invoice.invoice_line_ids:
            if line.withholding_tax_id:
                tax = line.withholding_tax_id
                amount = line.price_subtotal * (tax.percentage / 100)
                if tax in withholding_map:
                    withholding_map[tax] += amount
                else:
                    withholding_map[tax] = amount

        # Encontrar a linha de contas a receber/pagar de forma robusta,
        # verificando as contas configuradas no parceiro.
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

        # O lançamento da retenção deve ser criado num diário de "Operações Diversas"
        # para não ser confundido com uma fatura por outros módulos (ex: certificação).
        misc_journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', invoice.company_id.id)
        ], limit=1)
        if not misc_journal:
            raise UserError(_("Não foi encontrado um diário do tipo 'Operações Diversas'. Por favor, crie um para continuar."))

        for tax, amount in withholding_map.items():
            withholding_account = tax.account_id
            if not withholding_account:
                raise UserError(_("A conta contabilística para a retenção '%s' não está definida.") % tax.name)

            move_vals = {
                'move_type': 'entry',
                'partner_id': invoice.partner_id.id,
                'journal_id': misc_journal.id,
                'date': invoice.date,
                'ref': _('Retenção na Fatura: %s (%s)') % (invoice.name, tax.name),
                'line_ids': [
                    (0, 0, {
                        'name': _('Valor da Retenção (%s%%)') % tax.percentage,
                        'debit': amount,
                        'credit': 0.0,
                        'account_id': arp_line.account_id.id,
                        'partner_id': invoice.partner_id.id,
                    }),
                    (0, 0, {
                        'name': _('Provisão para %s') % tax.name,
                        'debit': 0.0,
                        'credit': amount,
                        'account_id': withholding_account.id,
                        'partner_id': invoice.partner_id.id,
                    }),
                ]
            }
            withholding_move = self.env['account.move'].create(move_vals)
            withholding_move.action_post()

            (arp_line | withholding_move.line_ids.filtered(lambda l: l.account_id == arp_line.account_id)).reconcile()

    @api.model
    def create(self, vals):
        """
        Sobrescreve o método create para garantir que o campo `withholding_tax_id` não é perdido.
        """
        # Extrair os valores de retenção das linhas de produto nos `vals` de entrada.
        withholding_values = []
        if 'invoice_line_ids' in vals:
            for line_command in vals.get('invoice_line_ids', []):
                if line_command and line_command[0] == 0:
                    line_vals = line_command[2]
                    withholding_values.append(line_vals.get('withholding_tax_id'))

        # Chamar o `create` original. O Odoo pode limpar o campo `withholding_tax_id` aqui.
        move = super(AccountMove, self).create(vals)

        # Restaurar os valores de retenção, fazendo a correspondência de forma robusta.
        # Filtramos as linhas para ignorar as que são de impostos, pois estas não
        # correspondem diretamente às linhas de entrada.
        product_lines = move.invoice_line_ids.filtered(lambda line: not line.tax_line_id)

        if withholding_values and len(product_lines) == len(withholding_values):
            for i, line in enumerate(product_lines):
                wht_id = withholding_values[i]
                if wht_id and not line.withholding_tax_id:
                    line.withholding_tax_id = wht_id

        return move

    def write(self, vals):
        """
        Sobrescreve o método write para garantir que o campo `withholding_tax_id` não é perdido.
        """
        if 'invoice_line_ids' in vals:
            # Guardar os IDs das linhas existentes para identificar as novas mais tarde.
            existing_line_ids = self.invoice_line_ids.ids

            # Extrair valores de retenção antes que se percam.
            line_updates = {}
            new_line_withholding = []
            for command in vals['invoice_line_ids']:
                if command[0] == 1:  # Update
                    if 'withholding_tax_id' in command[2]:
                        line_updates[command[1]] = command[2]['withholding_tax_id']
                elif command[0] == 0:  # Create
                    new_line_withholding.append(command[2].get('withholding_tax_id'))

            res = super(AccountMove, self).write(vals)

            # Restaurar valores.
            if line_updates:
                for line_id, wht_id in line_updates.items():
                    self.env['account.move.line'].browse(line_id).write({'withholding_tax_id': wht_id})
            
            if new_line_withholding:
                self.ensure_one() # Assumimos que estamos a editar uma fatura de cada vez.
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
        domain="[('company_id', '=', company_id)]",
        help="Selecione o tipo de retenção a aplicar nesta linha da fatura."
    )