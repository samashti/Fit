"""FIT file data message."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"


import logging
import datetime

from Fit.data_field import DataField
from Fit.dev_data_field import DevDataField
from Fit.message_type import MessageType


logger = logging.getLogger(__name__)


class DataMessageDecodeContext():
    """Class that holds data used across decoding of all DataMessages."""

    def __init__(self):
        self.matched_timestamp_16 = None
        self.last_timestamp = None
        self.last_absolute_timestamp = None


class DataMessage():
    """Class decodes and holds a FIT file data message."""

    def __init__(self, definition_message, fit_file, measurement_system, context):
        """Return a DataMessage instance decoded from the supplied FIT file using the supplied definition message."""
        self.definition_message = definition_message
        self.context = context
        self._fields = {}
        self.file_size = 0
        message_fields = {}
        for index in range(definition_message.fields):
            data_field = DataField(fit_file, definition_message, definition_message.field_definitions[index], measurement_system)
            self.file_size += data_field.file_size
            # expand subfields?
            field_value = data_field._field_value()
            subfield_names = field_value.subfield_names()
            if subfield_names is not None:
                for subfield_name in subfield_names:
                    subfield_value = field_value[subfield_name]
                    subfield_formal_name = subfield_value.field.name
                    if subfield_formal_name in message_fields:
                        message_fields[subfield_formal_name]._value.value += subfield_value._value.value
                    else:
                        message_fields[subfield_formal_name] = subfield_value
            else:
                message_fields[data_field._field_name()] = data_field._field_value()
        self.__convert_fields(message_fields, measurement_system)
        self.__convert_dev_fields(fit_file, definition_message, measurement_system)
        self.__track_time()

    def __control_field_value(self, field, message_fields, control_field_name):
        control_field = message_fields.get(control_field_name)
        if control_field is not None:
            return control_field.value
        logger.debug('Missing control field %s for %r in message %r', control_field_name, field, message_fields)

    def __convert_fields(self, message_fields, measurement_system):
        for field_value in message_fields.values():
            field = field_value.field
            dependant_field_func = getattr(field, 'dependant_field', None)
            if dependant_field_func:
                control_values = [self.__control_field_value(field, message_fields, control_field) for control_field in field._dependant_field_control_fields]
                field_value.field = dependant_field_func(control_values)
                field_value.reconvert(measurement_system)
            self._fields[field_value.field.name] = field_value

    def __convert_dev_fields(self, fit_file, definition_message, measurement_system):
        if definition_message.has_dev_fields:
            for index in range(definition_message.dev_fields):
                data_field = DevDataField(fit_file, definition_message, definition_message.dev_field_definitions[index], measurement_system)
                self.file_size += data_field.file_size
                field_value = data_field._field_value()
                self._fields[field_value.field.name] = field_value

    def __track_time(self):
        if 'timestamp' in self._fields:
            timestamp = self._fields['timestamp'].value
            self.context.last_absolute_timestamp = timestamp
            self.context.matched_timestamp_16 = None
            self.timestamp = timestamp
        else:
            timestamp_16_field = self._fields.get('timestamp_16')
            if timestamp_16_field is not None:
                if timestamp_16_field.value is not None:
                    self.timestamp = self.__timestamp16_to_timestamp(timestamp_16_field.value)
                else:
                    # This should not happen, if the timestamp16 field exists, it should not be None
                    # Issue #21: seen on Ubuntu on Windows
                    logger.error('timestamp16 with value None: %r', self._fields)
                    self.timestamp = self.context.last_timestamp
            else:
                self.timestamp = self.context.last_timestamp
        self.context.last_timestamp = self.timestamp

    def __timestamp16_to_timestamp(self, timestamp_16):
        if self.context.matched_timestamp_16:
            if timestamp_16 >= self.context.matched_timestamp_16:
                delta = timestamp_16 - self.context.matched_timestamp_16
            else:
                delta = (self.context.matched_timestamp_16 - 65535) + timestamp_16
        else:
            self.context.matched_timestamp_16 = timestamp_16
            delta = 0
        return self.context.last_absolute_timestamp + datetime.timedelta(seconds=delta)

    def type(self):
        """Return the message type."""
        return self.definition_message.message_type

    def to_dict(self, ignore_none_values=False, lower_case=True):
        """Return the message as dictionary of field name-value entries."""
        fields = {}
        for field_name, field_value in self._fields.items():
            if field_name == 'timestamp_16':
                fields['timestamp'] = self.timestamp
            elif not ignore_none_values or field_value.value is not None:
                fields[field_name.lower() if lower_case else field_name] = field_value.value
        return fields

    def __getitem__(self, name):
        """Return a message field's value given the field name."""
        return self._fields.get(name)

    def __iter__(self):
        """Iterate over the data message's fields."""
        return iter(self._fields)

    def keys(self):
        """Return the message's field's names."""
        return self._fields.keys()

    def items(self):
        """Iterate over the data message's fields."""
        return self._fields.items()

    def values(self):
        """Return the message's field's values."""
        return self._fields.values()

    def get(self, fieldname, default=None):
        """Return the field with named fieldname if preesent otherwise return default."""
        if fieldname in self.keys():
            return self[fieldname]
        return default

    def __str__(self):
        """Return a string representation of a DataMessage instance."""
        fields_str = "".join(["%s, " % value for value in self._fields.values()])
        return f'{self.__class__.__name__}: {repr(self.type())}: {fields_str}'

    def __repr__(self):
        """Return a string representation of a DataMessage instance."""
        return f'{self.__class__.__name__}({repr(self.type())}, {repr(self.timestamp)}: {repr(self._fields)})'
