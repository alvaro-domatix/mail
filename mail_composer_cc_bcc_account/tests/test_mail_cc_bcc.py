# Copyright 2023 Camptocamp
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tools import email_normalize, email_split

from odoo.addons.account.tests.test_account_move_send import TestAccountMoveSendCommon
from odoo.addons.mail.tests.common import MailCommon


@tagged("post_install_l10n", "post_install", "-at_install")
class TestMailCcBccInvoice(TestAccountMoveSendCommon, MailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env["res.partner"]
        cls.partner = Partner.create(
            {"name": "Customer", "email": "customer@example.com"}
        )
        cls.partner_cc = Partner.create({"name": "Cc", "email": "cc@example.com"})
        cls.partner_bcc = Partner.create({"name": "Bcc", "email": "bcc@example.com"})
        cls.template = cls.env["mail.template"].create(
            {
                "name": "Invoice with Cc",
                "model_id": cls.env["ir.model"]._get_id("account.move"),
                "subject": "Invoice {{ object.name }}",
                "body_html": "<p>Your invoice</p>",
                "use_default_to": False,
                "partner_to": "{{ object.partner_id.id }}",
                "email_cc": "{{ object.partner_id.email and 'cc@example.com' }}",
            }
        )

    def _header_addresses(self, header):
        return {
            tuple(sorted(email_normalize(a) for a in email_split(email[header] or "")))
            for email in self.emails
        }

    def test_invoice_mail_cc_bcc(self):
        invoice = self.init_invoice(
            "out_invoice", partner=self.partner, amounts=[1000], post=True
        )
        wizard = self.create_send_and_print(
            invoice,
            sending_methods=["email", "manual"],
            mail_partner_ids=self.partner,
            partner_cc_ids=self.partner_cc,
            partner_bcc_ids=self.partner_bcc,
        )

        with self.mock_mail_gateway():
            wizard.action_send_and_print()
        self.assertEqual(len(self._mails), 3)

        message = self._get_mail_message(invoice)
        self.assertEqual(len(message.mail_ids), 1)

        # Only 3 partners (from default_cc/bcc of company) notified
        self.assertEqual(len(message.notified_partner_ids), 3)
        self.assertEqual(len(message.notification_ids), 3)

    def test_invoice_template_cc(self):
        """The rendered template Cc is a real Cc, not one more To recipient"""
        invoice = self.init_invoice(
            "out_invoice", partner=self.partner, amounts=[1000], post=True
        )
        wizard = self.create_send_and_print(
            invoice, sending_methods=["email"], template_id=self.template.id
        )
        self.assertEqual(wizard.partner_cc_ids, self.partner_cc)
        self.assertEqual(wizard.mail_partner_ids, self.partner)

        with self.mock_mail_gateway():
            wizard.action_send_and_print()
        self.assertEqual(
            sorted(
                address for email in self.emails for address in email["smtp_to_list"]
            ),
            ["cc@example.com", "customer@example.com"],
        )
        self.assertEqual(self._header_addresses("msg_to"), {("customer@example.com",)})
        self.assertEqual(self._header_addresses("msg_cc"), {("cc@example.com",)})

    def test_invoice_template_cc_with_default_recipients(self):
        """A template using the default recipients ignores its hidden Cc"""
        self.template.use_default_to = True
        invoice = self.init_invoice(
            "out_invoice", partner=self.partner, amounts=[1000], post=True
        )
        wizard = self.create_send_and_print(
            invoice, sending_methods=["email"], template_id=self.template.id
        )
        self.assertFalse(wizard.partner_cc_ids)
        self.assertNotIn(self.partner_cc, wizard.mail_partner_ids)
