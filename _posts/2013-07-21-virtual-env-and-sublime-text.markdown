---
layout: post
title:  "Virtualenv and Sublime Text"
---


I have a particular fondness for developing with Python in Sublime Text.  It's clean and offers about as much "intelligent" autocomplete as I want.
I do not, however, enjoy arguing with Sublime Text's build system when I'm switching between projects with different environments.

These seem to be the popular suggestions:

* **Edit the build script when you switch environments.**  No, that sucks.  I don't want to think about build settings, I want to slam Ctrl+B and see magic happen.

* **Create a build script for each environment.**  Better, but now there's friction every time I create a new environment (which is pretty much every project).
Bonus, when you check the menu Tools > Build System there's 20 slightly different Python build systems.  That's not annoying.

* **`source bin/activate` is pretty easy, use that and leave the build system alone.**  Sorry, still too lazy for that.
In an ideal world, I never need to think about my environment again.  The possibility that I forgot a(n) (de)activate is another hoop to jump through when debugging a problem.

# Sell me a solution

Provided we make a 1:1 mapping between project and environment folder, it's really simple:
dispatch based on the location of the file you're running, or where you're running it from: [PyProMan][proj]

## Project setup

{% highlight bash %}
# Create a new project folder and a Python 3 environment:
~ $ proj init Spoon-Knife python3.3

# Setup environment for github project
~/projects $ git clone https://github.com/[username]/Spoon-Knife.git
~/projects $ cd Spoon-Knife
~/projects/Spoon-Knife $ proj init python3.3
{% endhighlight %}

## Usage

{% highlight bash %}
# Dependencies with pip:
~/projects/Spoon-Knife $ proj pip install requests

# Unit tests:
~/projects/Spoon-Knife $ proj nosetests

# Run a script:
~/projects/Spoon-Knife $ proj python myscript.py

# From a different folder:
~ $ proj python $PROJ/Spoon-Knife/myscript.py
{% endhighlight %}

# One build system to rule them all

That was the initial motivation, after all.  Since Sublime Text's build system executes from the directory the script is in,
we just edit the python build system to prepend "proj" and we're good to go.  For every project.  Don't touch it.

    {
      "cmd": ["proj", "python", "-u", "$file"],
      "file_regex":
        "^[ ]*File \"(...*?)\", line ([0-9]*)",
      "selector": "source.python",
      "env":
      {
        "PYTHONPATH": "$PROJ"
      }
    }

New overhead for using different environments with Sublime Text: **Zero.**


[proj]: https://github.com/numberoverzero/pyproman
