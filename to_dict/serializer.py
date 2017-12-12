from datetime import datetime, date
import logging

from collections import Iterable
from lib.timezones import to_local_time, format_date, format_datetime


logger = logging.getLogger('serializer')
logger.setLevel(logging.INFO)


class Serializer(object):
    simple_types = (int, str, float, bytes, bool, type(None))
    _WILDCARD = '*'
    _DELIM = '.'
    _NEGATION = '-'

    def __init__(self, **kwargs):
        """
        :is_greedy: bool
        :date_format: str Babel-format
        :datetime_format: str Babel-format
        :to_user_tz: bool
        """
        self.kwargs = kwargs
        self._keys = {}

    def __call__(self, value, schema=()):
        logger.info('Called with KEYS:%s VALUE:%s' % (schema, value))
        if callable(value):
            value = value()

        if isinstance(value, self.simple_types):
            return value

        elif isinstance(value, datetime):
            return self.serialize_datetime(value)

        elif isinstance(value, date):
            return self.serialize_date(value)

        elif isinstance(value, Iterable):
            return self.serialize_iter(value)

        elif isinstance(value, SerializerMixin):
            self._set_schema(
                self.merge_schemas(value.__schema__, schema)
            )
            return self.serialize_model(value)

        elif isinstance(value, dict):
            self._set_schema(schema)
            return self.serialize_dict(value)

        else:
            raise IsNotSerializable('Malformed value')

    @property
    def is_greedy(self):
        return bool(self.kwargs.get('is_greedy', True))

    @property
    def to_user_tz(self):
        return bool(self.kwargs.get('to_user_tz', False))

    @property
    def datetime_format(self):
        return self.kwargs.get('datetime_format') or '%Y-%m-%d %H:%M'

    @property
    def date_format(self):
        return self.kwargs.get('date_format') or '%Y-%m-%d'

    def _fork(self, key, value):
        """
        Process data in a separate serializer
        :param key:
        :param value:
        :return: serialized value
        """
        if isinstance(value, self.simple_types):
            return value
        serializer = Serializer(**self.kwargs)
        return serializer(value, schema=self._get_sub_schema(key=key))

    def _negate(self, key):
        return '%s%s' % (self._NEGATION, key)

    def _is_negation(self, key):
        return key.startswith(self._NEGATION)

    def _admit(self, key):
        if self._is_negation(key):
            return key[len(self._NEGATION):]
        return key

    def _is_valid(self, key):
        if self._negate(key) in self._keys:
            if not self._keys[self._negate(key)]:  # If tail is empty
                return False
        if self._WILDCARD in self._keys:
            return True
        return key in self._keys or self.is_greedy and not key.startswith('_')

    def _set_schema(self, keys):
        for k in keys:
            head, *tail = k.split(self._DELIM)  # -prop1.prop2.* --> ['-prop1', 'prop2', '*']
            if head in self._keys:
                if tail:
                    self._keys[head].append(tail)
            else:
                self._keys[head] = [tail] if tail else []
        logger.info('Set KEYS:%s' % self._keys)

    def _get_sub_schema(self, key):
        keys = []
        for k in self._keys.get(key, []):
            if k:
                keys.append(k)
        for k in self._keys.get(self._negate(key), []):
            if not k:
                raise Exception('Excluded KEY:%s has no access to subkeys' % k)
            k[0] = self._negate(k[0])  # move negation mark to next elm
            keys.append(k)
        return [self._DELIM.join(k) for k in keys]  # ['-prop1', 'prop2', '*'] --> -prop1.prop2.*

    def merge_schemas(self, *args):
        """
        Merges lists of string-keys, priority grows from left to right
        :param args: tuple of lists of keys
        :return: list
        """
        logger.info('Merge schemas {}'.format(args))
        lists = list(args)
        lists.reverse()
        res = set()
        while lists:
            keys = lists.pop()
            for k in keys:
                if self._is_negation(k):
                    if self._admit(k) in res:
                        res.remove(self._admit(k))
                else:
                    if self._negate(k) in res:
                        res.remove(self._negate(k))
                res.add(k)
        return res

    def serialize_datetime(self, value):
        if self.to_user_tz:
            value = to_local_time(value)
            return format_datetime(value, self.datetime_format, rebase=False)
        return value.strftime(self.datetime_format)

    def serialize_date(self, value):
        if self.to_user_tz:
            return format_date(value, self.date_format, rebase=False)
        return value.strftime(self.date_format)

    def serialize_iter(self, value):
        res = []
        for v in value:
            try:
                res.append(self(v))
            except IsNotSerializable:
                continue
        return res

    def serialize_dict(self, value):
        res = {}
        for k, v in value.items():
            if self._is_valid(k):
                res[k] = self._fork(key=k, value=v)
            else:
                logger.info('Skipped KEY:%s' % k)
        return res

    def serialize_model(self, value):
        res = {}
        for k in value.get_model_keys():
            if self._is_valid(k):
                v = getattr(value, k)
                res[k] = self._fork(key=k, value=v)
            else:
                logger.info('Skipped KEY:%s' % k)
        return res


class IsNotSerializable(Exception):
    pass


class SerializerMixin(object):
    """Mixin for retrieving public fields of sqlAlchemy-model in json-compatible format"""
    __schema__ = ()

    def get_model_keys(self):
        return self._sa_instance_state.attrs.keys()

    def to_dict(self, schema=(), is_greedy=True, date_format=None, datetime_format=None, to_user_tz=False):
        r"""
        Returns SQLAlchemy model's data in JSON compatible format\n

        :param schema: iterable with names of properties to grab or ignore (see exact syntax in example)
        :param is_greedy: bool grab or not properties which are not in keys var
        :param date_format: str in Babel format
        :param datetime_format: str in Babel format
        :param to_user_tz: whether or not convert datetimes to local user timezone (Babel)

        :return: data: dict

        Example:
            class Model1(db.Model):
                prop1 = ...
                prop2 = ...

            class Model2(db.Model):
                prop1 = ...
                prop2 = ...
                prop3 = db.relationship('Model3')

            class Model3(db.Model):
                prop1 = ...
                prop2 = ...

            class SQLAlchemyModel(db.Model, Serializer)
                __private__ = {'rel3'}
                prop1 = db.relationship('Model1', uselist=False)
                prop2 = db.relationship('Model2')
                prop3 = db.Column(ARRAY(db.String)))
                prop4 = db.Column(db.String))

            model = SQLAlchemyModel.query.one()

            model.to_dict(
                keys=('prop4', 'prop2.prop3.prop1', 'prop1.prop1', '-prop3',)
            )

            {
                'prop1': {'prop2':...,},
                'prop2': [{
                    'prop1':...,
                    'prop2':...,
                    'prop3':[{'prop2':...}]
                }],
                'prop3': [....]
            }

        """
        s = Serializer(
            is_greedy=is_greedy,
            date_format=date_format,
            datetime_format=datetime_format,
            to_user_tz=to_user_tz
        )
        return s(self, schema=schema)
