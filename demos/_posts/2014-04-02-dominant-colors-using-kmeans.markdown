---
layout: post
title:  "Finding Dominant Colors Using Kmeans"
logline: "Pull colors out of images using math!"
---

<style>
.demo-input {border:1px solid gray;}
label { display: inline-block; width: 140px; text-align: right; }
</style>

This uses a javascript implementation of my [kmeans code for python][pykmeans], specifically the [c module][pykmeans-c].



<label>Image URL</label>
<input type="text" id="image-url" />

<label>Number of colors</label>
<input type="text" id="k" value="5" />

<label>Terminating constraint</label>
<input type="text" id="max-diff" value="1" />

<label>Maximum iterations</label>
<input type="text" id="max-iter" value="200" />

<button type="button" onclick="alert('Alert!');">Generate!</button>



[pykmeans]: https://github.com/numberoverzero/kmeans
[pykmeans-c]: https://github.com/numberoverzero/kmeans/blob/master/kmeans/_lib.c
