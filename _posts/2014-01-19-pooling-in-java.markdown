---
layout: post
title:  "Pooling in Java"
---


I've been playing around with [libgdx][libgdx] lately, and holy shit is it awesome.  This is a shocking departure from the blog's previous "all python all the time" tone - unfortunately, pygame was harder to install on both a windows and linux setup than installing intellij, eclipse, jdk7uXX, and libgdx.  I've done work in pygame [before][gritty] but the setup pain was too high.

# What's going on?

[Game Programming Patterns][gpp] explains an Object Pool better than I could ever hope to, so if you're not familiar with the term, head over there.  In fact, the section on finding the first available particle in [constant time][constant-lookup] is what prompted most of this work.  Well, that and needing a robut event system.  More on that next post.

Before the full breakdown, here's [all the code][pool-gist] for the following post, if you'd prefer to absorb it without my rambling explanations.

# Interface and enum

We want to pool arbitrary things, like particles and events and actors, so we'll need a "can-be-pooled" interface to start.

``` java
public interface Poolable<E> {
    E getNext();

    void setNext(E next);

    boolean isActive();

    E reset();
}
```

* `setNext`/`getNext` shouldn't surprise here, since we'll be using a stack based on a singly-linked list to track items in the pool.
* `isActive` is used by the pool when trying to acquire the next item, and probably by other application logic to decide if the values in the item are still valid.
* `reset` is a bit odd here.  It's used by the pool to clean up an inactive item before returning it for use during acquire, but it also returns a value.  This could be a void method, but I like chaining and libgdx is an enabler on that front.

``` java
public enum PoolBehavior {
    /**
     * Expand the pool to accommodate the call
     */
    EXPAND,

    /**
     * Return an item without expanding the pool, likely by
     * destroying/resetting another item that is active
     */
    DESTROY,

    /**
     * Return null if there is no inactive item to return
     */
    NULL
}
```

These should be somewhat straightforward.  This is used when the pool runs out of inactive items, and encounters an active item at the beginning of the list.  When you're pooling something that absolutely must be created and the others cannot be updated, such as collision events, use EXPAND.  When you can afford to kill active items or not make a new one - usually, most particle systems - DESTROY or NULL will keep memory bounded.

# PoolBuffer

``` java
public class PoolBuffer<E extends Poolable<E>> {
    private E head;

    public PoolBuffer() {
        head = null;
    }

    public E insert(E e) {
        e.setNext(head);
        head = e;
        return head;
    }

    public E peek() {
        return head;
    }

    public E pop() {
        E tmp = head;
        head = head.getNext();
        return tmp;
    }
}
```

This is just a stack backed by a singly-linked list.  Null/bounds checks are left as an exercise for the reader

# Pool

``` java
public class Pool<E extends Poolable<E>> {

    private final PoolBuffer<E> buffer;
    private final PoolBehavior behavior;
    private final Callable<? extends E> factory;

    public Pool(int size, PoolBehavior behavior, Callable<? extends E> factory) {
        if (size < 1) {
            throw new IllegalArgumentException("Invalid size " + size);
        }
        this.behavior = behavior;
        this.factory = factory;
        buffer = new PoolBuffer<>();

        // Keep a reference to the first element inserted (end of the list) so
        // that it can refer to the head when we're done generating elements
        E end = buffer.insert(create());
        for (int i = 0; i < size - 1; i++) {
            buffer.insert(create());
        }
        end.setNext(buffer.peek());
    }

    protected E create() {
        try {
            return factory.call();
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    public E acquire() {
        if (buffer.peek().isActive()) {
            switch (behavior) {
            case DESTROY:
                // Ignore that it's active and reset it anyway
                break;
            case EXPAND:
                release(create());
                break;
            case NULL:
                return null;
            }
        }
        return buffer.pop().reset();
    }

    public void release(E e) {
        if (e == null) {
            return;
        }
        assert !e.isActive();
        buffer.insert(e);
    }
}
```

Here's where it gets good.  In the constructor, we make sure the size is useful, and then use the provided Callable to initialize the pool to the specified size.  Because of how `acquire` and `release` will work, we loop the linked list.  Since we'd rather run into active items than run off the end of the buffer, the last item (the first we created) points to the current head.

* `create` is a wrapper around callable.  If we ever try to create and fail, that's a RTE and the game's over.
* `acquire` takes a special action if the next item is still active, but otherwise pops the head (advancing the buffer for the next acquire)
* `release` pushes the item to the head, so it will be the next item returned from `acquire`.

### How is 'return next inactive' an O(1) operation?

Initially, all of our items should be inactive.  Every acquire will remove an inactive item from the buffer - **mostly** - and return it.  Conversely, release should only put inactive events back in the buffer - at the front.  The **mostly** above is because we might exhaust the pool and then ask for the next item.  That's where the switch in acquire comes in: if the front of the buffer is active, we either ignore that the item is active (DESTROY) create a new item (EXAPND - releasing an item from the generator moves it to the front of the buffer) or don't return an item (NULL).  If the item isn't active or we don't care, it's popped off the buffer, reset, and returned.  That's where the chaining comes in.

# What's next?

An event system.  I wanted to generate tens of thousands of events in libgdx, without incurring gc and without the source of the event knowing about all the destinations.  That work is largely inspired by this [stack overflow post][so-events].  With the addition of pooling, it's possible to write the following:

``` java
public class Unit {
	private EventDispatcher dispatcher;

	public void hit(Unit source, int amount, DamageType type) {
		DamageEvent event = dispatcher.acquire(DamageEvent.class);
		event.update(this, source, amount, type);
		dispatcher.notify(event);
		dispatcher.release(event);
	}
}
```

The hit method doesn't need to know anything about event pooling, routing the message to appropriate listeners, or really anything.  It asks for an event, fills it out, sends it off, and then releases it back to the dispatcher - there's no garbage collection, so we don't have to worry about invoking a collection during an intense explosion, for instance.

[libgdx]: http://libgdx.badlogicgames.com/
[gritty]: https://github.com/numberoverzero/gritty
[gpp]: http://gameprogrammingpatterns.com/object-pool.html
[constant-lookup]: http://gameprogrammingpatterns.com/object-pool.html#faster-particle-creation
[pool-gist]: https://gist.github.com/numberoverzero/8510323
[so-events]: http://stackoverflow.com/a/942990
