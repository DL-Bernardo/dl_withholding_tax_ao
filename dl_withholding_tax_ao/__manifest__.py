{
    'name': 'Angola Withholding Tax 6.5% (Retenção na Fonte)',
    'version': '18.0.1.0.7',
    'summary': 'Automated Withholding Tax (Retenção na Fonte 6.5%, IP 15%, IVA Cativo) on Quotations, Invoices & Vendor Bills for Angola',
    'description': """
Withholding Tax Management for Angola (Retenção na Fonte 6.5%)
==============================================================

Automate Angolan legal withholding tax (Retenção na Fonte) calculation and reporting on Sales Quotations, Customer Invoices, and Vendor Bills:
- Setup custom withholding rates and base calculation rules (6.5% II standard services, 15% non-resident, 15% IP rental, 50%/100% IVA Cativo).
- Line-by-line withholding application on sales quotations/orders, vendor bills, and customer invoices.
- Automatic transfer of withholding tax from confirmed sales orders to customer invoices.
- Automated gross calculation, withholding retention amount, and net payable.
- Withholding tax summary tables on PDF reports and monthly statement reports.
- Ready for AGT fiscal integration and SAFT-AO XML reporting.
- 100% compatible with Odoo 15, 16, 17, 18, 19 & 20 (Community, Enterprise & Odoo.sh).
    """,
    'author': 'DIGITALUB ANGOLA, LDA',
    'website': 'https://www.digitalub.ao',
    'support': 'suporte@digitalub.ao',
    'license': 'AGPL-3',
    'category': 'Accounting',
    'depends': ['account', 'sale'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/withholding_tax_data.xml',
        'views/withholding_tax_views.xml',
        'views/account_move_views.xml',
        'views/sale_order_views.xml',
        'views/res_partner_views.xml',
        'views/withholding_report_wizard_views.xml',
        'report/reports.xml',
        'report/report_withholding.xml',
        'report/report_sale_order_withholding.xml',
        'report/report_payment_receipt.xml',
    ],
    'installable': True,
    'application': True,
    # Odoo Apps Store info
    'price': 79.0,
    'currency': 'USD',
    'images': ['static/description/banner.png'],
}
