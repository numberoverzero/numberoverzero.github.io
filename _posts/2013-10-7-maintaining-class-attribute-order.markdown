---
layout: post
title:  "Python 2: Maintaining class attribute order"
---

I wish we were all on Python 3.  There are [so many cool things][beazley-meta] [PDF] to do in Python 3.  That's all one link, and it's amazing.  If you read through that whole thing and then come back here, probably hours later, most of this will seem absurd.  The rest of this post is solved in Python 3 with `__prepare__`.  And it lets you do lots more than what I'll be outlining below.

So Python 3 is pretty sweet.

# What are we trying to do

In Python 2, preserve attribute declaration order at class definition.

# Back up, what is \_\_prepare\_\_?

Python 3 introduced a very useful feature for metaprogramming: [\_\_prepare\_\_][pep-3115].

`__prepare__`: "is invoked as a function before the evaluation of the class body... \_\_prepare\_\_ returns a dictionary-like object which is used to store the class member definitions during evaluation of the class body..."

This lets us return an `OrderedDict` instead of the default `dict()`, which retains the attribute ordering information.

``` python
import collections
class OrderedMeta(type):

    @classmethod
    def __prepare__(cls, name, bases):
            return collections.OrderedDict()

    def __new__(cls, name, bases, attrs):
            for key, value in attrs.items():
                    print("="*20)
                    print("key: "+str(key))
                    print("value: "+str(value))
            return super().__new__(cls, name, bases, attrs)

class MyClass(metaclass=OrderedMeta):
    a = 10
    b = "Hello"
    c = list("charlie")
    d = False
```

From an interactive python session, the following is printed when `MyClass` is defined:

``` python
====================
key: __module__
value: __main__
====================
key: __qualname__
value: MyClass
====================
key: a
value: 10
====================
key: b
value: Hello
====================
key: c
value: ['c', 'h', 'a', 'r', 'l', 'i', 'e']
====================
key: d
value: False
```

# Python 2: The plan

This isn't a straight port since python 2.x doesn't have `__prepare__`, and we're forced to use a regular dictionary.  There's a clever but somewhat limited solution: wrap all attributes in a proxy which records the order it was created in.  When the attributes of the class are available in `__new__` sort on the create value, and stuff them back in the class attributes for future access.

## Sounds perfect!

Almost.  Now, all of our attributes are these wrapped classes.  Not for long - after sorting and storing the sort order unbox the original values and update the class dictionary.  Now the wrapper is discarded after class creation, and doesn't add any overhead when looking up/setting/getting those attributes.

The remaining problem is that every attribute must be wrapped with this special wrapper.  So the original example:

``` python
class MyClass(metaclass=OrderedMeta):
    a = 10
    b = "Hello"
    c = list("charlie")
    d = False
```

becomes:

``` python
class MyClass(metaclass=OrderedMeta):
    a = wrapper(10)
    b = wrapper("Hello")
    c = wrapper(list("charlie"))
    d = wrapper(False)
```

Of course, if you're already requiring each attribute to be wrapped with special sauce for some other application (seems likely), then it's not a problem.

# Python 2: Implementation

This has been used in a few places - I referred to [django's form fields][django-field] while working on the boxing/unboxing.  To the best of my knowledge, this is not thread safe.

``` python
# I know, I know, I saw the "stop using classes" talk too.
# This is a class so we can isinstance() to filter attributes,
# and to scope _ordering_counter so that I don't have a
# "global _ordering_counter" in a function somewhere.

class OrderingWrapper(object):
	_ordering_counter = 0
	def __init__(self, obj):
		self.obj = obj
		self._ordering_counter = OrderingWrapper._ordering_counter
		OrderingWrapper._ordering_counter += 1
		super(OrderingWrapper, self).__init__()

class OrderingMetaclass(type):
	def __new__(cls, name, bases, attrs):

            # Get a list of all attributes that are
            # really wrapped objects
            is_wrapper = lambda item: isinstance(item[1], OrderingWrapper)
            wrapped_attrs = filter(is_wrapper, attrs.iteritems())

            # Sort wrapped attributes
            wrapped_attrs.sort(key=lambda x: x[1]._ordering_counter)

            # Push the ordered list of attribute keys
            # back into the class for future use
            attrs['_ordered_attrs'] = [key for (key, value) in wrapped_attrs]

            # Unwrap attributes back into class dict now that we're
            # done storing the ordering information.
            for key, box in wrapped_attrs:
            	attrs[key] = box.obj

            return super(OrderingMetaclass, self).__new__(cls, name, bases, attrs)
```

This solution is limited in some non-obvious ways - namely, inheritance is broken since we never check/update ordering for any base classes.  This is addressed in django's [forms.py:get\_declared\_fields][django-getfields].  For the sake of keeping this example reasonable, we'll only handle immediate class attributes.

## Try it out

Load some values up:

``` python
# alias OrderingWrapper for readability
w = OrderingWrapper

class MyClass(object):
	__metaclass__ = OrderingMetaclass
	first_field = w(1)
	second_field = w("Hello")
	fake_third_field = False  # Not wrapped, won't be listed in our ordered attrs :(
	third_field = w(True)



print MyClass._ordered_attrs
assert 'fake_third_field' not in MyClass._ordered_attrs
assert 2 == MyClass._ordered_attrs.index(third_field)
```

## Extensions

So you've made the above code compatible with 2 and 3 (probably using six, see django links) AND you've got inheritance working again?  Here are a few more ideas:

1. Email me with a link to your updated implementation so I can include it in this post.  I'll eventually get around to inheritance, but if you want a reason to muck around with metaclasses, here's your excuse!

2. Transfer other state on the wrapper.  In the metaclass \_\_new\_\_ method, you can preserve other metadata that might have been saved in each wrapper.  This could be validation, caching, anything.  Because you can shove anything you want back into `attrs` before the class is constructed, you'll be able to access those values after the class is created, too.

[beazley-meta]: http://dabeaz.com/py3meta/Py3Meta.pdf
[pep-3115]: http://www.python.org/dev/peps/pep-3115/
[django-field]: https://github.com/django/django/blob/master/django/forms/fields.py#L47
[django-getfields]: https://github.com/django/django/blob/master/django/forms/forms.py#L32
