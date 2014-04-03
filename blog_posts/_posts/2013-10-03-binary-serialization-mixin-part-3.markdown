---
layout: post
title:  "Binary Serialization Mixin: Metaclasses (Part 3)"
---

### *From the Archives*

*This is a series from my old blog on developing [origami][origami], when I was still planning on using some clever descriptor/metaclass magic.  Most of that was swapped out for performance and maintainability reasons, but it's been a useful reference when I've had to rebuild various magic inspection components*

# Navigation

[Part 1: Requirements][part-1]

[Part 2: Descriptors][part-2]

Part 3: Metaclasses

[Part 4: More Metaclasses][part-4]

# Where were we?

This post we're only going to create a metaclass that leverages some of the magic of the Field class - next post we tackle serialization-specific work in the metaclass.

We had just constructed Field, a descriptor class which wrapped the init args to a class to create a factory of sorts:

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

    def __get__(self, obj, cls):
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

And this was the target implementation that we're trying to facilitate:

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

Before we define either base class above, we're going to need a metaclass to do some of the heavy lifting. Those base classes are there to curtain off some of the magic, so users don't need to worry about how we're injecting their fields when they subclass Serializable.

As a reminder, all of this code is using Python3.3 - adapting it to work with 2.7 is possible, but when ordering of fields matters it can be a pain. Here's a metaclass that notifies us when it creates a new class, but otherwise does nothing:

``` python
class MetaNotifier(type):
    def __new__(cls, name, bases, attrs):
        print("I'm making a new class named " + name)
        return super().__new__(cls, name, bases, attrs)

class Foo(metaclass=MetaNotifier):
    name = "Bill"
    def __init__(self):
        print("I don't get called in this example")
    def random_func(self):
        print("That was unexpected")

print("End of example.")
```


We never created an instance of Foo, so its \_\_init\_\_ method wasn't called. The \_\_new\_\_ method in MetaNotifier was passed the name of the class Foo that we wanted to create, along with some other information about the class. It then returned a **class object** that Foo was assigned. Let's break down what each of those fields is:

* **cls**: The metaclass we're using. This is the self of a metaclass, not the class we're creating.
* **name**: The name of the class we're creating.
* **bases**: Tuple of the base objects of the class we're making. In our example, this is (object,) because the assumed base when none is declared is object.
* **attrs**: dictionary of attribute names => attribute values of the class we're building. In the example above, this attrs would be:

``` python
{
  '__init__': ,
  'name': 'Bill',
  'random_func':
}
```

Notice that we don't have the ordering of the attributes as we declared them. This is unacceptable for serialization, since we need consistent ordering. Luckily, Python 3 provides another method on the metaclass that lets us specify a structure to store attributes in, and we can use an ordered dictionary!

``` python
import collections

class MetaNotifier(type):
    @classmethod
    def __prepare__(cls, name, bases):
        return collections.OrderedDict()

    def __new__(cls, name, bases, attrs):
        print("I'm making a new class named " + name)
        return super().__new__(cls, name, bases, attrs)
```

Now the dictionary we get back is:

``` python
OrderedDict({
  'name': 'Bill',
  '__init__': ,
  'random_func':
})
```

Perfect. Inside of the \_\_new\_\_ function in MetaNotifier, we can manipulate these values - insert new values, change existing values, remove them entirely. Notice for example, that we could entirely remove any \_\_init\_\_ method that's defined for the class, or replace it with our own. To help with the field magic, we're going to be modifying a decent amount of this dictionary, including the init function.

# Hacking up the class dictionary

For the next few snippets, we're assuming that we are inside of the \_\_new\_\_ function above, before the return statement. The first thing we need is a(n ordered) dictionary of all the attributes that are instances of our special Field class. Here's how we can do that:

``` python
declared_fields = collections.OrderedDict()
for attr_name, attr_val in attrs.items():
    if isinstance(attr_val, Field):
        declared_fields[attr_name] = attr_val
        attr_val.name = attr_name
attrs['_declared_fields'] = declared_fields
```

Oh, that's nice. If we find a field, the first line will add it to our collection of fields - not too exciting. The second line, however, takes care of one of the open questions from part 2 - how do we set the field's name without repeating the string everywhere? Since the keys of the attribute dictionary are the names the attributes are assigned to, we can hand them over to the attributes they'll be named! That line gives the descriptor the name it will use when storing values in the instance dictionary. Finally, we push that dictionary of Fields back into attrs, so that instances of the class can get at the raw field objects if they need to, without being forced through those fields' __get__ and __set__ methods.

Next, we're going to wrap the init function of the class so that we create real versions of the Fields they declared in the class.

``` python
noop_init = lambda self, *a, **kw: None
real_init = attrs.get('__init__', noop_init)
def fake_init(self, *args, **kwargs):
    for field_name, field in self._declared_fields.items():
        setattr(self, field_name, field.instance)
    real_init(self, *args, **kwargs)
attrs['__init__'] = fake_init
```

The first two lines try to find an existing init method, and if there isn't one, we swap in a function that does nothing. Then, we go through each field in the \_declared\_fields dictionary (which was created above, sort of - inside of the init function, \_declarative\_fields is already tied to the class so we can get at it) and for each one, we create an instance (of the class passed to that field, with its args and kwargs) and set that on the object instance we initializing using setattr. We use setattr because this will trigger the \_\_get\_\_ function on the field that is mapped to self.field\_name. Finally, we call real\_init, which is the init function they've defined (if any) or our noop function and push that init function back into attrs.

The last section we'll add is a reasonable default for __str__ if one isn't provided:

``` python
if '__str__' not in attrs:
    def str_(self):
        cls_name = self.__class__.__name__
        fmt = lambda item: '{}={}'.format(*item)
        decl_iter = ', '.join(map(fmt, self._declared_fields.items()))
        return '{}({})'.format(cls_name, decl_iter)
    attrs['__str__'] = str_
```

# Putting it all together

Here's the final metaclass we'll be using for classes with declarative fields:

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
                fmt = lambda item: '{}={}'.format(*item)
                decl_iter = ', '.join(map(fmt, self._declared_fields.items()))
                return '{}({})'.format(cls_name, decl_iter)
            attrs['__str__'] = str_

        return super().__new__(cls, name, bases, attrs)
```

## Kicking the tires

Let's test it out (along with our Field class defined at the top of this post):

``` python
class Channel:
    def __init__(value, enabled=True):
        self.value = value
        self.enabled = enabled
    def __str__(self):
        return 'Channel({}, enabled={})'.format(self.value, self.enabled)

class Color(metaclass=DeclarativeMetaclass):
    r = f(Channel)(100)
    g = f(Channel)(101, False)
    b = f(Channel)(102)
    a = f(Channel)(103, enabled=False)

    def __str__(self):
        return 'Color(r={}, g={}, b={}, a={})'.format(self.r, self.g, self.b, self.a)

color1 = Color()
color2 = Color()

print("Created two colors, should be the same:")
print(color1)
print(color2)
print()

color1.r.value = 200
color2.a.enabled = True

print("Even though we didn't explicitly initialize different Channel objects,")
print("changes in one color object don't reflect in the other:")
print(color1)
print(color2)
print()
```

That's it for metaclasses (well, not really) and fields. [Next post][part-4], we subclass DeclarativeMetaclass to start adding our serialization layer in. This will primarily be computing the serialization\_format string and creating a subset of \_declared\_fields that are serializable, in case some declared fields aren't serializable.

[origami]: https://github.com/numberoverzero/origami
[part-1]: {% post_url 2013-10-01-binary-serialization-mixin-part-1 %}
[part-2]: {% post_url 2013-10-02-binary-serialization-mixin-part-2 %}
[part-3]: {% post_url 2013-10-03-binary-serialization-mixin-part-3 %}
[part-4]: {% post_url 2013-10-04-binary-serialization-mixin-part-4 %}
