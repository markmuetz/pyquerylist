import operator

from nose.tools import assert_raises

from pyquerylist import Query


class Item:
    pass


def test_field_op_value_constructors():
    Query('a', '<', 5)
    Query('a', operator.__ge__, 6)
    Query('a', 'lt', 1)


def test_func_constructors():
    def fn(a):
        return a.field < 10

    Query(fn)
    Query(lambda x: x.field > 20)


def test_func_constructors():
    def fn(a):
        return a.field < 10

    Query(fn)
    Query(lambda x: x.field > 20)


def test_single_kwargs_constructors():
    Query(a=5)
    Query(a__lt=6)
    Query(a__in=[6, 7, 8])


def test_multi_kwargs_constructors():
    Query(a=5, b=4)
    Query(a__lt=6, b__ge=9)
    Query(a__in=[6, 7, 8], b__in=['a', 'b', 'c'])
    Query(a__in=[6, 7, 8], b__in=['a', 'b', 'c'], c=22)


def test_multi_query_constructors():
    q1 = Query(a=5, b=4)
    q2 = Query('a', '<', 5)
    q3 = Query(lambda x: x.field > 20)
    Query(q1, '|', q2)
    Query(q1, '&', q3)
    Query(q2, 'or', q3)


def test_constructor_errors():
    assert_raises(ValueError, Query, 'a', '<', 5, a=6)
    assert_raises(ValueError, Query, 'a = 22')
    assert_raises(ValueError, Query, 5, '<', 5)
    assert_raises(ValueError, Query, 'a', 'not_an_op', 5)
    q1 = Query(a=5, b=4)
    q2 = Query('a', '<', 5)
    assert_raises(ValueError, Query, q1, '<', q2)


def test_combinations():
    q1 = Query(a=5, b=4)
    q2 = Query('a', '<', 5)
    q3 = Query(lambda x: x.field > 20)
    q4 = q1 & q2
    q5 = q1 | q2
    q6 = ~q1 | ~q3
    q7 = ~q1 | ~q2 | ~q3
    q8 = ~q1 & ~q2 | ~q3 & q7


def test_field_op_value_match():
    q1 = Query('a', '<', 5)
    q2 = Query('a', operator.__ge__, 6)
    q3 = Query('a', 'lt', 1)

    item = Item
    item.a = 4

    assert q1.match(item)
    assert not q2.match(item)
    assert not q3.match(item)

    item = {'a': 8}

    assert not q1.match(item, dict)
    assert q2.match(item, dict)
    assert not q3.match(item, dict)


def test_func_match():
    def fn(a):
        return a.field < 10

    q1 = Query(fn)
    q2 = Query(lambda x: x.field > 20)

    item = Item
    item.field = 4

    assert q1.match(item)


def test_single_kwargs_match():
    q1 = Query(a=5)
    q2 = Query(a__lt=6)
    q3 = Query(a__in=[6, 7, 8])

    item = Item
    item.a = 6

    assert not q1.match(item)
    assert not q2.match(item)
    assert q3.match(item)


def test_multi_kwargs_match():
    q1 = Query(a=5, b='c')
    q2 = Query(a__lt=6, b__in=['d', 'e'])
    q3 = Query(a__in=[6, 7, 8], b__in=['a', 'b', 'c'])
    q4 = Query(a__in=[6, 7, 8], b__in=['a', 'b', 'c'], c=22)

    item = Item
    item.a = 6
    item.b = 'c'
    item.c = 22

    assert not q1.match(item)
    assert not q2.match(item)
    assert q3.match(item)
    assert q4.match(item)


def test_multi_query_match():
    q1 = Query(a=5, b=4)
    q2 = Query('a', '<', 5)
    q3 = Query(lambda x: x.c > 20)
    q4 = Query(q1, '|', q2)
    q5 = Query(q1, '&', q3)
    q6 = Query(q2, 'or', q3)

    item = Item
    item.a = 1
    item.b = 'c'
    item.c = 22

    assert q4.match(item)
    assert not q5.match(item)
    assert q6.match(item)


def test_combinations_match():
    q1 = Query(a=5, b=4)
    q2 = Query('a', '<', 5)
    q3 = Query(lambda x: x.c < 20)
    q4 = q1 & q2
    q5 = q1 | q2
    q6 = ~q1 & ~q3
    q7 = ~q1 | ~q2 | ~q3
    q8 = (~q1 & ~q2) | ~q3 & q7

    item = Item
    item.a = 1
    item.b = 'c'
    item.c = 22

    assert not q4.match(item)
    assert q5.match(item)
    assert q6.match(item)
    assert q7.match(item)
    assert q8.match(item)


def test_equality():
    assert Query('a', '>', 5) == Query('a', '>', 5)
    assert Query('b', '>', 5) != Query('a', '>', 5)
    assert Query('a', '<', 5) != Query('a', '>', 5)
    assert Query('a', '>', 6) != Query('a', '>', 5)
    assert Query('a', '>', 5) != ~Query('a', '>', 5)

    assert Query('a', '=', 5) == Query(a=5)
    assert Query('a', '>', 5) == Query(a__gt=5)

    assert Query('a', '>', 5) & Query('b', '<', 10) == Query(a__gt=5) & Query(b__lt=10)
    # Technically these are equal, but the LHS/RHS have been swapped.
    assert Query('b', '<', 10) | Query('a', '>', 5) != Query(a__gt=5) | Query(b__lt=10)

    assert Query(name='a') | Query(price__le=5) == Query(Query(name='a'), '|', Query(price__le=5))

    def fn(a):
        return a.field < 10

    assert Query(fn) == Query(fn)
    # Technically these are equal, but cannot tell a lambda is the same as a func.
    assert Query(fn) != Query(lambda x: x.field < 10)
    # Or indeed that two lamdas are the same:
    assert Query(lambda x: x.field < 10) != Query(lambda x: x.field < 10)
