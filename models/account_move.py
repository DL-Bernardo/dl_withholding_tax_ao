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

        # Obter o diário de retenção a partir da configuração da empresa.
        # Este diário é usado para criar o lançamento de contrapartida da retenção.
        misc_journal = invoice.company_id.withholding_journal_id
        if not misc_journal:
            raise UserError(_("O diário para lançamentos de retenção não está configurado. Por favor, defina-o nas configurações da empresa."))

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
        Sobrescreve o método `create` para contornar um problema específico do Odoo
        em que o valor do campo `withholding_tax_id` pode ser perdido durante a
        criação da fatura, especialmente quando há interações com o cálculo de
        impostos (que pode recriar ou limpar as linhas).

        WORKAROUND:
        1. Antes de chamar o `super().create()`, os valores de `withholding_tax_id`
           de cada linha são extraídos e guardados numa lista temporária.
        2. O método `super().create()` é chamado, o que pode resultar na perda
           dos valores de retenção.
        3. Após a criação, os valores guardados são restaurados nas linhas da fatura
           recém-criada, fazendo a correspondência pela ordem das linhas.
        """
        withholding_values = []
        if 'invoice_line_ids' in vals:
            for line_command in vals.get('invoice_line_ids', []):
                if line_command and line_command[0] == 0:  # (0, 0, {values})
                    line_vals = line_command[2]
                    withholding_values.append(line_vals.get('withholding_tax_id'))

        move = super(AccountMove, self).create(vals)

        product_lines = move.invoice_line_ids.filtered(lambda line: not line.tax_line_id)

        if withholding_values and len(product_lines) == len(withholding_values):
            for i, line in enumerate(product_lines):
                wht_id = withholding_values[i]
                if wht_id and not line.withholding_tax_id:
                    line.withholding_tax_id = wht_id

        return move

    def write(self, vals):
        """
        Sobrescreve o método `write` para garantir que o campo `withholding_tax_id`
        não é perdido durante a atualização de uma fatura. A lógica é semelhante
        à do método `create`.

        WORKAROUND:
        1. Antes de chamar `super().write()`, os valores de `withholding_tax_id`
           são extraídos dos comandos de atualização (1) e criação (0) de linhas.
        2. O `super().write()` é chamado.
        3. Os valores são restaurados nas linhas correspondentes.
        """
        if 'invoice_line_ids' in vals:
            existing_line_ids = self.invoice_line_ids.ids

            line_updates = {}
            new_line_withholding = []
            for command in vals['invoice_line_ids']:
                if command[0] == 1:  # (1, id, {values}) - Update
                    if 'withholding_tax_id' in command[2]:
                        line_updates[command[1]] = command[2]['withholding_tax_id']
                elif command[0] == 0:  # (0, 0, {values}) - Create
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
        domain="[('company_id', '=', company_id)]",
        help="Selecione o tipo de retenção a aplicar nesta linha da fatura."
    )