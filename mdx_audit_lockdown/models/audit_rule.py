# -*- coding: utf-8 -*-
from odoo import api, fields, models


class MdxAuditRule(models.Model):
    _name = "mdx.audit.rule"
    _description = "MDX Audit Rule"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    name = fields.Char(required=True)

    # hedef model (boşsa tüm modellere uygulanır)
    model_ids = fields.Many2many(
        "ir.model",
        string="Models (optional - leave empty for all)",
        ondelete="cascade",
    )

    # teknik isimler (Many2many için computed)
    models = fields.Char(
        string="Models (Technical)",
        compute="_compute_models",
        store=True,
        readonly=True,
        help="Comma-separated list of model names",
    )

    # hangi operasyonlar
    track_create = fields.Boolean(string="Track Create", default=False)
    track_write = fields.Boolean(string="Track Write", default=True)
    track_unlink = fields.Boolean(string="Track Delete", default=False)

    # hangi alanlar (boş ise: write'ta vals gelen her field için log basar)
    field_ids = fields.Many2many(
        "ir.model.fields",
        string="Tracked Fields",
    )
    
    # hangi alanlar HARIÇ (boşsa etkisi yok, sadece Tracked Fields boşsa anlamlı)
    excluded_field_ids = fields.Many2many(
        "ir.model.fields",
        "mdx_audit_rule_excluded_fields_rel",
        "rule_id",
        "field_id",
        string="Excluded Fields",
        help="If 'Tracked Fields' is empty (track all), these fields will be ignored."
    )

    # kimler için geçerli
    user_ids = fields.Many2many("res.users", "mdx_audit_rule_users_rel", "rule_id", "user_id", string="Users (optional)")
    group_ids = fields.Many2many("res.groups", string="Groups (optional)")
    
    # kimler hariç tutulacak (örn: OdooBot)
    excluded_user_ids = fields.Many2many(
        "res.users", 
        "mdx_audit_rule_excluded_users_rel", 
        "rule_id", 
        "user_id", 
        string="Excluded Users",
        help="Selected users will never be logged by this rule, even if they match other criteria."
    )

    @api.depends("model_ids")
    def _compute_models(self):
        for rec in self:
            if rec.model_ids:
                rec.models = ",".join(m.model for m in rec.model_ids)
            else:
                rec.models = "*all*"

    def _rule_applies_to_model(self, model_name):
        """Rule geçerli mi bu model'e? Boşsa tüm modeller."""
        self.ensure_one()
        if not self.model_ids:
            return True  # Tüm modeller için geçerli
        return any(m.model == model_name for m in self.model_ids)

    def _rule_applies_to_user(self, user):
        """User/Group filtreleri boşsa herkese uygula."""
        self.ensure_one()
        
        # 1. Check Exclusion first - if user is excluded, return False immediately
        if self.excluded_user_ids and user in self.excluded_user_ids:
            return False

        # 2. Check Inclusion (whitelist)
        # If user_ids is set, user MUST be in user_ids
        if self.user_ids and user not in self.user_ids:
            return False
            
        # If group_ids is set, user MUST belong to at least one group
        if self.group_ids and not any(user in g.users for g in self.group_ids):
            return False
            
        return True

    def action_view_logs(self):
        """Open audit logs filtered by this rule (and users if set)."""
        self.ensure_one()
        action = self.env.ref("mdx_audit_lockdown.action_mdx_audit_log").read()[0]

        # Always filter by this rule
        domain = [("rule_id", "=", self.id)]

        # If the rule is restricted to specific users, only show those users' logs
        if self.user_ids:
            domain.append(("user_id", "in", self.user_ids.ids))

        action.update({
            "domain": domain,
            "context": {},
        })
        return action