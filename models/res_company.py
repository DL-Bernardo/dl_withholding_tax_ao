from odoo import fields, models

class ResCompany(models.Model):
    _inherit = 'res.company'

    withholding_journal_id = fields.Many2one(
        'account.journal',
        string="Diário de Retenção",
        domain="[('type', '=', 'general')]",
        help="Selecione o diário a ser utilizado para os lançamentos de retenção na fonte."
    )