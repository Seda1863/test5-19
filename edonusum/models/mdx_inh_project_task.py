# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError

class MdxInhProjectTask(models.Model):
    _inherit = 'project.task'
