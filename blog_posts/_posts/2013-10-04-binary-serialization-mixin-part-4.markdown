---
layout: post
title:  "Binary Serialization Mixin: More Metaclasses (Part 4)"
---

### *From the Archives*

*This is a series from my old blog on developing [origami][origami], when I was still planning on using some clever descriptor/metaclass magic.  Most of that was swapped out for performance and maintainability reasons, but it's been a useful reference when I've had to rebuild various magic inspection components*

# Navigation

[Part 1: Requirements][part-1]

[Part 2: Descriptors][part-2]

[Part 3: Metaclasses][part-3]

Part 4: More Metaclasses

# Where were we?

In our [last episode][part-3], we had a concise field wrapper that let us defer object instantiation so we could call the initializer (with all the args and kwargs specified at class declaration) each time we instantiated the class we were building.  We still didn't have anything related to serialization.  Today we finalize the metaclass and take stock of our final solution.  **Spoilers**: there's a better solution than Metaclasses, but the investigation's worth it.

### Field class

``` python
from functools import wraps

class Field:
    def __init__(self, cls, *args, **kwargs):
        '''
        Allows us to defer instantation of an attribute
        of a class from class creation
        '''
        self.cls = cls
        self.args = args
        self.kwargs = kwargs

    def __get__(self, obj, *args):
        return obj.__dict__[self.name]

    def __set__(self, obj, value):
        obj.__dict__[self.name] = value

    @property
    def instance(self):
        return self.cls(*(self.args), **(self.kwargs))

def f(cls):
    '''Wraps a class so it can Fieldatized'''
    @wraps(cls)
    def init(*args, **kwargs):
        return Field(cls, *args, **kwargs)
    return init
```

### DeclarativeMetaclass class

``` python
import collections
noop_init = lambda *a, **kw: None

class DeclarativeMetaclass(type):
    @classmethod
    def __prepare__(cls, name, bases):
        return collections.OrderedDict()

    def __new__(cls, name, bases, attrs):
        declared_fields = collections.OrderedDict()
        for attr_name, attr_val in attrs.items():
            if isinstance(attr_val, Field):
                declared_fields[attr_name] = attr_val
                attr_val.name = attr_name
        attrs['_declared_fields'] = declared_fields

        real_init = attrs.get('__init__', noop_init)
        def fake_init(self, *args, **kwargs):
            for field_name, field in self._declared_fields.items():
                setattr(self, field_name, field.instance)
            real_init(self, *args, **kwargs)
        attrs['__init__'] = fake_init

        if '__str__' not in attrs:
            def str_(self):
                cls_name = self.__class__.__name__
                # Note that this won't exactly work for fields, since
                # We'll get the string of the descriptor, not its value.
                fmt = lambda item: '{}={}'.format(*item)
                decl_iter = ', '.join(map(fmt, self._declared_fields.items()))
                return '{}({})'.format(cls_name, decl_iter)
            attrs['__str__'] = str_

        return super().__new__(cls, name, bases, attrs)
```

Pretty good, but there's no serialization logic in there. Let's change that.

# Let's get cereal

From the beginning of [part three][part-3], we wanted to be able to do the following:

``` python
class Channel(BASE_CLASS_X):
    serializable_format = 'uint:8'

class Color(BASE_CLASS_Y):
    r = f(Channel)(100)
    g = f(Channel)(101)
    b = f(Channel)(102)

color = Color(r=201, g=202, b=203)
color2 = Color()
```

So far we've got the attribute declaration down for the Color class, but we haven't incorporated the serializable\_format field. Let's change that. We're going to add this next bit to the \_\_new\_\_ function right after the chunk where declared\_fields are set up:

``` python
serial_fields = collections.OrderedDict()
for attr_name, attr_val in declared_fields.items():
    if isinstance(attr_val, SerializableMixin):
        serial_fields[attr_name] = attr_val
attrs['_serial_fields'] = serial_fields
```

Look familiar? Almost the same format as the declared\_fields setup above, but we're sorting out from those fields, the ones that implement the SerializableMixin interface. Now we can create the full serial\_format string for our class (since it's going to be made up of the format strings of all its attributes):

``` python
fmt_gen = (f.serial_format for f in serial_fields.values())
serial_format = ', '.join(fmt_gen)
attrs['serial_format'] = serial_format
```

Woohoo! Now we don't have to calculate that again - when we serialize the class, we'll have the complete format string to hand to bitstring for packing, which is a huge gain over packing value by value.

# Serializable base class: An end in sight?

That's all for the metaclass - we don't need to touch it again. It's done plenty of work for us - wrapping an init function so that field initialization can be deferred, packing up our serial\_format string so it doesn't need to be computed again (and improving our packing performance on the bitstring side) and providing us easy access to the serializable fields through the "\_serial\_fields" attribute, since we can't get the field itself using my\_object.attribute (since the field implements the descriptor protocol and overwrites the attribute lookup on the object).

But we're missing two thirds of the SerializableMixin interface - we don't have serializable_values or deserialize. Enter the Serializable base class:

``` python
class Serializable(SerializableMixin, metaclass=SerializableMetaclass):
    @property
    def serial_values(self):
        values = lambda field: field.serial_values(self)
        values_gen = map(values, self._serial_fields.values())
        return list(flatten(values_gen))

    def deserialize(self, values, offset=0):
        for field in self._serial_fields.values():
            offset = field.deserialize(self, values, offset)
        return offset

```

Notice that although this class doesn't declare any fields, the metaclass \_\_new\_\_ will be run when any subclass is defined, so fields that the inheriting class defines will be used in the serial_values function. flatten is the following utility function, which basically turns arbitrarily nested sequences into a single flat list:

``` python
import collections

def flatten(l, ltypes=collections.Sequence):
    l = list(l)
    while l:
        if isinstance(l[0], str):
            yield l.pop(0)
            continue
        while l and isinstance(l[0], ltypes):
            l[0:1] = l[0]
        if l:
            yield l.pop(0)

```

So for a class deriving from Serializable, the serial\_values function (property, really) will walk through the fields' serial\_values and create a flat list - whose order will exactly match the flattened serial\_format string we constructed in the metaclass! Nice!

deserialize will do the same sort of re-nesting - values is an array of objects whose position matches the position in the serial\_format string. Serializable will have each of its fields read as many objects as it needs, and expects those fields to return the new offset after reading. So a field that stores two values and gets an offset of n will return the offset n+2.

# Subclassing fields

There's one final problem to tackle before we're done: The Field object doesn't inherit from SerializableMixin, which means it doesn't support serial\_format, serial\_values, or deserialize. Let's clean that up quick, with the following two classes:

``` python
passthrough = lambda v: v

class ClassWrapperField(Field, SerializableMixin):
    def __init__(self, cls, *args, **kwargs):
        assert issubclass(cls, SerializableMixin)
        super().__init__(cls, *args, **kwargs)
        self.serial_format = self.cls.serial_format

    def serial_values(self, obj):
        return self.__get__(obj).serial_values

    def deserialize(self, obj, values, offset=0):
        return self.__get__(obj).deserialize(values, offset)

class RawSerialField(Field, SerializableMixin):
    def __init__(self, format='', default=None,
                 to_serial=passthrough, from_serial=passthrough):
        self.serial_format = format
        self.default = default
        self.to_serial = to_serial
        self.from_serial = from_serial

    def serial_values(self, obj):
        raw_object = self.__get__(obj)
        serial_object = self.to_serial(raw_object)
        return serial_object

    def deserialize(self, obj, values, offset=0):
        serial_object = values[offset]
        raw_object = self.from_serial(serial_object)
        self.__set__(obj, raw_object)
        return offset + 1

    @property
    def instance(self):
        return self.default
```

RawSerialField allows us to make the basic building blocks - ints, bools, etc. ClassWrapperField is used on any class that already subclasses SerializableMixin.

Notice that to get the serial\_values from a Field, or to deserialize a Field, we need the obj that the field is on, since we use the descriptor protocol's \_\_get\_\_ to retrieve the underlying value.
This is why the Serializable class passes self as its first argument in the serial\_values property and deserialize method.

# Everyone together now

Here's everything together, with the f function improved a bit to handle both serializable classes and raw fields. This also includes a bunch of code that we haven't seen since parts one or two, such as SerializableMixin and the serialize/deserialize functions. You can also grab everything below as a [gist][full-gist].

``` python
from functools import wraps
import collections
import bitstring

noop_init = lambda *a, **kw: None
passthrough = lambda v: v

def flatten(l, ltypes=collections.Sequence):
    l = list(l)
    while l:
        if isinstance(l[0], str):
            yield l.pop(0)
            continue
        while l and isinstance(l[0], ltypes):
            l[0:1] = l[0]
        if l:
            yield l.pop(0)

def serialize(obj):
    values = list(obj.serial_values)
    return bitstring.pack(obj.serial_format, *values)

def deserialize(obj, bitstream):
    object_array = bitstream.unpack(obj.serial_format)
    obj.deserialize(object_array)

class SerializableMixin(object):
    serializable_format = ''
    serializable_values = []

    def deserialize(self, values, offset=0):
        return offset

class Field(object):
    def __init__(self, cls, *args, **kwargs):
        '''
        Allows us to defer instantation of an attribute
        of a class from class creation
        '''
        self.cls = cls
        self.args = args
        self.kwargs = kwargs

    def __get__(self, obj, *args):
        return obj.__dict__[self.name]

    def __set__(self, obj, value):
        obj.__dict__[self.name] = value

    @property
    def instance(self):
        return self.cls(*(self.args), **(self.kwargs))

class ClassWrapperField(Field, SerializableMixin):
    def __init__(self, cls, *args, **kwargs):
        assert issubclass(cls, SerializableMixin)
        super().__init__(cls, *args, **kwargs)
        self.serial_format = self.cls.serial_format

    def serial_values(self, obj):
        return self.__get__(obj).serial_values

    def deserialize(self, obj, values, offset=0):
        return self.__get__(obj).deserialize(values, offset)

class RawSerialField(Field, SerializableMixin):
    def __init__(self, format='', default=None,
                 to_serial=passthrough, from_serial=passthrough):
        self.serial_format = format
        self.default = default
        self.to_serial = to_serial
        self.from_serial = from_serial

    def serial_values(self, obj):
        raw_object = self.__get__(obj)
        serial_object = self.to_serial(raw_object)
        return serial_object

    def deserialize(self, obj, values, offset=0):
        serial_object = values[offset]
        raw_object = self.from_serial(serial_object)
        self.__set__(obj, raw_object)
        return offset + 1

    @property
    def instance(self):
        return self.default

def f(*args, **kwargs):
    '''
    Wraps a SerializableMixin class so it can Fieldatized,
    or constructs a RawSerialField if kwargs are passed
    '''
    assert len(args) < 2  # If it's a SerializableMixin class,
                          # it should be exactly one arg
                          # and no kwargs.  If it's a RawSerialField,
                          # everything should be kwargs.

    if len(args) == 1 and not kwargs:
        cls = args[0]

        @wraps(cls)
        def init(*args, **kwargs):
            return ClassWrapperField(cls, *args, **kwargs)
        return init
    return RawSerialField(**kwargs)

class DeclarativeMetaclass(type):
    @classmethod
    def __prepare__(cls, name, bases):
        return collections.OrderedDict()

    def __new__(cls, name, bases, attrs):
        declared_fields = collections.OrderedDict()
        for attr_name, attr_val in attrs.items():
            if isinstance(attr_val, Field):
                declared_fields[attr_name] = attr_val
                attr_val.name = attr_name
        attrs['_declared_fields'] = declared_fields

        serial_fields = collections.OrderedDict()
        for attr_name, attr_val in declared_fields.items():
            if isinstance(attr_val, SerializableMixin):
                serial_fields[attr_name] = attr_val
        attrs['_serial_fields'] = serial_fields

        fmt_gen = (f.serial_format for f in serial_fields.values())
        serial_format = ', '.join(fmt_gen)
        attrs['serial_format'] = serial_format

        real_init = attrs.get('__init__', noop_init)

        def fake_init(self, *args, **kwargs):
            for field_name, field in self._declared_fields.items():
                setattr(self, field_name, field.instance)
            real_init(self, *args, **kwargs)
        attrs['__init__'] = fake_init

        if '__str__' not in attrs:
            def str_(self):
                cls_name = self.__class__.__name__
                fmt = lambda item: '{}={}'.format(
                    item[0], str(item[1].__get__(self)))
                decl_iter = ', '.join(map(fmt, self._declared_fields.items()))
                return '{}({})'.format(cls_name, decl_iter)
            attrs['__str__'] = str_

        return super().__new__(cls, name, bases, attrs)

class Serializable(SerializableMixin, metaclass=DeclarativeMetaclass):
    @property
    def serial_values(self):
        values = lambda field: field.serial_values(self)
        values_gen = map(values, self._serial_fields.values())
        return list(flatten(values_gen))

    def deserialize(self, values, offset=0):
        for field in self._serial_fields.values():
            offset = field.deserialize(self, values, offset)
        return offset
```

# Try it out

Here are some serializable classes, with some helpers for the field definitions.

``` python
uint8 = lambda: f(format='uint:8', default=0)
boolean = lambda: f(format='uint:1', default=False,
                    to_serial=int, from_serial=bool)

class Color(Serializable):
    def __init__(self, r, g, b, a):
        self.r = r
        self.g = g
        self.b = b
        self.a = a
    r = uint8()
    g = uint8()
    b = uint8()
    a = uint8()

class Tile(Serializable):
    enabled = boolean()
    color = f(Color)(122, 123, 124, 125)
    elite = boolean()
```

And to put those classes through their paces:

``` python
t = Tile()
print("Original tile:")
print(t)
print()

t.enabled = True
t.color.g = t.color.a = 100
print("Tile modified (using True instead of 1 for bool field)")
print(t)
print()

s = serialize(t)
print("Serialized tile data:")
print(s.bin)
print()

t2 = Tile()
print("Created new Tile (t2) to deserialize into:")
print(t2)
print()

deserialize(t2, s)
print("Deserialized tile data into t2.")
print("The following should be equal:")
print(t)
print(t2)
print()
```

The above should output:

```
Original tile:
Tile(enabled=False, color=Color(r=122, g=123, b=124, a=125), elite=False)

Tile modified (using True instead of 1 for bool field)
Tile(enabled=True, color=Color(r=122, g=100, b=124, a=100), elite=False)

Serialized tile data:
1011110100110010001111100011001000

Created new Tile (t2) to deserialize into:
Tile(enabled=False, color=Color(r=122, g=123, b=124, a=125), elite=False)

Deserialized tile data into t2.
The following should be equal:
Tile(enabled=True, color=Color(r=122, g=100, b=124, a=100), elite=False)
Tile(enabled=True, color=Color(r=122, g=100, b=124, a=100), elite=False)
```

# Spoilers

At the beginning I mentioned some spoilers. In the next part I'm going to talk about what happened to goal 3: serialization shouldn't get in the way. Looking at the demo above, it certainly has. We're forced to provide defaults, we're using currrying to defer instantiation, all because we need the format strings at class creation. Wouldn't it be great if we could just... add serialization to an already existing class without subclassing anything, just passing it a format string to say where which bits go? That's the goal of the most recent iteration of the serialization package. Here's what it looks like to use that:

``` python
from pyserializable import autoserializer, Serializer

s = Serializer()
autoserialized = autoserializer(s)

@autoserialized
class Address(object):
    serial_format = 'house_number=uint:7'

    def __init__(self, house_number=None):
        self.house_number = house_number

@autoserialized
class Person(object):
    serial_format = 'age=uint:10, address=Address, alive=uint:1'
    serial_attr_converters = {'alive': [int, bool]}

    def __init__(self, age=-1, alive=False, address=None):
        self.age = age
        self.alive = alive
        self.address = address or Address()

bill = Person(120, True, Address(10))
bill_data = s.serialize(bill)

#Deserialize by class
other_bill = s.deserialize(Person, bill_data)

#Deserialize into existing instance
another_bill = Person()
s.deserialize(another_bill, bill_data)
```

Looks much better without all those declarative fields, I think. But it was a fun journey to see what we would get out of it all :)

I don't think I'll be doing another multi-part on the current serialization code; there's still plenty of low-hanging performance optimizations to make, and a handful of features I want to add. After writing these last two sections, I'm ready to just hack away for a week or so.

[origami]: https://github.com/numberoverzero/origami
[full-gist]: https://gist.github.com/numberoverzero/5660533
[part-1]: {% post_url 2013-10-01-binary-serialization-mixin-part-1 %}
[part-2]: {% post_url 2013-10-02-binary-serialization-mixin-part-2 %}
[part-3]: {% post_url 2013-10-03-binary-serialization-mixin-part-3 %}
[part-4]: {% post_url 2013-10-04-binary-serialization-mixin-part-4 %}
