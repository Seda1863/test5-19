# -*- coding: utf-8 -*-
{
    "name": "MDX Audit Lockdown",
    "version": "18.0.1.0.0",
    "category": "Technical",
    "summary": "Restrict technical tracking/audit screens to system administrators only",
    "license": "LGPL-3",
    "author": "MindDX",
    "depends": ["mail"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/audit_log_views.xml",
        "views/audit_rule_views.xml",
        "views/res_users_views.xml",
        "views/res_config_settings_views.xml",
        "views/menu.xml",
        "views/mail_tracking_lockdown.xml",
    ],
    "installable": True,
    "application": False,
}