from collections import defaultdict
import copy
from itertools import groupby
import operator

from tabulate import tabulate

# Operator mapping to allow symbols strings to be used for query operators.
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
    object: getattr,
    'dict': dict.__getitem__,
    dict: dict.__getitem__,
}


def _check_item_type(item_type):
    """Raises a ValueError if item_type not supported.

    :param item_type: requested item type
    :return: None
    """
    if item_type not in ITEM_GETTERS:

        def fmt(t):
            if isinstance(t, str):
                return f"'{t}'"
            else:
                return repr(t)

        item_types = ', '.join([fmt(t) for t in ITEM_GETTERS.keys()])
        raise ValueError(f'item_type must be one of {item_types}')


def _get_field_val(item, field, item_type):
    """Get a value from an item of a specific type.

    :param item: item to use
    :param field: field of item to get
    :param item_type: type of item ('obj' or 'dict')
    :return: value of item's field
    """
    _check_item_type(item_type)
    getter = ITEM_GETTERS[item_type]
    val = getter(item, field)
    if callable(val):
        val = val()
    return val


class BaseQuery:
    """Base class for all query classes that implements logical operations (& | ~) for combining."""

    def __init__(self, inverted):
        """Constructor.

        :param inverted: whether to invert any matches
        """
        self.inverted = inverted

    def __and__(self, other):
        return MultiQuery(self, other, operator.__and__)

    def __rand__(self, other):
        return MultiQuery(other, self, operator.__and__)

    def __or__(self, other):
        return MultiQuery(self, other, operator.__or__)

    def __ror__(self, other):
        return MultiQuery(other, self, operator.__or__)


class Query(BaseQuery):
    """Combinable query class, where condition is specified by a field, operator and value.

    >>> q1 = Query('field1', '>', 5)
    >>> q2 = Query('field1', '<', 10)
    >>> qand = q1 & q2
    >>> qor = q1 | q2
    >>> qnand = ~q1 & ~q2
    """

    def __init__(self, field, op, val, inverted=False):
        """Constructor that takes a field, operator and value as arguments.

        op can be specified using a string (used to pick from `operator.__{op}__`). See OPMAP for values.

        :param field: field (of item) that will be tested
        :param op: operator (e.g. "=") to use in test
        :param val: value to test against
        :param inverted: whether to invert the condition
        """
        super().__init__(inverted)
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
        """Determine if item matches query.

        >>> q1 = Query('field1', '>', 5)
        >>> class Item: pass
        >>> item = Item()
        >>> item.field1 = 6
        >>> q1.match(item, 'obj')
        True
        >>> (~q1).match(item, 'obj')
        False

        :param item: item to test
        :param item_type: type of item
        :return: True if item matches query
        """
        _check_item_type(item_type)
        item_val = _get_field_val(item, self.field, item_type)
        if self.op is operator.__contains__:
            retval = self.op(self.val, item_val)
        else:
            retval = self.op(item_val, self.val)
        if self.inverted:
            return retval == False
        else:
            return retval

    def __repr__(self):
        return f"Query('{self.field}', '{self._op}', {repr(self.val)}, {self.inverted})"

    def __invert__(self):
        return Query(self.field, self._op, self.val, not self.inverted)


class FuncQuery(BaseQuery):
    """Combinable query class, where condition is specified by a function/lambda

    >>> q1 = FuncQuery(lambda x: x.field1 > 5)
    >>> q2 = FuncQuery(lambda x: x.field1 < 10)
    >>> qand = q1 & q2
    >>> qor = q1 | q2
    >>> qnand = ~q1 & ~q2
    """

    def __init__(self, func, inverted=False):
        """Constructor that takes a function/lambda as argument.

        :param func: function or lambda for query condition
        :param inverted: whether to invert the condition
        """
        super().__init__(inverted)
        self.func = func

    def match(self, item, item_type):
        """Determine if item matches function query.

        >>> q1 = FuncQuery(lambda x: x.field1 > 5)
        >>> class Item: pass
        >>> item = Item()
        >>> item.field1 = 6
        >>> q1.match(item, 'obj')
        True
        >>> (~q1).match(item, 'obj')
        False

        :param item: item to test
        :param item_type: type of item
        :return: True if item matches query
        """
        retval = self.func(item)
        if self.inverted:
            return retval == False
        else:
            return retval

    def __repr__(self):
        return f"FuncQuery('{self.func}', {self.inverted})"

    def __invert__(self):
        return FuncQuery(self.func, not self.inverted)


class MultiQuery(BaseQuery):
    """When two queries are combined using e.g. &, a MultiQuery object is created."""

    def __init__(self, lhs, rhs, op, inverted=False):
        """Constructor.

        :param lhs: query1
        :param rhs: query2
        :param op: operator used to combine query1 and query2
        """
        super().__init__(inverted)
        self.lhs = lhs
        self.rhs = rhs
        self.op = op

    def match(self, item, item_type):
        """

        >>> q1 = Query('field1', '>', 5)
        >>> q2 = FuncQuery(lambda x: x.field1 < 10)
        >>> class Item: pass
        >>> item = Item()
        >>> item.field1 = 6
        >>> # Creates a MultiQuery.
        >>> (q1 & q2).match(item, 'obj')
        True
        >>> (~(q1 | q2)).match(item, 'obj')
        False

        :param item: item to test
        :param item_type: type of item
        :return: True if item matches query
        """
        retval = self.op(
            self.lhs.match(item, item_type), self.rhs.match(item, item_type)
        )
        if self.inverted:
            return retval == False
        else:
            return retval

    def __repr__(self):
        opstr = '&' if self.op == operator.__and__ else '|'
        return '(' + repr(self.lhs) + opstr + repr(self.rhs) + ')'

    def __invert__(self):
        return MultiQuery(self.lhs, self.rhs, self.op, not self.inverted)


class QueryList(list):
    """Queryable list.

    >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 4, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
    >>> len(ql)
    3
    >>> ql[:2]
    QueryList([{'a': 1, 'b': 2}, {'a': 4, 'b': 5}])
    >>> ql.where(a=1).select('a')
    [1]
    """

    def __init__(self, iterable=None, item_type='obj'):
        """Construct QueryList based on existing list-like object, and with a given type.

        :param iterable: iterable (e.g. list) used to create this
        :param item_type: type of each item (see ITEM_GETTERS for allowed types)
        """
        _check_item_type(item_type)
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
        """Filter based on query.

        >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 4, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.where(Query('a', '=', 1))
        QueryList([{'a': 1, 'b': 2}])
        >>> ql.where(b__gt=8)
        QueryList([{'a': 7, 'b': 9}])

        :param query: query to apply
        :param kwargs: optional arguments to apply
        :return: filtered QueryList
        """
        if not query and not kwargs:
            raise ValueError('One or both of query and kwargs must be given')
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
        return QueryList(new_items, self.item_type)

    def select(self, field=None, fields=None, func=None):
        """Select given field(s).

        Exactly one of the three arguments must be supplied.

        >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 4, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.select('a')
        [1, 4, 7]
        >>> ql.select(fields=['a', 'b'])
        [(1, 2), (4, 5), (7, 9)]
        >>> ql.select(func=lambda x: x['a']**2)
        [1, 16, 49]

        :param field: field to select
        :param fields: multiple fields to select
        :param func: function to apply to item -- output is selected
        :return: list of selected field(s) or function output
        """
        if sum([bool(field), bool(fields), bool(func)]) != 1:
            raise ValueError('Exactly one of "field", "fields", or "func" must be set')
        if field:
            return [_get_field_val(item, field, self.item_type) for item in self]
        elif fields:
            return [
                tuple([_get_field_val(item, f, self.item_type) for f in fields])
                for item in self
            ]
        elif func:
            return [func(item) for item in self]

    def count(self):
        """Get number of items.

        >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 4, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.count()
        3
        >>> ql.count() == len(ql)
        True

        :return: number of items
        """
        return len(self)

    def first(self):
        """Get first item.

        >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 4, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.first()
        {'a': 1, 'b': 2}

        :return: first item
        """
        return self[0]

    def last(self):
        """Get last item.

        >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 4, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.last()
        {'a': 7, 'b': 9}

        :return: first item
        """
        return self[-1]

    def all(self, query):
        """Test if all items match query.

        >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 4, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.all(Query('a', '>', 0))
        True
        >>> ql.all(Query('a', '>', 4))
        False

        :param query: query to test
        :return: True if all items match query
        """
        return len(self.where(query)) == len(self)

    def any(self, query):
        """Test if any items match query.

        >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 4, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.any(Query('a', '>', 10))
        False
        >>> ql.any(Query('a', '>', 4))
        True

        :param query: query to test
        :return: True if all items match query
        """
        return len(self.where(query)) != 0

    def orderby(self, field=None, fields=None, key=None, order='ascending'):
        """Order QueryList based on supplied arguments.

        Exactly one of field, fields or key must be supplied.

        >>> ql = QueryList([{'a': 5, 'b': 2}, {'a': 4, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.orderby('a')
        QueryList([{'a': 4, 'b': 5}, {'a': 5, 'b': 2}, {'a': 7, 'b': 9}])
        >>> ql.orderby(fields=['a', 'b'])
        QueryList([{'a': 4, 'b': 5}, {'a': 5, 'b': 2}, {'a': 7, 'b': 9}])
        >>> ql.orderby(key=lambda x: x['b'], order='descending')
        QueryList([{'a': 7, 'b': 9}, {'a': 4, 'b': 5}, {'a': 5, 'b': 2}])

        :param field: field to order by
        :param fields: fields to order by
        :param key: key to order on (passed to `sorted`)
        :param order: ascending or descending
        :return: Ordered QueryList
        """
        if sum([bool(field), bool(fields), bool(key)]) != 1:
            raise ValueError('Exactly one of "field", "fields" or "key" must be set')
        if order not in ['ascending', 'descending']:
            raise ValueError('Order must be "ascending" or "descending"')
        reverse = False if order == 'ascending' else True
        if not key:
            if field:

                def key(item):
                    return _get_field_val(item, field, self.item_type)

            else:

                def key(item):
                    return tuple(
                        [_get_field_val(item, f, self.item_type) for f in fields]
                    )

        return QueryList(sorted(self, key=key, reverse=reverse), self.item_type)

    def groupby(self, field=None):
        """Group on given field.

        >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 1, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.groupby('a')
        {1: QueryList([{'a': 1, 'b': 2}, {'a': 1, 'b': 5}]), 7: QueryList([{'a': 7, 'b': 9}])}

        :param field: field to group on
        :return: `QueryGroup` of grouped data
        """
        group = defaultdict(list)
        for k, g in groupby(self, lambda x: _get_field_val(x, field, self.item_type)):
            group[k].extend(g)
        for k, v in group.items():
            group[k] = QueryList(v, self.item_type)
        return QueryGroup(group)

    def aggregate(self, method, field=None, fields=None):
        """Aggregate a given field(s) based on method.

        Exactly one of field or fields must be supplied.

        >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 4, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.aggregate(sum, 'a')
        12
        >>> ql.aggregate(sum, fields=['a', 'b'])
        [12, 16]

        :param method: method to use (e.g. `statistics.mean`)
        :param field: field to aggregate over
        :param fields: fields to aggregate over
        :return: aggregated values
        """
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
        """Produce a formated table of a QueryList

        >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 4, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> print(ql.tabulate(['a', 'b']))
          a    b
        ---  ---
          1    2
          4    5
          7    9

        :param fields: to use as headers/values
        :return: output string of table
        """
        return tabulate(self.select(fields=fields), headers=fields)

    def __str__(self):
        return 'QueryList(\n' + ',\n'.join(' ' * 4 + str(i) for i in self) + '\n)'

    def __repr__(self):
        return 'QueryList([' + ', '.join(str(i) for i in self) + '])'


class QueryGroup(dict):
    """Extension of dict to allow aggregate statistics to be calculated on `QueryList.groupby`."""

    def __init__(self, group):
        """Constructor.

        :param group: group (dict) to initiate with
        """
        super().__init__(group)

    def count(self):
        """Count instances of each group.

        >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 1, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.groupby('a').count()
        {1: 2, 7: 1}

        :return: dict containing key (group) and values (counts)
        """
        return {k: len(ql) for k, ql in self.items()}

    def aggregate(self, method, field=None, fields=None):
        """Aggregate over instances of each group using method and field(s).

        >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 1, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.groupby('a').aggregate(sum, 'b')
        {1: 7, 7: 9}

        :param method: method to use (e.g. `statistics.mean`)
        :param field: field to aggregate over
        :param fields: fields to aggregate over
        :return: aggregated values dict with key (group) and value (aggregated value)
        """
        if sum([bool(field), bool(fields)]) != 1:
            raise ValueError('Exactly one of "field" or "fields" must be set')
        kwargs = dict(method=method, field=field, fields=fields)
        aggr = {}
        for key, query_list in self.items():
            aggr[key] = query_list.aggregate(**kwargs)
        return aggr

    def select(self, field=None, fields=None, func=None):
        """Select given field(s) from instances of each group.

        Exactly one of the three arguments must be supplied.

        >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 1, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.groupby('a').select('b')
        {1: [2, 5], 7: [9]}

        :param field: field to select
        :param fields: multiple fields to select
        :param func: function to apply to item -- output is selected
        :return: aggregated values dict with key (group) and value (selected field(s))
        """
        if sum([bool(field), bool(fields), bool(func)]) != 1:
            raise ValueError('Exactly one of "field", "fields", or "func" must be set')
        kwargs = dict(field=field, fields=fields, func=func)
        aggr = {}
        for key, query_list in self.items():
            aggr[key] = query_list.select(**kwargs)
        return aggr
