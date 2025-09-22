🇦🇴 DL Withholding Tax Angola (dl_withholding_tax_ao)

💡 This module adds Withholding Tax functionality to Odoo 15, fully aligned with the Angolan tax requirements.

✨ Features

Configure different types of withholding tax.

Apply withholding tax directly on invoice lines.

Automatic calculation of the withholding amount and net payable.

Display of withholding values on the invoice form and PDF reports.

SAFT Angola integration: the module extends the SAFT file by adding the withholding_tax field, complying with legal requirements from AGT (General Tax Administration of Angola).

⚙️ Installation

Copy the dl_withholding_tax_ao folder into your Odoo addons directory.

Restart the Odoo service.

Activate the Developer Mode.

Go to Apps → click Update Apps List.

Search for "Withholding Tax Angola" and click Install.

🧑‍💻 Usage
➤ Configure withholding tax rates

Go to Accounting > Configuration > Withholding Tax.

Create or edit the tax rates as required.
(Some predefined rates are already included in the module).

➤ Apply withholding on an invoice

When creating a vendor bill, select the withholding tax rate in the "Withholding" field on the invoice line.

The system will automatically calculate the withholding amount and update the net payable at the bottom of the invoice.

📊 Practical Example

Invoice amount: 100,000 Kz

Withholding Tax: 6.5%

Withholding amount: 6,500 Kz

Net payable: 93,500 Kz
