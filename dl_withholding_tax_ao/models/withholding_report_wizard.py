from odoo import models, fields, api

class WithholdingReportWizard(models.TransientModel):
    _name = 'withholding.report.wizard'
    _description = 'Wizard para Mapa de Retenção na Fonte'

    date_from = fields.Date(string="Data de Início", required=True)
    date_to = fields.Date(string="Data de Fim", required=True)
    company_id = fields.Many2one('res.company', string="Empresa", required=True,
                                 default=lambda self: self.env.company)

    def print_report(self):
        self.ensure_one()
        domain = [
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('withholding_amount', '>', 0),
            ('state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
        ]
        invoices = self.env['account.move'].search(domain)

        if not invoices:
            raise models.UserError("Não foram encontradas faturas com retenção no período selecionado.")

        data = {
            'doc_ids': invoices.ids,
            'doc_model': 'account.move',
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company': self.company_id,
        }
        return self.env.ref('dl_withholding_tax_ao.action_report_withholding').report_action(invoices, data=data)