from collections import defaultdict
import copy
from itertools import groupby
import operator

from tabulate import tabulate

OPMAP = {
    '=': 'eq',
    '==': 'eq',
    '!=': 'ne',
    '<': 'lt',
    '<=': 'le',
    '>': 'gt',
    '>=': 'ge',
    'in': 'contains',
}

ITEM_GETTERS = {
    'obj': getattr,
    'dict': dict.__getitem__,
    dict: dict.__getitem__,
}


def check_item_type(item_type):
    if item_type not in ITEM_GETTERS:

        def fmt(t):
            if isinstance(t, str):
                return f"'{t}'"
            else:
                return repr(t)

        item_types = ', '.join([fmt(t) for t in ITEM_GETTERS.keys()])
        raise ValueError(f'item_type must be one of {item_types}')


def get_field_val(item, field, item_type):
    getter = ITEM_GETTERS[item_type]
    val = getter(item, field)
    if callable(val):
        val = val()
    return val


class Query:
    def __init__(self, field, op, val, inverted=False):
        self.inverted = inverted
        self.field = field
        self.val = val
        self._op = op
        if isinstance(op, str):
            if op in OPMAP:
                op = OPMAP[op]
            self.op = getattr(operator, f'__{op}__')
        else:
            self.op = op

    def match(self, item, item_type):
        check_item_type(item_type)
        item_val = get_field_val(item, self.field, item_type)
        if self.op is operator.__contains__:
            retval = self.op(self.val, item_val)
        else:
            retval = self.op(item_val, self.val)
        if self.inverted:
            return not retval
        else:
            return retval

    def __repr__(self):
        return f"Query('{self.field}', '{self._op}', {repr(self.val)}, {self.inverted})"

    def __and__(self, other):
        return MultiQuery(self, other, operator.__and__)

    def __rand__(self, other):
        return MultiQuery(other, self, operator.__and__)

    def __or__(self, other):
        return MultiQuery(self, other, operator.__or__)

    def __ror__(self, other):
        return MultiQuery(other, self, operator.__or__)

    def __invert__(self):
        self.inverted = not self.inverted
        return self


class FuncQuery(Query):
    def __init__(self, func, inverted=False):
        self.func = func
        self.inverted = inverted

    def match(self, item, item_type):
        retval = self.func(item)
        if self.inverted:
            return not retval
        else:
            return retval

    def __repr__(self):
        return f"FuncQuery('{self.func}', {self.inverted})"


class MultiQuery(Query):
    def __init__(self, lhs, rhs, op):
        self.lhs = lhs
        self.rhs = rhs
        self.op = op

    def match(self, item, item_type):
        return self.op(self.lhs.match(item, item_type), self.rhs.match(item, item_type))

    def __repr__(self):
        opstr = '&' if self.op == operator.__and__ else '|'
        return '(' + repr(self.lhs) + opstr + repr(self.rhs) + ')'


class QueryList(list):
    def __init__(self, iterable=None, item_type='obj'):
        check_item_type(item_type)
        self.item_type = item_type
        if not iterable:
            iterable = []
        super().__init__(iterable)

    def __getitem__(self, i):
        # Returns a QueryList if a slice is used, else an individual item.
        if isinstance(i, slice):
            return QueryList(list.__getitem__(self, i), self.item_type)
        else:
            return list.__getitem__(self, i)

    def where(self, query=None, **kwargs):
        if kwargs:
            for k, v in kwargs.items():
                if '__' in k:
                    field, op = k.split('__')
                else:
                    field = k
                    op = '='
                new_query = Query(field, op, v)
                if query:
                    query = query & new_query
                else:
                    query = new_query

        new_items = []
        for item in self:
            if query.match(item, self.item_type):
                new_items.append(item)
        return QueryList(new_items)

    def select(self, field=None, fields=None, func=None):
        if sum([bool(field), bool(fields), bool(func)]) != 1:
            raise ValueError('Exactly one of "field", "fields", or "func" must be set')
        if field:
            return [get_field_val(item, field, self.item_type) for item in self]
        elif fields:
            return [
                tuple([get_field_val(item, f, self.item_type) for f in fields])
                for item in self
            ]
        elif func:
            return [func(item) for item in self]

    def count(self):
        return len(self)

    def first(self):
        return self[0]

    def last(self):
        return self[-1]

    def all(self, query):
        return len(self.where(query)) == len(self)

    def any(self, query):
        return len(self.where(query)) != 0

    def orderby(self, field=None, fields=None, key=None, order='ascending'):
        if sum([bool(field), bool(fields)]) != 1:
            raise ValueError('Exactly one of "field" or "fields" must be set')
        reverse = False if order == 'ascending' else True
        if not key:
            if field:
                key = lambda x: get_field_val(x, field, self.item_type)
            else:
                key = lambda x: tuple(
                    [get_field_val(x, f, self.item_type) for f in fields]
                )
        return QueryList(sorted(self, key=key, reverse=reverse))

    def groupby(self, field=None):
        group = defaultdict(list)
        for k, g in groupby(self, lambda x: get_field_val(x, field, self.item_type)):
            group[k].extend(g)
        for k, v in group.items():
            group[k] = QueryList(v)
        return QueryGroup(group)

    def aggregate(self, method, field=None, fields=None):
        if sum([bool(field), bool(fields)]) != 1:
            raise ValueError('Exactly one of "field" or "fields" must be set')
        if field:
            return method(self.select(field))
        elif fields:
            aggrs = []
            for field in fields:
                aggrs.append(self.aggregate(method, field))
            return aggrs

    def tabulate(self, fields):
        return tabulate(self.select(fields=fields), headers=fields)

    def __str__(self):
        return 'QueryList(\n' + ',\n'.join(' ' * 4 + str(i) for i in self) + '\n)'

    def __repr__(self):
        return 'QueryList([' + ', '.join(str(i) for i in self) + '])'


class QueryGroup(dict):
    def __init__(self, group):
        super().__init__(group)

    def count(self):
        return {k: len(ql) for k, ql in self.items()}

    def aggregate(self, method, field=None, fields=None):
        if sum([bool(field), bool(fields)]) != 1:
            raise ValueError('Exactly one of "field" or "fields" must be set')
        kwargs = dict(method=method, field=field, fields=fields)
        aggr = {}
        for key, query_list in self.items():
            aggr[key] = query_list.aggregate(**kwargs)
        return aggr
