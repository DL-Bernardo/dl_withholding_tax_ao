from odoo.tests.common import tagged, TransactionCase
from odoo.exceptions import UserError

@tagged('post_install', '-at_install')
class TestWithholding(TransactionCase):

    @classmethod
    def setUpClass(cls, *args, **kwargs):
        super().setUpClass(*args, **kwargs)
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        # Company and Accounts
        cls.company = cls.env.ref('base.main_company')
        cls.account_receivable = cls.env['account.account'].search([
            ('company_id', '=', cls.company.id), ('account_type', '=', 'asset_receivable')
        ], limit=1)
        cls.account_payable = cls.env['account.account'].search([
            ('company_id', '=', cls.company.id), ('account_type', '=', 'liability_payable')
        ], limit=1)
        cls.wt_account_6_5 = cls.env['account.account'].create({
            'name': 'Withholding Tax 6.5%',
            'code': 'WT_PAY_65',
            'account_type': 'liability_payable',
            'company_id': cls.company.id,
        })
        cls.wt_account_10 = cls.env['account.account'].create({
            'name': 'Withholding Tax 10%',
            'code': 'WT_PAY_10',
            'account_type': 'liability_payable',
            'company_id': cls.company.id,
        })
        cls.expense_account = cls.env['account.account'].create({
            'name': 'Test Expense',
            'code': 'EXP_TEST',
            'account_type': 'expense',
            'company_id': cls.company.id,
        })

        # Journal
        cls.journal = cls.env['account.journal'].search([
            ('type', '=', 'purchase'), ('company_id', '=', cls.company.id)
        ], limit=1)

        # Withholding Tax Rates
        cls.wt_rate_6_5 = cls.env['withholding.tax'].create({
            'name': 'Test Rate 6.5%',
            'code': 'T6.5',
            'tax_type': 'ii',
            'percentage': 6.5,
            'account_id': cls.wt_account_6_5.id,
            'company_id': cls.company.id,
        })
        cls.wt_rate_10 = cls.env['withholding.tax'].create({
            'name': 'Test Rate 10%',
            'code': 'T10',
            'tax_type': 'iac',
            'percentage': 10,
            'account_id': cls.wt_account_10.id,
            'company_id': cls.company.id,
        })

        # Partner and Products
        cls.partner = cls.env['res.partner'].create({'name': 'Test Supplier'})
        cls.product_service = cls.env['product.product'].create({
            'name': 'Test Service',
            'type': 'service',
            'standard_price': 1000.0,
            'property_account_expense_id': cls.expense_account.id,
        })
        cls.product_consulting = cls.env['product.product'].create({
            'name': 'Test Consulting',
            'type': 'service',
            'standard_price': 500.0,
            'property_account_expense_id': cls.expense_account.id,
        })

    def test_01_single_withholding_on_vendor_bill(self):
        """Test the full flow of a single withholding tax on a vendor bill line."""
        # 1. Create a vendor bill with one line having a withholding tax
        invoice = self.env['account.move'].create({
            'partner_id': self.partner.id,
            'move_type': 'in_invoice',
            'journal_id': self.journal.id,
            'invoice_date': '2025-01-15',
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product_service.id,
                'quantity': 1,
                'price_unit': 1000.00,
                'withholding_tax_id': self.wt_rate_6_5.id,
            })]
        })

        # 2. Check calculation
        # amount_untaxed = 1000
        # withholding = 1000 * 6.5% = 65
        # total = 1000
        # net = 1000 - 65 = 935
        self.assertAlmostEqual(invoice.withholding_amount, 65.0, places=2)
        self.assertAlmostEqual(invoice.amount_total, 1000.0, places=2)
        self.assertAlmostEqual(invoice.net_amount, 935.0, places=2)

        # 3. Post the invoice
        invoice._post()
        self.assertEqual(invoice.state, 'posted')

        # 4. Check that a new journal entry for the withholding was created
        wt_move = self.env['account.move'].search([
            ('ref', '=', f'Retenção na Fatura: {invoice.name} ({self.wt_rate_6_5.name})')
        ])
        self.assertTrue(wt_move, "Withholding journal entry was not created.")
        self.assertEqual(len(wt_move), 1)

        # 5. Check the lines of the withholding entry
        debit_line = wt_move.line_ids.filtered(lambda l: l.debit > 0)
        credit_line = wt_move.line_ids.filtered(lambda l: l.credit > 0)
        self.assertAlmostEqual(debit_line.debit, 65.0)
        self.assertEqual(debit_line.account_id, self.account_payable)
        self.assertAlmostEqual(credit_line.credit, 65.0)
        self.assertEqual(credit_line.account_id, self.wt_account_6_5)

        # 6. Check reconciliation and residual amount
        self.assertAlmostEqual(invoice.amount_residual, 935.0)

    def test_02_multiple_withholdings_on_vendor_bill(self):
        """Test a vendor bill with multiple lines and different withholding taxes."""
        # 1. Create a vendor bill with multiple lines
        invoice = self.env['account.move'].create({
            'partner_id': self.partner.id,
            'move_type': 'in_invoice',
            'journal_id': self.journal.id,
            'invoice_date': '2025-01-20',
            'invoice_line_ids': [
                (0, 0, { # Line 1 with 6.5% WT
                    'product_id': self.product_service.id,
                    'quantity': 1,
                    'price_unit': 1000.00,
                    'withholding_tax_id': self.wt_rate_6_5.id,
                }),
                (0, 0, { # Line 2 with 10% WT
                    'product_id': self.product_consulting.id,
                    'quantity': 1,
                    'price_unit': 500.00,
                    'withholding_tax_id': self.wt_rate_10.id,
                }),
                (0, 0, { # Line 3 with no WT
                    'product_id': self.product_service.id,
                    'name': 'Line with no withholding',
                    'quantity': 1,
                    'price_unit': 200.00,
                    'withholding_tax_id': False,
                })
            ]
        })

        # 2. Check calculation
        # amount_untaxed = 1000 + 500 + 200 = 1700
        # withholding_1 = 1000 * 6.5% = 65
        # withholding_2 = 500 * 10% = 50
        # total_withholding = 65 + 50 = 115
        # total = 1700
        # net = 1700 - 115 = 1585
        self.assertAlmostEqual(invoice.amount_untaxed, 1700.0, places=2)
        self.assertAlmostEqual(invoice.withholding_amount, 115.0, places=2)
        self.assertAlmostEqual(invoice.amount_total, 1700.0, places=2)
        self.assertAlmostEqual(invoice.net_amount, 1585.0, places=2)

        # 3. Post the invoice
        invoice._post()
        self.assertEqual(invoice.state, 'posted')

        # 4. Check that two separate journal entries were created
        wt_move_1 = self.env['account.move'].search([
            ('ref', '=', f'Retenção na Fatura: {invoice.name} ({self.wt_rate_6_5.name})')
        ])
        wt_move_2 = self.env['account.move'].search([
            ('ref', '=', f'Retenção na Fatura: {invoice.name} ({self.wt_rate_10.name})')
        ])
        self.assertTrue(wt_move_1, "6.5% withholding journal entry was not created.")
        self.assertTrue(wt_move_2, "10% withholding journal entry was not created.")

        # 5. Check WT entry 1 (6.5%)
        self.assertAlmostEqual(wt_move_1.amount_total, 65.0)
        self.assertEqual(wt_move_1.line_ids.filtered(lambda l:l.credit > 0).account_id, self.wt_account_6_5)

        # 6. Check WT entry 2 (10%)
        self.assertAlmostEqual(wt_move_2.amount_total, 50.0)
        self.assertEqual(wt_move_2.line_ids.filtered(lambda l:l.credit > 0).account_id, self.wt_account_10)

        # 7. Check residual amount
        self.assertAlmostEqual(invoice.amount_residual, 1585.0)