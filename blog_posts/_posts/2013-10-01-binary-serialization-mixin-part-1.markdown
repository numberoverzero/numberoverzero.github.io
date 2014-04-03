---
layout: post
title:  "Binary Serialization Mixin: Requirements (Part 1)"
---

### *From the Archives*

*This is a series from my old blog on developing [origami][origami], when I was still planning on using some clever descriptor/metaclass magic.  Most of that was swapped out for performance and maintainability reasons, but it's been a useful reference when I've had to rebuild various magic inspection components*

# Navigation

Part 1: Requirements

[Part 2: Descriptors][part-2]

[Part 3: Metaclasses][part-3]

[Part 4: More Metaclasses][part-4]

# Introduction

I've been working on a project that requires serializing objects.  I could use Google's [protobuf][protobuf], but this seemed like a great opportunity to see what I could do with python.  Of course, less painful serialization isn't a new concept.

I have some preferences for how this serialization fits in with my existing code, and a few of them have been notably complex:

1. Many values fit in one or two bytes at most - booleans fit in a bit, color channels fit in 1 byte.  Any solution needs to allow bit-width specification.
2. I shouldn't need to specify the bit-width of every value.  Reasonable defaults should exist that can be dropped in where appropriate.
3. Serialization shouldn't get in the way, and I shouldn't have to give it much thought when I write my classes.
4. I should be able to drop into the details when a class requires custom serialization.
5. Performance overhead, both time and space, should be as low as possible.  Per-instance overhead is almost entirely unacceptable.
6. Serializable classes should be nestable, and the overhead for nesting should be as low as possible.

There's tension in these requirements.  The first suggests explicitly declaring every field's width every time, while the second encourages providing defaults for common fields (like ints).  The second and fourth are also clashing since defaults will not always be space-optimal.

Keeping time and space overhead low suggests we store all of the serialization metadata on the classes instead of the instances, so we'll probably end up with metaclasses.  Before that though, I wanted to see what a solution looked like without diving into metaclasses.

# Interface

I'll be using the excellent [bitstring][bitstring] package for the value packing and unpacking, and [this recipe][flatten-recipe] for flattening irregular lists.

``` python
import bitstring
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

class SerializableMixin:
    serializable_format = ''
    serializable_values = []

    def deserialize(self, values, offset=0):
        return offset

def serialize(obj):
    fmt = obj.serializable_format
    flat\_values = flatten(obj.serializable\_values)
    values = list(flat_values)
    return bitstring.pack(fmt, *values)

def deserialize(obj, bitstream):
    fmt = obj.serializable_format
    values = bitstream.unpack(fmt)
    obj.deserialize(values)
```

There isn't too much here, but let's try to break it down.  bitstring offers a few ways to pack values, and suggests that the best performance can be had when packing all values at once using a format string.  Therefore, we assume an interface where the object being packed is able to collect all of the values in its attributes (and any of its attributes' serializable attributes)and provide the format string for them.

If we didn't assume we could know all the serializable attributes at once, we would instead walk the attributes of the class, packing each value iteratively.  Where does flatten come in?  bitstring.pack expects all of the values at once, hence *values in the pack call.  Some of our serializable classes will return a single value to serialize, while others will return many (such as nested serializable classes).

To build some concrete examples, we'll first create two serializable classes to take care of the heavy lifting.  The first lets us nest objects, and the second is a nicer wrapper around a single serializable value (since the interface expects a list for serializable values).

# Building Blocks

``` python
class Serializable(base.SerializableMixin):
    '''List of attrs on the class that can be serialized'''
    serializable_attrs = []

    @property
    def serializable_format(self):
        attr_fmt = lambda attr_name: getattr(self, attr_name).serializable_format
        return ', '.join(map(attr_fmt, self.serializable_attrs))

    @property
    def serializable_values(self):
        attr_values = lambda attr_name: getattr(self, attr_name).serializable_values
        return map(attr_values, self.serializable_attrs)

    def deserialize(self, values, offset=0):
        for attr in self.serializable_attrs:
        offset = getattr(self, attr).deserialize(values, offset)
        return offset

    def __str__(self):
        items = zip(self.serializable_attrs, self.serializable_values)
        str_items = ', '.join('{}={}'.format(*item) for item in items)
        return self.__class__.__name__ + '(' + str_items + ')'

class ScalarSerializable(base.SerializableMixin):
    @property
    def serializable_values(self):
        return self.value

    def deserialize(self, values, offset=0):
        self.value = values[offset]
        return offset + 1
```

At this point we're missing the mark on a lot of the requirements outlined.  A quick rundown:

* **Bit-level specification**: I can pass bit width in the serializable_format attribute, so we're good so far.
* **No reasonable defaults**: The Serializable class expects all attributes to be SerializableMixins, so we can't include raw ints or lists as attributes.
* **Getting in the way**: If I want to serialize an integer with the ScalarSerializable, I can't treat it like a normal class - I need to set its value attribute instead of assigning directly.
* **Dropping into the details**: Not a problem, since right now everything's directly accessible.
* **Performance overhead**: Really bad right now, since we recalculate the entire format every time we serialize or deserialize the object.  Space is pretty good.
* **Nestable**: We've got netable, since Serializable calls through to each of its attributes' respective functions (eg. serializable\_format grabs the serializable\_format of each of its attributes to construct its own)

Before we start trying to fix these we should try using them and pick out the problems directly.

# Basic Example

``` python
class Channel(ScalarSerializable):
    serializable_format = 'uint:8'
    value = 0

class Color(Serializable):
    serializable_attrs = ['r', 'g', 'b']

    def __init__(self):
        self.r = Channel()
        self.g = Channel()
        self.b = Channel()

color = Color()
color.r.value = 201
color.g.value = 202
color.b.value = 203

color2 = Color()

s = serialize(color)
deserialize(color2, s)

print(color)
print()
print(color2)
```

Not too bad.  Let's get a list of areas for improvement and how to address each:

1. Declaring serializable attributes is a bit annoying, but not every attribute should be serialized.  Hopefully we can find a compromise; metaclasses provide access to attributes at class creation, perhaps that can be leveraged...
2. I know the serializable attributes at class creation (named in serializable\_attrs) and I'm probably not changing the serialized format much, so cleaning out of the \_\_init\_\_ function would be nice.  Metaclasses should also help here.
3. I want to set color.[r,g,b] directly instead of using color.r.value etc.  One way to fix this is overloading the \_\_[get,set]attr\_\_ functions on the class.  Descriptors are the other option, but that could introduce complexity with nesting.
4. Not directly related to serialization, but if I know my attributes ahead of time, it would be nice if I could pass r, g, b as keyword arguments to the init function without writing a tedious \_\_init\_\_ function that just passes values through.

[Next post][part-2] will introduce some basic metaclass examples, as well as a first pass at solving some of these problems.

[origami]: https://github.com/numberoverzero/origami
[protobuf]: http://code.google.com/p/protobuf/
[bitstring]: http://code.google.com/p/python-bitstring/
[flatten-recipe]: http://stackoverflow.com/a/2159079
[part-1]: {% post_url 2013-10-01-binary-serialization-mixin-part-1 %}
[part-2]: {% post_url 2013-10-02-binary-serialization-mixin-part-2 %}
[part-3]: {% post_url 2013-10-03-binary-serialization-mixin-part-3 %}
[part-4]: {% post_url 2013-10-04-binary-serialization-mixin-part-4 %}
