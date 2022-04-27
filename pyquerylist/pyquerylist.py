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
OPERATORS = set(getattr(operator, f'__{v}__') for v in OPMAP.values())

LOGICAL_OPMAP = {
    '|': 'or',
    '&': 'and',
}
LOGICAL_OPERATORS = set(getattr(operator, f'__{v}__') for v in LOGICAL_OPMAP.values())


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


def _parse_query_args(args, kwargs):
    """Parses arguments (args, kwargs) to Query constructor."""
    inverted = kwargs.pop('inverted', False)
    field = None
    _op = None
    op = None
    func = None
    multi = False
    value = None
    lhs = None
    rhs = None
    logical_op = None

    if bool(args) and bool(kwargs):
        raise ValueError('Only one of args, kwargs can be set')
    if len(args) == 1:
        arg = args[0]
        if callable(arg):
            # arg is a function/lambda.
            func = arg
        else:
            raise ValueError(f'Single argument {arg} not recognized, must be a callable function')
    elif len(args) == 3:
        if isinstance(args[0], Query) and isinstance(args[2], Query):
            multi = True
            lhs, logical_op, rhs = args
            if not isinstance(logical_op, str) and logical_op not in LOGICAL_OPERATORS:
                raise ValueError(
                    f'Second argument of 3 (query, op, query) must be a string or a logical `operator` function'
                )
        else:
            field, op, value = args
            if not isinstance(field, str):
                raise ValueError(f'First argument of 3 (field, op, value) must be a string')
            if not isinstance(op, str) and op not in OPERATORS:
                raise ValueError(f'Second argument of 3 (field, op, value) must be a string or an `operator` function')
    elif kwargs:
        if len(kwargs) > 1:
            multi = True
            lhs = None
            logical_op = '&'
        for k, value in kwargs.items():
            if '__' in k:
                field, op = k.split('__')
            else:
                field = k
                op = '='
            if multi:
                new_query = Query(field, op, value)
                if lhs:
                    if rhs:
                        rhs = Query(rhs, '&', new_query)
                    else:
                        rhs = new_query
                else:
                    lhs = new_query

    _op = op
    if op and isinstance(op, str):
        if op in OPMAP:
            op = OPMAP[op]
        try:
            op = getattr(operator, f'__{op}__')
        except AttributeError:
            raise ValueError(f'operator {op} not recognized')
    if logical_op and isinstance(logical_op, str):
        if logical_op in LOGICAL_OPMAP:
            logical_op = LOGICAL_OPMAP[logical_op]
        try:
            logical_op = getattr(operator, f'__{logical_op}__')
        except AttributeError:
            raise ValueError(f'operator {logical_op} not recognized')
    return field, _op, op, value, func, multi, lhs, rhs, logical_op


class Query:
    """Combinable query class.

    Condition can be specified in different ways:

    * specified by a field, operator and value.
    * specified by a lambda or function.
    * specified by key value pairs.

    >>> q1 = Query('field1', '>', 5)
    >>> q2 = Query(lambda x: x.field1 < 10)
    >>> q3 = Query(field1=8)
    >>> q4 = Query(field1__lt=9, field2='a')
    >>> q5 = Query(q1, '|', q3)
    >>> qand = q1 & q2
    >>> qor = q2 | q4
    >>> qnand = ~q1 & ~q3
    """

    def __init__(self, *args, **kwargs):
        """Constructor can be called using:

        Field, operator, value:
        operator can be a string such as '<', '>', '=';
        or a string such as 'lt', 'gt', 'eq', 'in';
        or an attribute on the `operator` package - i.e. `operator.__gt__`.

        >>> q = Query('field1', '>', 5)
        >>> q = Query('field1', operator.__gt__, 5)
        >>> q = Query('field1', 'in', [5, 6, 7])

        Function or lambda:

        >>> def fn(x): return x.field < 10
        >>> q = Query(fn)
        >>> q = Query(lambda x: x.field1 < 10)

        Key value pairs:
        field and operator can be included in the key using double underscore '__'
        where the operator is on of e.g. 'lt', 'gt'...

        >>> q = Query(field1=8)
        >>> q = Query(field1__lt=9, field2='a')
        """
        self.inverted = kwargs.pop('inverted', False)
        (
            self.field,
            self._op,
            self.op,
            self.value,
            self.func,
            self.multi,
            self.lhs,
            self.rhs,
            self.logical_op,
        ) = _parse_query_args(args, kwargs)

    def match(self, item, item_type='obj'):
        """Determine if the given item is matched by this query.

        >>> class Item: pass
        >>> item = Item()
        >>> item.field1 = 6
        >>> item.field2 = 'a'
        >>> q1 = Query('field1', '>', 5)
        >>> q2 = Query(lambda x: x.field1 < 10)
        >>> q3 = Query(field1=8)
        >>> q4 = Query(field1__lt=9, field2='a')
        >>> q5 = Query(q1, '|', q3)
        >>> q1.match(item)
        True
        >>> q2.match(item)
        True
        >>> q3.match(item)
        False
        >>> q4.match(item)
        True
        >>> q5.match(item)
        True

        :param item: item to test
        :param item_type: type of item
        :return: True if item matches query
        """
        _check_item_type(item_type)
        if self.func:
            retval = self.func(item)
        elif self.multi:
            retval = self.logical_op(self.lhs.match(item, item_type), self.rhs.match(item, item_type))
        else:
            item_val = _get_field_val(item, self.field, item_type)
            if self.op is operator.__contains__:
                retval = self.op(self.value, item_val)
            else:
                retval = self.op(item_val, self.value)

        if self.inverted:
            return retval == False
        else:
            return retval

    def __and__(self, other):
        return Query(self, operator.__and__, other)

    def __rand__(self, other):
        return Query(other, operator.__and__, self)

    def __or__(self, other):
        return Query(self, operator.__or__, other)

    def __ror__(self, other):
        return Query(other, operator.__or__, self)

    def __invert__(self):
        if self.func:
            return Query(self.func, inverted=not self.inverted)
        elif self.multi:
            return Query(self.lhs, self.logical_op, self.rhs, inverted=not self.inverted)
        else:
            return Query(self.field, self._op, self.value, inverted=not self.inverted)

    def __neq__(self, other):
        return not self == other

    def __eq__(self, other):
        for attr in ['field', 'op', 'value', 'func', 'lhs', 'rhs', 'logical_op', 'inverted']:
            if getattr(self, attr) != getattr(other, attr):
                return False
        return True

    def __repr__(self):
        if self.func:
            return f"Query('{self.func}', inverted={self.inverted})"
        elif self.multi:
            opstr = '&' if self.logical_op == operator.__and__ else '|'
            return f"Query({repr(self.lhs)}, '{opstr}', {repr(self.rhs)}, inverted={self.inverted})"
        else:
            return f"Query('{self.field}', '{self._op}', {repr(self.value)}, inverted={self.inverted})"


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
        if kwargs:
            query = Query(**kwargs)

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
            return [tuple([_get_field_val(item, f, self.item_type) for f in fields]) for item in self]
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
                    return tuple([_get_field_val(item, f, self.item_type) for f in fields])

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
