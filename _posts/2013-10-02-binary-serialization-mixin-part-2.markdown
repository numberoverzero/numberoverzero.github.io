---
layout: post
title:  "Binary Serialization Mixin: Descriptors (Part 2)"
---

### *From the Archives*

*This is a series from my old blog on developing [origami][origami], when I was still planning on using some clever descriptor/metaclass magic.  Most of that was swapped out for performance and maintainability reasons, but it's been a useful reference when I've had to rebuild various magic inspection components*

# Navigation

[Part 1: Requirements][part-1]

Part 2: Descriptors

[Part 3: Metaclasses][part-3]

[Part 4: More Metaclasses][part-4]

# Where were we?

This post will look at how to wrap functions and classes, trying to keep the syntactic overhead low.  Here's the sample implementation we had from the previous post:

{% highlight python %}
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
{% endhighlight %}

The biggest annoyance by far is that my r, g, b attributes can't be treated like the integers they wrap - I'm forced to set each of their 'value' attributes directly. Worse, any time I add or remove an attribute to the Color class I need to update two places: serializable_attrs and the init function. I want to be able to treat the r, g, b attributes like what they are: ints. But I also want each to be packed into 1 byte since they will only ever have values on the range [0, 255]. Here's what I want.

### Ideal End Result

{% highlight python %}
class Channel(BASE_CLASS_X):
    serializable_format = 'uint:8'

class Color(BASE_CLASS_Y):
    r = Channel(100)
    g = Channel(101)
    b = Channel(102)

color = Color(r=201, g=202, b=203)
color2 = Color()

s = serialize(color)
deserialize(color2, s)

print(color)
print()
print(color2)
{% endhighlight %}

Making sure we're on the same page, here's what I want out of the above:

1. Each color class has 3 attributes, and each one is a channel object.
2. I want the default value for r, g, b, to be 100, 101, 102 respectively.
3. I should be able to serialize and deserialize the Color class, since all of its declared attributes are serializable.
4. Because I've declared my serializable fields at **class creation** I expect the serializable format to be a string attribute on the Color class, such that it never needs to be computed again.
5. Also, notice that **the value attribute of the Channel class is gone**. I want to interact with each channel like a python int.

## Reality

Ignore for a moment that BASE_CLASS_X and BASE_CLASS_Y aren't defined. There's a serious problem: the value of the r attribute on the Color class is an instance of the Channel class when the Color class is defined - how can we instantiate it per Color instance? Worse, we can't even capture the arguments passed to Channel to duplicate the instantiation, since the instantiation happens before the assignment (or addition to the attrs variable passed to Color's metaclass, as we'll see later). I can think of two solutions:

1. Assuming that all the declared attributes are serializable, we can store their serialized form on the class when it's created, and then deserialize it into a new instance of that class when a new Color class is created. **Pros**: the declaration is exactly what we'd use for a single instance - we get class-level format strings without losing the syntax we were already using for serializable classes. **Cons**: Logic that runs on initialization but not deserialization is missed. Depending on how expensive the serialization/deserialization is for a class, this could get pricy.
2. Wrap the class Channel in a function that defers initialization and stores the arguments passed so that we can duplicate the initialization when a new instance of Color is created. **Pros**: The Channel class will truly be initialized, not just deserialized. Depending on the size of the args and complexity of serialization, this could be faster than the previous method. **Cons**: We're adding syntax somewhere in the declaration - it might be wrapping the class, or it could be wrapping the entire *args, **kwargs body. Either way, we're adding an opaque layer to the code that wasn't there before.

The second approach is how Django handles this question, but given the layers of validation and coercion and other various hooks that their fields have, it would be impractical to use the first. In our case however, either could probably do the job equally well. I've decided to use the second, since declarative classes with package-specific fields aren't uncommon, and if we're careful we can probably keep the syntax overhead very low.

# Descriptors

Descriptors probably aren't too magical within the context of python magic, but for some reason it took me longer to wrap my head around them than metaclasses. The python docs offer a good overview on this topic, but in a nutshell, descriptors are a way to override attribute access for an object in python. Let's start with an example:

{% highlight python %}
class Field:
    def __init__(self, name, default):
        self.name = name
        self.default = default

    def __get__(self, obj, cls):
        try:
            return obj.__dict__[self.name]
        except (AttributeError, KeyError):
            return self.default

    def __set__(self, obj, val):
        obj.__dict__[self.name] = val

class Color:
    r = Field('r', 100)
    g = Field('g', 101)
    b = Field('b', 102)

color = Color()
color2 = Color()

print("Same default value")
print(color.r)
print(color2.r)
print()

color.r = 0
print("Changing the value for one instance doesn't impact the other instances")
print(color.r)
print(color2.r)
print()

print("The type of each channel is int, since that's what the default is.")
print("Our Field class is nowhere to be seen in our color instances.")
print(type(color.r), type(color.g), type(color.b))
print()

print("There are no Field instances in the color's __dict__ either:")
print(color.__dict__)
print()
{% endhighlight %}

Descriptors invert the attribute lookup - when we use color.r, the color instance checks for the variable r and finds a variable with a \_\_get\_\_ function. It passes itself into the get function of the descriptor - in this case, it returns the result of Field.\_\_get\_\_(, self, Color) where is the field instance from the class declaration line "r = Field('r', 100)" and self is the instance of color that we tried to get the r attribute of.

Our descriptor chooses to store the actual value it references inside the \_\_dict\_\_ of the object that's looking it up, but we could have our own custom mapping that we use to keep track of values. This demonstrates an important point: `some_object.foo` is the same as `getattr(some_object, 'foo')` but neither of them is necessarily the same as `some_object.__dict__['foo']`. That is to say, while attribute lookup usually ends up pulling things from the \_\_dict\_\_ value, this isn't necessarily the case.

This is a nice pattern to get rid of that pesky "value" attribute that we had to tack on to every channel we modified (color.r.value -= 10). Now, we make r a Descriptor, and it does the pass through to \_\_dict\_\_ for us, and we can use color.r -= 10 once again.

We still haven't addressed the initialization problem, since passing an instance of the Channel class into the field as the default value means we get the same Channel for every instance. We've also got a second problem - we repeat the attribute name when we declare the field - r = Field('r', 100). It's not terrible, but it's still annoying and we can do better. Metaclasses will solve this for us since we can get the name of the attribute we're assigning to, and set the field's name attribute when the containing class is being created.

To address the instantiation problem, we can use the following pattern:

{% highlight python %}
class InitWrapper:
    def __init__(self, cls, *args, **kwargs):
        print("This is InitWrapper's init")
        print("Captured args: ", args)
        print("Captured kwargs: ", kwargs)
        self.cls = cls
        self.args = args
        self.kwargs = kwargs

    @property
    def instance(self):
        return self.cls(*(self.args), **(self.kwargs))

class Foo:
    def __init__(self, first, last, a='a', b='b'):
        self.first = first
        print("Now we're in Foo's init")
        print("First is:", first)
        print("Last is:", last)
        print("a is:", a)
        print("b is:", b)

print("Creating a Foo")
my_foo = Foo('John', 'Smith', b='blah')
print()

print("Creating a wrapped Foo that we can instantiate multiple times.")
my_foo_wrapper = InitWrapper(Foo, 'Jane', 'Doe', b='blargh')
print()

print("Instantiating one of our wrapped foos")
my_new_foo = my_foo_wrapper.real_init
print()

print("Instantiating another wrapped foo")
my_other_new_foo = my_foo_wrapper.real_init
print()

print("Both instances have different name attributes")
my_new_foo.first = "First"
my_other_new_foo.first = "Second"
print(my_new_foo.first)
print(my_other_new_foo.first)
print()
{% endhighlight %}

Also, we can create a function that just wraps the class so our initialization can look almost the same as the unwrapped initialization:

{% highlight python %}
from functools import wraps

def f(cls):
    @wraps(cls)
    def init(*args, **kwrags):
        return InitWrapper(cls, *args, **kwargs)
    return init

a_foo = Foo('John', 'Smith', b='blah')
foo_factory = f(Foo)('John', 'Smith', b='blah')
equivalent_foo_factory = InitWrapper(Foo, 'John', 'Smith', b='blah')
{% endhighlight %}

By combining these two classes, we can get attribute pass-through from the Descriptor protocol, and deferred initialization so that we declare fields as though they were declared on self instead of the class. Here's the final Field class, and currying function f:

{% highlight python %}
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
{% endhighlight %}

Using this class, the "Ideal End Result" code would now read:

{% highlight python %}
class Channel(BASE_CLASS_X):
    serializable_format = 'uint:8'

class Color(BASE_CLASS_Y):
    r = f(Channel)(100)
    g = f(Channel)(101)
    b = f(Channel)(102)

color = Color(r=201, g=202, b=203)
color2 = Color()

s = serialize(color)
deserialize(color2, s)

print(color)
print()
print(color2)
{% endhighlight %}

Wrapping the class looks a little strange, but it's still pretty readable - and easy to add wherever it's needed.

That's it for part 2. We've got a formula for a low-overhead syntax that allows us to use the full initialization signature of an attribute at class definition while still allowing per-instance versions of those variables, which puts us in a good spot when we use metaclasses to generate serialization strings. We haven't done any work on sane defaults for built-in classes like int. I suspect those options will become clear once we have a working declarative metaclass to get at our Field instances.  [Next up: Metaclasses][part-3].

[origami]: https://github.com/numberoverzero/origami
[part-1]: {% post_url 2013-10-01-binary-serialization-mixin-part-1 %}
[part-2]: {% post_url 2013-10-02-binary-serialization-mixin-part-2 %}
[part-3]: {% post_url 2013-10-03-binary-serialization-mixin-part-3 %}
[part-4]: {% post_url 2013-10-04-binary-serialization-mixin-part-4 %}
