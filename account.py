# This file is part of account_bank module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.model import Workflow, ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, Bool
from trytond.transaction import Transaction
__all__ = [
    'PaymentType',
    'Invoice',
    'Line',
    ]
__metaclass__ = PoolMeta


class PaymentType:
    __name__ = 'account.payment.type'

    account_bank = fields.Selection([
        ('none', 'None'),
        ('party', 'Party'),
        ('company', 'Company'),
        ], 'Account Bank', select=True, required=True)

    @staticmethod
    def default_account_bank():
        return 'none'


class Invoice:
    __name__ = 'account.invoice'

    account_bank_from = fields.Function(fields.Many2One('party.party',
            'Account Bank From', on_change_with=['party', 'payment_type']),
        'on_change_with_account_bank_from')
    bank_account = fields.Many2One('bank.account', 'Bank Account',
        domain=[
            ('owners', '=', Eval('account_bank_from')),
            ],
        states={
            'readonly': ~Eval('state').in_(['draft', 'validated']),
            'invisible': ~Bool(Eval('account_bank_from')),
            },
        depends=['party', 'payment_type', 'account_bank_from'])

    @classmethod
    def __setup__(cls):
        super(Invoice, cls).__setup__()
        cls.payment_type.on_change = ['payment_type', 'party']
        cls._error_messages.update({
                'invoice_without_bank_account': ('This invoice has no bank '
                    'account associated, but its payment type requires it.')
                })

    def on_change_with_account_bank_from(self, name=None):
        '''
        Sets the party where get bank account for this invoice.
        '''
        pool = Pool()
        Company = pool.get('company.company')
        if self.payment_type and self.party:
            payment_type = self.payment_type
            party = self.party
            if payment_type.account_bank == 'party':
                return party.id
            elif payment_type.account_bank == 'company':
                company = Transaction().context.get('company', False)
                return Company(company).party.id

    @classmethod
    def _get_bank_account(cls, payment_type, party, company):
        pool = Pool()
        Company = pool.get('company.company')
        Party = pool.get('party.party')

        party_fname = '%s_bank_account' % payment_type.kind
        if hasattr(Party, party_fname):
            account_bank = payment_type.account_bank
            if account_bank == 'company':
                party = company and Company(company).party
            if account_bank in ('company', 'party') and party:
                default_bank = getattr(party, party_fname)
                return default_bank

    def on_change_payment_type(self):
        '''
        Add account bank to account invoice when changes payment_type.
        '''
        res = {'bank_account': None}
        payment_type = self.payment_type
        party = self.party
        company = Transaction().context.get('company')
        if payment_type:
            bank_account = self._get_bank_account(payment_type, party, company)
            res['bank_account'] = bank_account and bank_account.id or None
        return res

    def on_change_party(self):
        '''
        Add account bank to account invoice when changes party.
        '''
        pool = Pool()
        PaymentType = pool.get('account.payment.type')

        res = super(Invoice, self).on_change_party()
        res['bank_account'] = None
        party = self.party
        company = Transaction().context.get('company')
        if res.get('payment_type'):
            payment_type = PaymentType(res['payment_type'])
            bank_account = self._get_bank_account(payment_type, party, company)
            res['bank_account'] = bank_account and bank_account.id or None
        return res

    def _get_move_line(self, date, amount):
        '''
        Add account bank to move line when post invoice.
        '''
        res = super(Invoice, self)._get_move_line(date, amount)
        if self.bank_account:
            res['bank_account'] = self.bank_account
        return res

    @classmethod
    def create(cls, vlist):
        pool = Pool()
        PaymentType = pool.get('account.payment.type')
        Party = pool.get('party.party')
        Company = pool.get('company.company')
        vlist = [x.copy() for x in vlist]
        for values in vlist:
            if (not 'bank_account' in values and 'payment_type' in values
                    and 'party' in values):
                party = Party(values['party'])
                company = Company(values.get('company',
                    Transaction().context.get('company'))).party
                if values.get('payment_type'):
                    payment_type = PaymentType(values['payment_type'])
                    bank_account = cls._get_bank_account(payment_type, party,
                        company)
                    values['bank_account'] = (bank_account and bank_account.id
                        or None)
        return super(Invoice, cls).create(vlist)

    @classmethod
    @ModelView.button
    @Workflow.transition('posted')
    def post(cls, invoices):
        '''
        Check up invoices that requires bank account because its payment type,
        has one
        '''
        for invoice in invoices:
            account_bank = (invoice.payment_type and
                invoice.payment_type.account_bank or 'none')
            if (invoice.payment_type and account_bank != 'none'
                    and not (account_bank in ('party', 'company')
                        and invoice.bank_account)):
                cls.raise_user_error('invoice_without_bank_account')
        super(Invoice, cls).post(invoices)


class Line:
    __name__ = 'account.move.line'

    account_bank_from = fields.Function(fields.Many2One('party.party',
            'Account Bank From', on_change_with=['party', 'payment_type']),
        'on_change_with_account_bank_from')
    bank_account = fields.Many2One('bank.account', 'Bank Account',
        domain=[
            # TODO: ('owners', '=', Eval('account_bank_from')),
            ],
        states={
                'readonly': Bool(Eval('reconciliation')),
            },
        depends=['party', 'payment_type', 'account_bank_from'])

    @classmethod
    def __setup__(cls):
        super(Line, cls).__setup__()
        if hasattr(cls, '_check_modify_exclude'):
            cls._check_modify_exclude.append('bank_account')
        cls.payment_type.on_change = ['payment_type', 'party']
        cls._error_messages.update({
                'party_without_bank_account': ('%s has no any %s bank '
                    'account.\nPlease set up one if you want to use this '
                    'payment type.'),
                })

    def _get_bank_account(self, payment_type, party, company):
        pool = Pool()
        Company = pool.get('company.company')
        Party = pool.get('party.party')

        party_fname = '%s_bank_account' % payment_type.kind
        if hasattr(Party, party_fname):
            account_bank = payment_type.account_bank
            if account_bank == 'company':
                party = company and Company(company).party
            if account_bank in ('company', 'party') and party:
                default_bank = getattr(party, party_fname)
                if not default_bank:
                    self.raise_user_error('party_without_bank_account',
                        (party.name, payment_type.kind))
                return default_bank

    def on_change_party(self):
        '''
        Add account bank to account move line when changes party.
        '''
        pool = Pool()
        PaymentType = pool.get('account.payment.type')

        res = super(Line, self).on_change_party()
        party = self.party
        company = Transaction().context.get('company', False)
        res['bank_account'] = None
        if res.get('payment_type'):
            payment_type = PaymentType(res['payment_type'])
            bank_account = self._get_bank_account(payment_type, party, company)
            res['bank_account'] = bank_account and bank_account.id or None
        return res

    def on_change_payment_type(self):
        '''
        Add account bank to account invoice when changes payment_type.
        '''
        res = {'bank_account': None}
        payment_type = self.payment_type
        party = self.party
        company = Transaction().context.get('company', False)
        if payment_type:
            bank_account = self._get_bank_account(payment_type, party, company)
            res['bank_account'] = bank_account and bank_account.id or None
        return res

    def on_change_with_account_bank_from(self, name=None):
        '''
        Sets the party where get bank account for this move line.
        '''
        pool = Pool()
        Company = pool.get('company.company')
        if self.payment_type and self.party:
            payment_type = self.payment_type
            party = self.party
            if payment_type.account_bank == 'party':
                return party.id
            elif payment_type.account_bank == 'company':
                company = Transaction().context.get('company', False)
                return Company(company).party.id
