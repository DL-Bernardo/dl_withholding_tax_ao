from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    withholding_tax_id = fields.Many2one(
        'withholding.tax',
        string="Retenção na Fonte Padrão",
        help="Define uma retenção na fonte padrão para este parceiro."
    )