# Copyright 2024 Camptocamp
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
#
from odoo import Command, api, fields, models
from odoo.tools.mail import email_split


class AccountMoveSendWizard(models.TransientModel):
    _inherit = "account.move.send.wizard"

    partner_cc_ids = fields.Many2many(
        "res.partner",
        "account_move_send_wizard_res_partner_cc_rel",
        "wizard_id",
        "partner_id",
        string="Cc",
        compute="_compute_mail_partner_cc_bcc_ids",
        store=True,
        readonly=False,
    )
    partner_bcc_ids = fields.Many2many(
        "res.partner",
        "account_move_send_wizard_res_partner_bcc_rel",
        "wizard_id",
        "partner_id",
        string="Bcc",
        compute="_compute_mail_partner_cc_bcc_ids",
        store=True,
        readonly=False,
    )

    # -------------------------------------------------------------------------
    # DEFAULTS
    # -------------------------------------------------------------------------

    @api.model
    def default_get(self, fields_list):
        # EXTENDS 'base'
        results = super().default_get(fields_list)
        company = self.env.company
        partner_cc = company.default_partner_cc_ids
        if partner_cc:
            results["partner_cc_ids"] = [Command.set(partner_cc.ids)]
        partner_bcc = company.default_partner_bcc_ids
        if partner_bcc:
            results["partner_bcc_ids"] = [Command.set(partner_bcc.ids)]
        return results

    @api.model
    def _get_default_mail_partner_ids(self, move, mail_template, mail_lang):
        # EXTENDS 'account': the template Cc goes to partner_cc_ids, not to To,
        # unless the same partner is also a To recipient of the template.
        partners = super()._get_default_mail_partner_ids(move, mail_template, mail_lang)
        partners_cc = self._get_template_partners(
            move, mail_template, mail_lang, "email_cc"
        )
        if not partners_cc:
            return partners
        partners_to = self.env["res.partner"]
        if mail_template.email_to:
            email_to = self._get_mail_default_field_value_from_template(
                mail_template, mail_lang, move, "email_to"
            )
            partners_to = move._partner_find_from_emails_single(
                email_split(email_to or ""), no_create=True
            )
        if mail_template.partner_to:
            partner_to = self._get_mail_default_field_value_from_template(
                mail_template, mail_lang, move, "partner_to"
            )
            partners_to |= (
                self.env["res.partner"]
                .sudo()
                .browse(mail_template._parse_partner_to(partner_to))
                .exists()
            )
        return partners - (partners_cc - partners_to)

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------
    def _get_template_partners(self, move, mail_template, mail_lang, field_name):
        """Partners of a rendered template address field (email_cc, email_bcc).

        Like 'account', a template using the default recipients is ignored:
        its Cc / Bcc fields are hidden on the template form.
        """
        partners = self.env["res.partner"]
        if (
            not mail_template
            or mail_template.use_default_to
            or not mail_template[field_name]
        ):
            return partners
        emails = self._get_mail_default_field_value_from_template(
            mail_template, mail_lang, move, field_name
        )
        return move._partner_find_from_emails_single(
            email_split(emails or ""), no_create=False
        )

    @api.depends("template_id", "lang")
    def _compute_mail_partner_cc_bcc_ids(self):
        company = self.env.company
        for wizard in self:
            if not wizard.template_id:
                wizard.partner_cc_ids = company.default_partner_cc_ids
                wizard.partner_bcc_ids = company.default_partner_bcc_ids
                continue
            wizard.partner_cc_ids = wizard._get_template_partners(
                wizard.move_id, wizard.template_id, wizard.lang, "email_cc"
            )
            wizard.partner_bcc_ids = wizard._get_template_partners(
                wizard.move_id, wizard.template_id, wizard.lang, "email_bcc"
            )

    @api.model
    def _send_mail(self, move, mail_template, **kwargs):
        move_with_context = move.with_context(
            is_from_composer=True,
            partner_cc_ids=self.partner_cc_ids,
            partner_bcc_ids=self.partner_bcc_ids,
        )
        return super()._send_mail(move_with_context, mail_template, **kwargs)
