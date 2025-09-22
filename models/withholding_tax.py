from odoo import models, fields

class WithholdingTax(models.Model):
    _name = 'withholding.tax'
    _description = 'Retenção na Fonte'

    name = fields.Char(string="Nome", required=True)
    code = fields.Char(string="Código", required=True)
    tax_type = fields.Selection([
        ('ii', 'Imposto Industrial'),
        ('ipu', 'Imposto Predial Urbano'),
        ('iac', 'Imposto sobre Aplicação de Capitais')
    ], string="Tipo de Imposto", required=True, default='ii')
    percentage = fields.Float(string="% Imposto", required=True)
    account_id = fields.Many2one(
        'account.account',
        string="Conta Contabilística",
        required=False,
        domain="[('deprecated', '=', False), ('company_id', '=', company_id)]",
        help="Conta para registar o valor da retenção."
    )
    company_id = fields.Many2one(
        'res.company',
        string="Empresa",
        required=True,
        default=lambda self: self.env.company
    )