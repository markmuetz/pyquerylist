from dataclasses import dataclass

from pyquerylist import Query as Q, FuncQuery as FQ, QueryList


@dataclass
class Book:
    name: str
    price_pence: int
    category: str

    def price(self):
        return self.price_pence / 100

    def vat_price(self):
        return self.price() * 1.2


books = QueryList(
    [
        Book('Three crows', 500, 'fantasy'),
        Book('Molly had a little calf', 200, 'child'),
        Book('Time for another', 150, 'bargain'),
        Book('Of stars and mud', 700, 'highbrow'),
        Book('The Fruggalo', 300, 'child'),
        Book('Three women in a canoe', 120, 'classic'),
        Book('Who turns the page', 700, 'mystery'),
        Book('The sword of silver', 300, 'fantasy'),
        Book('Murder at 30000 ft', 150, 'mystery'),
        Book('Once I saw a little mouse', 50, 'child'),
        Book('The Leonardo code', 20, 'bargain'),
        Book('The place we are at', 900, 'highbrow'),
    ]
)

print(books.count())
# books can be filtered on one of their fields.
print(books.where(name='The Fruggalo').count())
# This can also be done using a query.
print(books.where(Q('name', '=', 'The Fruggalo')).count())
# Queries can be inverted.
print(books.where(~Q('name', '=', 'The Fruggalo')).count())
# books is a list -- can be indexed or sliced:
print(books[:3])

# books can be filtered on multiple fields, showing price <= 3.
# if a field is a function (is callable) - it will be called (i.e. price).
print(books.where(category='fantasy', price__le=3))
# Equivalent to above using queries.
print(books.where(Q('category', '=', 'fantasy') & Q('price', '<=', 3)))

# Queries can be combined using logical operators, and ordered by field(s).
print(
    books.where(Q('category', '=', 'fantasy') | Q('price', '<=', 3))
    .orderby('price', order='descending')
    .select(fields=['category', 'price'])
)
# `lambda`s can be used, and fields can be chosen using `.select(...)`.
print(
    books.where(
        Q('category', '=', 'fantasy') | FQ(lambda x: x.price() * 2 <= 6)
    ).select(fields=['category', 'price'])
)
# Simple aggregate operations available.
print(books.aggregate(sum, 'price'))
print(books.aggregate(sum, fields=['price', 'vat_price']))

# Simple group by operator (returns a dict subclass), with group operations count and aggregate.
print(books.groupby('category')['mystery'])
print(books.groupby('category').count())
print(books.groupby('category').aggregate(sum, 'price'))

# QueryLists can be formatted for tabular display.
print(books.where(category='fantasy').tabulate(['name', 'price']))
