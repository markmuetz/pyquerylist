import pandas as pd

from .pyquerylist import Query


@pd.api.extensions.register_dataframe_accessor('q')
class QueryAccessor:
    def __init__(self, pandas_obj):
        self._obj = pandas_obj

    def where(self, query=None, **kwargs):
        if not query and not kwargs:
            raise ValueError('One or both of query and kwargs must be given')
        if kwargs:
            query = Query(**kwargs)
        return self._obj[query.match(self._obj)]

    def select(self, field=None, fields=None):
        if sum([bool(field), bool(fields)]) != 1:
            raise ValueError('Exactly one of "field" or "fields" must be set')
        if field:
            fields = [field]
        return self._obj[fields]

    def orderby(self, field=None, fields=None, key=None, order='ascending'):
        if sum([bool(field), bool(fields), bool(key)]) != 1:
            raise ValueError('Exactly one of "field" or "fields" must be set')
        if order not in ['ascending', 'descending']:
            raise ValueError('Order must be "ascending" or "descending"')
        ascending = True if order == 'ascending' else False
        if key:
            return self._obj.sort_values(key=key, ascending=ascending)
        if field:
            fields = [field]
        return self._obj.sort_values(by=fields, ascending=ascending)

    def groupby(self, field=None):
        return self._obj.groupby(field)
