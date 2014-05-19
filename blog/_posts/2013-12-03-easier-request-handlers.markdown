---
layout: post
title:  "Easier request handlers"
---


Every time I start in on Yet Another Magic Card API, I get hung up on shit that probably shouldn't matter, like the wire format of nested filters.  Recently, it's how to easily add layers of handlers to the client/server if I need to extend it in the future.  And instead of reaching for an existing, well-tested, production-hardened solution like I should, I'll probably want to write an adapter and jam their model into my framework.  So I should at least make it easy to write the adapter, yeah?

tl;dr - Borrowed heavily from the @contextmanager implementation, dicts are cool.

# What do I want in a handler?

* **context** for the request I'm processing
* specify code to run **before** the rest of the chain processes the request
* specify code to run **after** the rest of the chain processes the request
* specify code to run if an **exception** occurs during the rest of the chain

## Oh boy, sounds like a situation for classes!

Here's a dumb translation of those requirements into a class:

``` python
class Handler(object):
    def before(self, context):
        # do stuff before the rest of the chain happens
        ...
    def after(self, context):
        # do stuff after the rest of the chain happens
        ...
    def exception(self, context):
        # do stuff when an exception occurs during the rest of the chain
        ...
```

And that's great and all, but look at all the shit I have to write to add timing:

``` python
class TimingHandler(Handler):
    def before(self, context):
        self.start_time = time.now()
    def after(self, context):
        logger.info(time.now() - self.start_time)
    def exception(self, context):
        logger.info(time.now() - self.start_time)
```

Anything I want to preserve from the `before` function for use in the `after` function gets dumped in `self`.

:(

## What about that @contextmanager thing?

Almost.

``` python
@handler
def timing_handler(context):
    start_time = time.now()
    try:
        yield
    finally:
        logger.log(time.now() - start_time)
```

`yield` represents the rest of the chain handling the request, so stuff before the yield happens before the chain - after the yield, after the chain.  Also, we don't need to store variables on `self` since it's one function.

This is also DRYer since we're not repeating the logging line.  And we get to use language constructs like `try` and `finally` without jamming them into a weird three-method model.

Oh, and I don't need to know the calling signature of the next handler, or what the next handler is.  I just let whatever is managing the execution order have control back, do its thing, and then return control to me on the way out of the chain.

## Sauce?

I got pretty confused trying to write this decorator and some of its edge cases, so I'm just going to dump it with comments in a [gist][handler-gist] and you can check it out.

Of interest, there's the `except:` block that throws **everything** from the rest of the chain's execution **back into the generator**, which is important because the generator is really the decorated fuction - without that, the exception propagates out of the wrapper since the wrapped function yielded control.

## Isn't this just contextmanager?

Not quite - contextmanager is almost perfect for this, except that we won't always run the next handler.  If we used contextmanager, it would read:

``` python
with handler(context):
    next_handler(context)
```

This won't work, because we'll **always** call the next handler.  A caching handler, which is trying to avoid invoking the rest of the handlers, won't yield if a cached version eists.  @contextmanager would throw a `RuntimeError` because the function doesn't yield for the end of the `__enter__` block that it's trying to set up.

Making things worse, we need to know about `next_handler` and how to call it, but we're nesting the handlers inside each other.  That callable needs to be set up to know the next handler in the chain, and the next after it, (and the next after it..) when we're only passing the context in.

Clever transition into...

# Chain-of-responsibility?

[Chain-of-responsbility][chain-wiki] on Wikipedia seems right for a sequence of handlers.  Here's the Java example from that page:

``` java
abstract class Logger {
    public static int ERR = 3;
    public static int NOTICE = 5;
    public static int DEBUG = 7;
    protected int mask;

    // The next element in the chain of responsibility
    protected Logger next;

    public void setNext(Logger log) {
        next = log;
    }

    public void message(String msg, int priority) {
        if (priority <= mask) {
            writeMessage(msg);
        }
        if (next != null) {
            next.message(msg, priority);
        }
    }

    abstract protected void writeMessage(String msg);
}
```

I dislike that each Logger has to keep track of not only the next logger in the chain, but must explicitly call the next logger's `message` method.  I should be able to say "execute these handlers, calling the next in the chain when the previous yields control" without first setting `previous.next = next` on each handler.  Setting an explicit next on each handler makes multi-threaded work fun, nevermind any sort of handler reconfiguration.  If I've got a `HeavyweightCacheHandler` which has a bunch of state, and I want to disconnect it from certain operations during load, there's not going to be a nice thread-safe solution which involves keeping a reference to the `next` handler on my cache handler instance.

## Flip it inside out

The almost-valid-python

``` python
def execute(context, handlers):
    index = -1
    def next_handler(context):
        index += 1
        if index >= len(handlers):
            return
        handlers[index](context, next_handler)
    next_handler(context)
```

Where a handler has the signature

``` python
def some_handler(context, next_handler):
    # some stuff
    next_handler(context)
    ...

```
And `next_handler` only takes one argument: `context`

It's a bit weird here that the call signature for a handler is two args, while the next handler (presumably, also a handler) only takes context.  What does that line up with?  The `@handler` decorator above!  While the decorated function only takes a context object, the wrapper returns a function with the correct handler signature of (context, next_handler).  So now we can write decorated functions that take a single argument that uses yield to invoke the next handler.

Of course, the above was almost-valid-python.  Python has some fun lexical scoping ideas, and since integers are immutable, the inner increment will fail with `UnboundLocalError` (see [SO][so-lexical] for one of many examples).  Python 3 adds the `nonlocal` keyword which helps us out, but there's no great solution in Python 2.x.  Either store the value you care about in a mutable variable (dict, list are common choices) or **store the variable on the inner function itself**.

### Wat

Functions are objects so it's all good.  You can't initialize the variable on the inner function until **after** the function's been created, so it can look a bit odd:

``` python
def counter():
    counter.value += 1
    return counter.value
counter.value = -1
```

I just alias the inner function to `self` and it feels like I'm working with an inner object again (because it is).  And we can use self (a mutable object) inside the function it refers to, as long as we alias `self` before the function is executed:

``` python
def execute(context, handlers):
    def next_handler(context):
        self.index += 1
        if self.index >= len(handlers):
            return
        handlers[self.index](context, self)
    self = next_handler
    self.index = -1
    next_handler(context)
```

# Give me the examples

Let's put these together and see how it looks:

``` python
@handler
def auth_handler(context):
    user = context.get("user", None)
    pw = context.get("pw", None)
    if not authenticated(user, pw):
        print "Could not authenticate %s" % user
    else:
        print "Authenticated user %s" % user
        yield

@handler
def cache_handler(context):
    key = tuple(context["input"])
    if key not in cache:
        print "Cache miss"
        yield
        cache[key] = context["output"]
    else:
        print "Cache hit"
        context["output"] = cache[key]
cache = {}

@handler
def wire_handler(context):
    '''Simulate the underlying function'''
    print "Calculating output"
    context["output"] = context["input"][:]

handlers = [auth_handler, cache_handler, wire_handler]

# Forgot pw
context = { "input": range(4), "user": "username"}
execute(context, handlers)  # stdout
                            # -----------
                            # Could not authenticate username

# Valid credentials
context = { "input": range(4), "user": "username", "pw": "hunter2"}
execute(context, handlers)  # stdout
                            # -----------
                            # Authenticated user username
                            # Cache miss
                            # Calculating output

# Cache hit
context = { "input": range(4), "user": "username", "pw": "hunter2"}
execute(context, handlers)  # stdout
                            # -----------
                            # Authenticated user username
                            # Cache hit
```

[handler-gist]: https://gist.github.com/numberoverzero/7765668
[so-lexical]: http://programmers.stackexchange.com/a/15507
[chain-wiki]: http://en.wikipedia.org/wiki/Chain-of-responsibility_pattern
