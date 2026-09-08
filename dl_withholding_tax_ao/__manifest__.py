{
    'name': 'Angola Withholding Tax 6.5% (Retenção na Fonte)',
    'version': '17.0.1.0.3',
    'summary': 'Automated Withholding Tax (Retenção na Fonte 6.5%) & AGT Fiscal Compliance for Angola',
    'description': """
Withholding Tax Management for Angola (Retenção na Fonte 6.5%)
==============================================================

Automate Angolan legal withholding tax (Retenção na Fonte) calculation and reporting on Invoices and Vendor Bills:
- Setup custom withholding rates and base calculation rules (6.5% standard services, rental, royalties).
- Line-by-line withholding application on vendor bills and customer invoices.
- Automated gross invoice calculation, withholding retention amount, and net payable.
- Withholding tax certificates and statement PDF reports.
- Ready for AGT fiscal integration and SAFT-AO XML reporting.
- 100% compatible with Odoo 17 Community, Enterprise & Odoo.sh.
    """,
    'author': 'DIGITALUB ANGOLA, LDA',
    'website': 'https://www.digitalub.ao',
    'support': 'suporte@digitalub.ao',
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
    'price': 79.0,
    'currency': 'EUR',
    'images': ['static/description/banner.png'],
}
