---
layout: post
title:  "functools.partial rocks!"
---

In a [previous post][request-handlers] I talked about (among less interesting
things) trying to nest a list of handlers.  functools.partial provides an
elegant solution to this issue.


## Context

Here's the context to catch up without re-reading that entire post
(names have adjusted slightly)

``` python

class Extension(object):
    def before_operation(self, next, operation, context):
        # Do something before an operation starts
    def handle_operation(self, next, operation, context):
        # Do something immediately surrounding the operation
    def after_operation(self, next, operation, context):
        # Do something after an operation completes
        # Always fires
```

With a utility that builds single-hook extensions, we can have

``` python
@extension("handle_operation")
def cache(operation, context):
    try:
        return cache._cache[context["request"]]
    except KeyError:
        yield
```

And a pseudo-code sqlalchemy extension

``` python
class SQLAlchemy(Extension):
    def before_operation(self, next, operation, context):
        # Create a thread-local session
        s = self.thread_local.session = new_session()
        context["session"] = s
        next(operation, context)
    def after_operation(self, next, operation, context):
        # Probably need to catch/rollback here
        self.thread_local.session.commit()
        next(operation, context)
```


## Contrived example

Let's take the case of two extensions, `a` and `b`.  The first argument to `a`
is the next extension to call with an operation and context.  We could try to
explicitly pass `b.before_operation` but this will fail since
the first argument to `before_operation` is a function that `b` will invoke (in
this case, probably noop since it's the last of two extensions).  Since `a`
doesn't have a reference to the next next extension (noop) it needs to be
bundled inside the `next` passed to `a`.  Previously, I accomplished this with
a recursive function that tracked iteration:

``` python
def execute(operation, context, extensions):
    def next_handler(operation, context):
        self.index += 1
        if self.index >= len(extensions):
            return
        extensions[self.index](self, operation, context)
    self = next_handler
    self.index = -1
    self(operation, context)
```

Here, the `next_handler` method takes an operation and context, and selects the
appropriate extension to invoke next.  It then passes itself as the first
argument, so that it will be invoked by the next handler.

This isn't ideal.  It's recursive, so recursion limits are a risk.  The next
extension is computed each time (here just an index, but this doesn't hold as
we'll see in a minute) so a lot of logic is duplicated for every
before/handle/after operation.

## The magic

This is an ideal case for `functools.partial` - we're trying to preload some
arguments to a function (namely, the next extension in each call) and save them
so the pre-loaded version can be called without the caller knowing about the
extra arguments.

This is the boiled-down heart of it all

``` python
extensions = [a, b, c, d] # a invokes b invokes c invokes d
noop = lambda *a, *kw: None

next_obj = noop
for obj in reversed(extensions):
    func = getattr(obj, "before_operation", None)
    if func:
        next_obj = functools.partial(func, next_obj)
entry_point = next_obj
```

At the end of this, `entry_point` takes an `operation, context` and calls
`a.before_operation`, with the next partial (next_obj) as the first argument.
That partial takes an operation, context and passes them to the next extension,
with a first argument of, again, the next partial - next_obj from the second to
last iteration.  This is why the extensions are iterated in reverse.

If the extension doesn't have a before_operation method, it's passed over, and
not included in the partial chain.  This is the additional logic missing in the
original `execute` function above, and the check is too expensive on every
iteration.

# Generalize it

``` python
noop = lambda *a, **kw: None


class Chain(object):
    def __init__(self, objs):
        self.__objs = objs
        self.__chain = {}

    def __getattr__(self, name):
        # Since we're only here once, compile the partial chain
        self.__compile(name)

        # Bind the partial so next call avoids the __getattr__ overhead
        func = functools.partial(self.__invoke, name)
        setattr(self, name, func)

        # Return the __invoke partial
        return func

    def __compile(self, name):
        next_obj = noop
        for obj in reversed(self.__objs):
            func = getattr(obj, name, None)
            if func:
                next_obj = functools.partial(func, next_obj)
        self.__chain[name] = next_obj

    def __invoke(self, name, *args, **kwargs):
        return self.__chain[name](*args, **kwargs)
```

[Gist][chain-gist]

The magic is still there, in the `__compile` method.  Note that this is taking
a name argument instead of "before_operation" which allows it to build a chain
for any function that a particular set of objects has - or some subset may
have.  Actually, it doesn't matter if any of them have that method, since that
would leave next_obj as noop, and invoking that partial would do nothing.

Note that compile and invoke are private to reduce the chance of a name
collision, since functions are bound to the chain in __getattr__.

Let's talk about `__getattr__` a bit.  First, a partial is built for __invoke,
so that the name doesn't need to be passed again.  Then, that function is bound
to the chain object as the passed name, so that further calls will avoid the
compile and __getattr__ overhead.

``` python
chain = Chain(some_objects)

# Since chain has no foo attribute, __getattr__ is used
chain.foo(arg1, kwarg='Blah', other='Foo')

# Now, foo is defined on chain, so this doesn't fall back to __getattr__
chain.foo(arg1, kwarg='Blah', other='Foo')
```

Pre-loading the partial chains for an object is as easy as referencing them:

``` python
chain = Chain(extensions)
chain.before_operation
chain.handle_operation
chain.after_operation
```


[request-handlers]: {% post_url 2013-12-03-easier-request-handlers %}
[chain-gist]: https://gist.github.com/numberoverzero/c668f2f59817b8432770
