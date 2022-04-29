import ast
from collections import defaultdict
import copy
from inspect import signature
from itertools import groupby
import operator

from tabulate import tabulate

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
    if _callable_no_arg(val):
        val = val()
    return val


def _callable_no_arg(obj):
    return callable(obj) and len(signature(obj).parameters) == 0


def _callable_single_arg(obj):
    return callable(obj) and len(signature(obj).parameters) == 1


def _parse_query_args(args):
    """Parses arguments (args) to Query constructor."""
    expr_str = None
    expr = None
    expr_inputs = None
    func = None
    multi = False
    value = None
    lhs = None
    rhs = None
    logical_op = None

    if len(args) == 1:
        arg = args[0]
        if isinstance(arg, str):
            expr_str = arg
            expr_inputs = Query._expr_validate_find_inputs(expr_str)
            expr = compile(expr_str, 'query_expr_str', 'eval')
        elif _callable_single_arg(arg):
            # arg is a function/lambda.
            func = arg
        else:
            raise ValueError(f'Single argument {arg} not recognized, must be a callable function or string')
    elif len(args) == 3:
        if isinstance(args[0], Query) and isinstance(args[2], Query):
            multi = True
            lhs, logical_op, rhs = args
            if not isinstance(logical_op, str) and logical_op not in LOGICAL_OPERATORS:
                raise ValueError(f'Second argument of 3 must be a string or a logical `operator` function')
        else:
            raise ValueError(f'3 arguemnts must be of type Query, str|logical `operator`, Query')

    if logical_op and isinstance(logical_op, str):
        if logical_op in LOGICAL_OPMAP:
            logical_op = LOGICAL_OPMAP[logical_op]
        try:
            logical_op = getattr(operator, f'__{logical_op}__')
        except AttributeError:
            raise ValueError(f'operator {logical_op} not recognized')
    return expr_str, expr, expr_inputs, func, multi, lhs, rhs, logical_op


class Query:
    """Combinable query class.

    Condition can be specified in two different ways:

    * specified by a python expression.
    * specified by a lambda or function.

    >>> q1 = Query('field1 < 10')
    >>> q2 = Query('(0 < field1 < 10) & (field2 == "b")')
    >>> q3 = Query(lambda x: x.field1 < 10)
    >>> q4 = Query(q1, '|', q2)
    >>> qand = q1 & q2
    >>> qor = q2 | q3
    >>> qnand = ~q1 & ~q4
    """

    _ast_comparisons = {
        # Comparisons.
        ast.Compare,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.Is,
        ast.IsNot,
        ast.In,
        ast.NotIn,
        ast.Gt,
        ast.Lt,
    }
    allowed_ast_types = {
        # BinOps.
        ast.BinOp,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.LShift,
        ast.RShift,
        ast.BitOr,
        ast.BitXor,
        ast.BitAnd,
        ast.BitAnd,
        # Literals.
        ast.Constant,
        ast.List,
        ast.Tuple,
        ast.Set,
        ast.Dict,
        # Extras.
        ast.Name,
        ast.Load,
    } | _ast_comparisons
    _validate_ast = True

    def __init__(self, *args, **kwargs):
        """Constructor can be called using:

        Python string.

        >>> q = Query('field1 > 5')
        >>> q = Query('field1 in [5, 6, 7]')

        Function or lambda:

        >>> def fn(x): return x.field < 10
        >>> q = Query(fn)
        >>> q = Query(lambda x: x.field1 < 10)

        """
        self.inverted = kwargs.pop('inverted', False)
        if kwargs:
            raise ValueError('"inverted" is the only allowed keyword argument')

        (
            self.expr_str,
            self.expr,
            self.expr_inputs,
            self.func,
            self.multi,
            self.lhs,
            self.rhs,
            self.logical_op,
        ) = _parse_query_args(args)

    @classmethod
    def add_allowed_ast_type(cls, ast_type):
        """Add additional allowed AST types to existing.

        When a query is constructed using:

        >>> q = Query('a < 10')

        Checks are done to validate the expression to make sure it only contains certain
        types given by Q.allowed_ast_types. This metho allows the addition of any AST types to
        this set.

        >>> Query.add_allowed_ast_type(ast.Call)
        >>> ast.Call in Query.allowed_ast_types
        True
        >>> q = Query('func() < 10')  # Normally would cause exception.

        :param ast_type: AST type or set of AST types.
        """
        if not isinstance(ast_type, set):
            ast_type = set([ast_type])
        cls.allowed_ast_types |= ast_type

    @classmethod
    def expr_validation(cls, validate):
        """Enable or disable expression validation

        >>> Query.expr_validation(False)
        >>> q = Query('func() < 10')  # Normally would cause exception.

        :param validate: whether to validate or not
        """
        cls._validate_ast = validate

    @classmethod
    def _expr_validate_find_inputs(cls, expr):
        inputs = set()
        st = ast.parse(expr)
        if cls._validate_ast and len(st.body) > 1:
            raise ValueError(f'Only one line/expr allowed in {expr}')
        expr_node = st.body[0]
        start_node = expr_node.value

        comparison = False
        for node in ast.walk(start_node):
            if cls._validate_ast and type(node) not in cls.allowed_ast_types:
                raise ValueError(f'Type {type(node).__name__} not allowed in {expr}')
            if type(node) in cls._ast_comparisons:
                comparison = True
            if type(node) is ast.Name:
                inputs.add(node.id)
        if cls._validate_ast and not comparison:
            raise ValueError(f'No comparison operators in {expr}')
        return inputs

    def match(self, item, item_type='obj'):
        """Determine if the given item is matched by this query.

        >>> class Item: pass
        >>> item = Item()
        >>> item.field1 = 6
        >>> item.field2 = 'a'
        >>> q1 = Query('(field1 > 0) & (field2 == "a")')
        >>> q2 = Query(lambda x: x.field1 < 10)
        >>> q1.match(item)
        True
        >>> q2.match(item)
        True

        :param item: item to test
        :param item_type: type of item
        :return: True if item matches query
        """
        _check_item_type(item_type)
        if self.expr:
            fields = self.expr_inputs
            vals = {f: _get_field_val(item, f, item_type) for f in fields}
            retval = eval(self.expr, {"__builtins__": None}, vals)
        elif self.func:
            retval = self.func(item)
        elif self.multi:
            retval = self.logical_op(self.lhs.match(item, item_type), self.rhs.match(item, item_type))

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
        if self.expr:
            return Query(self.expr_str, inverted=not self.inverted)
        elif self.func:
            return Query(self.func, inverted=not self.inverted)
        elif self.multi:
            return Query(self.lhs, self.logical_op, self.rhs, inverted=not self.inverted)

    def __neq__(self, other):
        return not self == other

    def __eq__(self, other):
        for attr in ['expr', 'func', 'lhs', 'rhs', 'logical_op', 'inverted']:
            if getattr(self, attr) != getattr(other, attr):
                return False
        return True

    def __repr__(self):
        if self.expr_str:
            return f"Query('{self.expr_str}', inverted={self.inverted})"
        elif self.func:
            return f"Query('{self.func}', inverted={self.inverted})"
        elif self.multi:
            opstr = '&' if self.logical_op == operator.__and__ else '|'
            return f"Query({repr(self.lhs)}, '{opstr}', {repr(self.rhs)}, inverted={self.inverted})"


class QueryList(list):
    """Queryable list.

    >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 4, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
    >>> len(ql)
    3
    >>> ql[:2]
    QueryList([{'a': 1, 'b': 2}, {'a': 4, 'b': 5}])
    >>> ql.where('a==1').select('a')
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

    def where(self, query):
        """Filter based on query.

        >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 4, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.where('(b>3)&(a==b-2)')
        QueryList([{'a': 7, 'b': 9}])

        :param query: query to apply
        :return: filtered QueryList
        """
        if isinstance(query, str) or _callable_single_arg(query):
            query = Query(query)

        new_items = []
        for item in self:
            if query.match(item, self.item_type):
                new_items.append(item)
        return QueryList(new_items, self.item_type)

    def select(self, fields=None, func=None):
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
        if sum([bool(fields), bool(func)]) != 1:
            raise ValueError('Exactly one of "field", "fields", or "func" must be set')
        if isinstance(fields, str):
            return [_get_field_val(item, fields, self.item_type) for item in self]
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
        >>> ql.all(Query('a>0'))
        True
        >>> ql.all(Query('a<4'))
        False

        :param query: query to test
        :return: True if all items match query
        """
        return len(self.where(query)) == len(self)

    def any(self, query):
        """Test if any items match query.

        >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 4, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.any(Query('a<0'))
        False
        >>> ql.any(Query('a>4'))
        True

        :param query: query to test
        :return: True if all items match query
        """
        return len(self.where(query)) != 0

    def orderby(self, fields=None, key=None, order='ascending'):
        """Order QueryList based on supplied arguments.

        Exactly one of fields or key must be supplied.

        >>> ql = QueryList([{'a': 5, 'b': 2}, {'a': 4, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.orderby('a')
        QueryList([{'a': 4, 'b': 5}, {'a': 5, 'b': 2}, {'a': 7, 'b': 9}])
        >>> ql.orderby(['a', 'b'])
        QueryList([{'a': 4, 'b': 5}, {'a': 5, 'b': 2}, {'a': 7, 'b': 9}])
        >>> ql.orderby(key=lambda x: x['b'], order='descending')
        QueryList([{'a': 7, 'b': 9}, {'a': 4, 'b': 5}, {'a': 5, 'b': 2}])

        :param field: field to order by
        :param fields: fields to order by
        :param key: key to order on (passed to `sorted`)
        :param order: ascending or descending
        :return: Ordered QueryList
        """
        if sum([bool(fields), bool(key)]) != 1:
            raise ValueError('Exactly one of "fields" or "key" must be set')
        if isinstance(fields, str):
            fields = [fields]
        if order not in ['ascending', 'descending']:
            raise ValueError('Order must be "ascending" or "descending"')
        reverse = False if order == 'ascending' else True
        if not key:

            def key(item):
                return tuple([_get_field_val(item, f, self.item_type) for f in fields])

        return QueryList(sorted(self, key=key, reverse=reverse), self.item_type)

    def groupby(self, field):
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

    def aggregate(self, method, fields):
        """Aggregate a given field(s) based on method.

        Exactly one of field or fields must be supplied.

        >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 4, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.aggregate(sum, 'a')
        12
        >>> ql.aggregate(sum, fields=['a', 'b'])
        [12, 16]

        :param method: method to use (e.g. `statistics.mean`)
        :param fields: fields to aggregate over
        :return: aggregated values
        """
        if isinstance(fields, str):
            return method(self.select(fields))
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

    def aggregate(self, method, fields):
        """Aggregate over instances of each group using method and field(s).

        >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 1, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.groupby('a').aggregate(sum, 'b')
        {1: 7, 7: 9}

        :param method: method to use (e.g. `statistics.mean`)
        :param fields: field(s) to aggregate over
        :return: aggregated values dict with key (group) and value (aggregated value)
        """
        kwargs = dict(method=method, fields=fields)
        aggr = {}
        for key, query_list in self.items():
            aggr[key] = query_list.aggregate(**kwargs)
        return aggr

    def select(self, fields=None, func=None):
        """Select given field(s) from instances of each group.

        Exactly one of the three arguments must be supplied.

        >>> ql = QueryList([{'a': 1, 'b': 2}, {'a': 1, 'b': 5}, {'a': 7, 'b': 9}], 'dict')
        >>> ql.groupby('a').select('b')
        {1: [2, 5], 7: [9]}

        :param fields: field(s) to select
        :param func: function to apply to item -- output is selected
        :return: aggregated values dict with key (group) and value (selected field(s))
        """
        if sum([bool(fields), bool(func)]) != 1:
            raise ValueError('Exactly one of "fields", or "func" must be set')
        kwargs = dict(fields=fields, func=func)
        aggr = {}
        for key, query_list in self.items():
            aggr[key] = query_list.select(**kwargs)
        return aggr
