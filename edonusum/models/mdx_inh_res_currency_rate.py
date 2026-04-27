# -*- coding: utf-8 -*-

import xml.etree.ElementTree as ET
import json

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

class MdxInhResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    forex_buying = fields.Float(string="Forex Buying", store=True)
    forex_selling = fields.Float(string="Forex Selling", store=True)
    banknote_buying = fields.Float(string="Banknote Buying", store=True)
    banknote_selling = fields.Float(string="Banknote Selling", store=True)