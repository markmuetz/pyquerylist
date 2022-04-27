from pyquerylist import Query as Q, QueryList
from pyquerylist.examples import books


def test_basics():
    assert len(books) == books.count() == 12
    assert books[0] == books.first()
    assert books[-1] == books.last()
    assert len(books[2:5]) == books[2:5].count() == 3


def test_where():
    # N fantasy.
    assert books.where(Q(category='fantasy')).count() == 2
    assert books.where(~Q(category='fantasy')).count() == 10

    # N child.
    assert books.where(Q(category='child')).count() == 3
    assert books.where(~Q(category='child')).count() == 9

    # N child and price < 1.
    assert books.where(Q(category='child', price__lt=1)).count() == 1
    assert books.where(~Q(category='child', price__lt=1)).count() == 11

    # N 1.1 < price < 6.5.
    assert books.where(Q(price__gt=1.1, price__lt=6.5)).count() == 7
    assert books.where(~Q(price__gt=1.1, price__lt=6.5)).count() == 5

    # N price > 1.1 or price > 6.5.
    assert books.where(Q(price__lt=1.1) | Q(price__gt=6.5)).count() == 5
    assert books.where(~(Q(price__lt=1.1) | Q(price__gt=6.5))).count() == 7

    # N 1.1 < price < 6.5.
    assert books.where(Q(lambda x: 1.1 < x.price() < 6.5)).count() == 7
    assert books.where(~Q(lambda x: 1.1 < x.price() < 6.5)).count() == 5

    # N price > 1.1 or price > 6.5.
    assert books.where(Q(lambda x: x.price() < 1.1 or x.price() > 6.5)).count() == 5
    assert books.where(~Q(lambda x: x.price() < 1.1 or x.price() > 6.5)).count() == 7

    # N 1.1 < price < 6.5.
    assert books.where(Q(lambda x: x.price() > 1.1) & Q(price__lt=6.5)).count() == 7
    assert books.where(~(Q(lambda x: x.price() > 1.1) & Q(price__lt=6.5))).count() == 5


def test_select():
    assert books[2:5].select('price_pence') == [150, 700, 300]
    assert books[2:5].select(fields=['price_pence', 'category']) == list(
        zip([150, 700, 300], ['bargain', 'highbrow', 'child'])
    )
    assert books[2:5].select(func=lambda b: f'sale price: {b.price_pence // 2}p') == [
        'sale price: 75p',
        'sale price: 350p',
        'sale price: 150p',
    ]


def test_orderby():
    assert books[2:5].orderby('price').select('price_pence') != [150, 700, 300]
    assert books[2:5].orderby('price').select('price_pence') == [150, 300, 700]
    assert books[2:5].orderby('price', order='descending').select('price_pence') == [150, 300, 700][::-1]
    assert books[2:5].orderby(fields=['category', 'price']).select(fields=['category', 'price_pence']) == list(
        zip(['bargain', 'child', 'highbrow'], [150, 300, 700])
    )


def test_aggregate():
    assert books[2:5].aggregate(sum, 'price_pence') == 1150
    assert books[2:5].aggregate(sum, fields=['price_pence', 'price']) == [1150, 11.5]
    assert books[2:5].aggregate(max, 'price_pence') == 700
    assert books[2:5].aggregate(max, fields=['price_pence', 'price']) == [700, 7]


def test_groupby():
    assert len(books.groupby('category')['mystery']) == 2
    assert books.groupby('category').count() == {
        'fantasy': 2,
        'child': 3,
        'bargain': 2,
        'highbrow': 2,
        'classic': 1,
        'mystery': 2,
    }
    assert books.groupby('category').aggregate(max, 'price_pence') == {
        'fantasy': 500,
        'child': 300,
        'bargain': 150,
        'highbrow': 900,
        'classic': 120,
        'mystery': 700,
    }
