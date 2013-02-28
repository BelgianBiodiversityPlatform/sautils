# -*- coding: utf-8 -*-

import json
import sys
import xml.etree.ElementTree as et

from datetime import datetime, date

from sqlalchemy import orm

__all__ = ['Serializer']


class BaseEncoder(object):

    def __init__(self, default=None,
                 timestamp_format='%Y-%m-%dT%H:%M:%SZ',
                 date_format='%Y-%m-%d'):

        # Map type to the correct function
        self.types_map = {
            datetime : self.from_datetime,
            date : self.from_date,
            tuple : self.from_tuple,
            list : self.from_list,
            dict : self.from_dict       
        }

        self.timestamp_format = timestamp_format
        self.date_format = date_format

        self.default = default

    def __call__(self, value, *args, **kwargs):
        encoder = self.types_map.get(value.__class__, self.default)

        if encoder:
            return encoder(value, *args, **kwargs)
        else:
            for (cls, func) in self.types_map.iteritems():
                if isinstance(value, cls):
                    return func(value, *args, **kwargs)
            return value

    def from_datetime(self, value):
        return value.strftime(self.timestamp_format)

    def from_date(self, value):
        return value.strftime(self.date_format)

    def _from_iterable(self, value):
        return [self.__call__(i) for i in value]

    from_tuple = from_list = _from_iterable

    def from_dict(self, value):
        return {k: self.__call__(v) for (k, v) in value.iteritems()}


class Serializer(object):
    '''
        - Seriliaze all columns:
        Seriliazer(obj).dict(include_columns=True)
            include_columns = True
            exclude_columns = None

        - Seriliaze without colums:
        Serializer(obj).dict(exclude_columns=True)
            include_columns = None
            exclude_columns = True

        - Serialize only those columns:
        Serializer(obj).dict(include_columns=['id', 'title'])
            include_columns = [ ... ]
            exclude_columns = None

        - Seriliaze all columns except 'foo' and 'bar':
        Serializer(obj).dict(exclude_columns=['foo', 'bar'])
            include_columns = None
            exclude_columns = [ ... ]
    '''

    def __init__(self, src, **kwargs):
        self.src = src
        self.mapper = orm.object_mapper(src)

    def dict(self, encoder=BaseEncoder(), **kwargs):
        data = dict()

        include_columns = kwargs.get('include_columns')
        exclude_columns = kwargs.get('exclude_columns')

        include_relations = kwargs.get('include_relations')
        exclude_relations = kwargs.get('exclude_relations')
        
        if exclude_columns is None and include_columns is None:
            raise ValueError('include_colums or exclude_columns required')

        # Iterate on all MapperProperty objects.
        # A mapped column is represented as an instance of ColumnProperty and a
        # relationship() is represented as an instance of RelationshipProperty.
        for prop in self.mapper.iterate_properties:

            # An object attribute that corresponds to a table column 
            # Public constructor is the orm.column_property() function.
            if isinstance(prop, orm.properties.ColumnProperty) and\
            ((include_columns is True or prop.key in include_columns) or\
             (include_columns is None and prop.key not in exclude_columns)):
                data[prop.key] = encoder(getattr(self.src, prop.key))

            # An object property that holds a single item or list of items that
            # correspond to a related database table.
            elif isinstance(prop, orm.properties.RelationshipProperty) and\
            ((include_relations == '*' or prop.key in include_relations) and\
             (prop.key not in exclude_relations or exclude_relations != '*')):
                obj = getattr(self.src, prop.key)

                # A many-to-many relationship (secondary=)
                if isinstance(obj, orm.collections.InstrumentedList):
                    data[prop.key] = [self.__class__(i).dict(encoder)\
                                      for i in obj]
                elif isinstance(obj, orm.dynamic.AppenderMixin):
                    # TODO
                    pass
                elif isinstance(obj, orm.dynamic.AppenderQuery):
                    # TODO
                    pass
                elif obj is not None:
                    data[prop.key] = self.__class__(obj).dict(encoder)

        return data

    def json(self, encoder=BaseEncoder(), fp=None, **kwargs):
        return json.dump(self.dict(encoder, **kwargs), fp) if fp else\
               json.dumps(self.dict(encoder, **kwargs))

    def xml(self, encoder=PrimitiveStrExport(), fp=sys.stdout, **kwargs):

        def _build_node(key, value, parent):
            elem = et.SubElement(parent, key)

            if isinstance(value, dict):
                for (k, v) in value.iteritems():
                    _build_node(k, v, elem)
            elif isinstance(value, (list, tuple, set, frozenset)):
                for (cpt, item) in enumerate(value):
                    _build_node('%s_%s' % (key, cpt), item, elem)
            else:
                elem.text = value

        root = et.Element('content')

        for (key, value) in self.dict(converter, **kwargs).iteritems():
            _build_node(key, value, root)

        tree = et.ElementTree(root)
        tree.write(fp, encoding='utf-8')
