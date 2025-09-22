{
    'name': 'Withholding Tax Angola',
    'version': '17.0.1.0.0',
    'summary': 'Withholding Tax Management (Angola)',
    'description': """
Module to support Withholding Tax in Angola.

Features:
- Setting up withholding tax rates
- Applying withholding tax on invoice lines
- Automatic calculation of retention and net payable
- Display on invoices, receipts and SAFT export (legal requirement in Angola)
    """,
    'author': 'DIGITALUB ANGOLA',
    'website': 'https://www.digitalub.ao',
    'license': 'AGPL-3',
    'category': 'Accounting',
    'depends': ['account'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/withholding_tax_data.xml',
        'views/withholding_tax_views.xml',
        'views/account_move_views.xml',
        'views/res_partner_views.xml',
        'views/withholding_report_wizard_views.xml',
        'report/reports.xml',
        'report/report_withholding.xml',
        'report/report_payment_receipt.xml',
    ],
    'installable': True,
    'application': True,
    # Odoo Apps Store info
    'price': 87.0,
    'currency': 'USD',
    'images': ['static/description/banner.png'],
}
