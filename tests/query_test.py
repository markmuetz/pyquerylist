import operator

from pytest import raises

from pyquerylist import Query

class Item:
    pass


class TestQueries:

    def test_expr_constructors(self):
        Query('a<5')
        Query('a>=6')
        Query('(a<1)&(b>2)')
        Query('(a<1)|(b in [3, 4, 5])')


    def test_func_constructors(self):
        def fn(a):
            return a.field < 10

        Query(fn)
        Query(lambda x: x.field > 20)


    def test_multi_query_constructors(self):
        q1 = Query('(a==5)&(b==4)')
        q2 = Query('a<5')
        q3 = Query(lambda x: x.field > 20)
        q4 = Query(q1, '|', q2)
        q5 = Query(q1, '&', q3)
        q6 = Query(q2, 'or', q3)
        q7 = Query(q2, 'or', q5)
        q8 = Query(q7, '&', q4)
        q9 = Query(~q7, '|', ~q8)


    def test_constructor_errors(self):
        with raises(ValueError):
            Query('func() < 2')
        with raises(ValueError):
            Query('a*3')
        with raises(ValueError):
            Query(a=5, b=4)
        with raises(ValueError):
            q1 = Query('a<5')
            q2 = Query('b>6')
            Query(q1, '<', q2)


    def test_combinations(self):
        q1 = Query('(a==5)&(b==4)')
        q2 = Query('a<5')
        q3 = Query(lambda x: x.field > 20)
        q4 = q1 & q2
        q5 = q1 | q2
        q6 = ~q1 | ~q3
        q7 = ~q1 | ~q2 | ~q3
        q8 = ~q1 & ~q2 | ~q3 & q7


    def test_expr_match(self):
        q1 = Query('a<5')
        q2 = Query('a>=6')
        q3 = Query('a<1')
        q4 = Query('a in [1, 2, 3, 8]')
        q5 = Query('a in [4, 5]')

        item = Item
        item.a = 4

        assert q1.match(item)
        assert not q2.match(item)
        assert not q3.match(item)
        assert not q4.match(item)
        assert q5.match(item)

        item = {'a': 8}

        assert not q1.match(item, dict)
        assert q2.match(item, dict)
        assert not q3.match(item, dict)
        assert q4.match(item, dict)
        assert not q5.match(item, dict)


    def test_func_match(self):
        def fn(a):
            return a.field < 10

        q1 = Query(fn)
        q2 = Query(lambda x: x.field > 20)

        item = Item
        item.field = 4

        assert q1.match(item)


    def test_multi_query_match(self):
        q1 = Query('(a==5)&(b==4)')
        q2 = Query('a<5')
        q3 = Query(lambda x: x.c < 20)
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


    def test_combinations_match(self):
        q1 = Query('(a==5)&(b==4)')
        q2 = Query('a<5')
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


    def test_equality(self):
        assert Query('a>5') == Query('a > 5')
        assert Query('b<5') != Query('a<5')
        assert Query('a>5') != ~Query('a > 5')

        assert Query('a<5') & Query('b<10') == Query('a<5') & Query('b<10')
        assert Query('a<5') & Query('b<10') != Query('a<5') | Query('b<10')
        # Technically these are equal, but the LHS/RHS have been swapped.
        assert Query('a<5') | Query('b<10') != Query('b<10') | Query('a<5')

        assert Query('name=="a"') | Query('price<=5') == Query(Query('name=="a"'), '|', Query('price<=5'))

        def fn(a):
            return a.field < 10

        assert Query(fn) == Query(fn)
        # Technically these are equal, but cannot tell a lambda is the same as a func.
        assert Query(fn) == Query(lambda x: x.field < 10)
        # Or indeed that two lamdas are the same:
        assert Query(lambda x: x.field < 10) == Query(lambda x: x.field < 10)
