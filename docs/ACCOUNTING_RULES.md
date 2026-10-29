# Current money and accounting behavior

This foundation has **no double-entry accounting module** and must not be used to assert profit, balance-sheet, tax, or professional-accounting results.

- Product prices and costs are entered as decimal values. Checkout reads the selling price from the server-side product record and multiplies it by quantity with `Decimal`; line totals are rounded to two decimal places (`ROUND_HALF_UP`) in the organization's configured currency.
- This release does not configure, calculate or retain tax snapshots, discounts, COGS postings, payment fees, journal entries or credit notes.
- Cash checkout is represented as a paid sale. A bank transfer is a pending sale because an operator has not verified settlement. Customer credit is recorded unpaid. No card or mobile-money collection integration is configured.
- Dashboard “confirmed sales today” is the sum of sales with `status=paid` inside the organization's local calendar day. It is not a P&L revenue figure and does not include pending/unpaid sales.
- Inventory is represented by quantity ledger movements, but there is no valued inventory ledger or accounting reconciliation.

Tax and financial rules must be validated by qualified local accounting/tax professionals against current applicable requirements before these capabilities are built or relied on.
