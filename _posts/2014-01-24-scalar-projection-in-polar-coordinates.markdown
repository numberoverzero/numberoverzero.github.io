---
layout: post
title:  "Scalar Projection In Polar Coordinates"
---


This one's short, but I wanted to try out some MathJax.  Some definitions we'll need:

<div>\[\begin{eqnarray}
	x = r \cos \theta \\
	y = r \sin \theta \\
	r = \sqrt{x^2 + y^2} \quad \\
	|a| = \sqrt{a_x^2 + a_y^2} \quad \\
	a \cdot b = a_xb_x + a_yb_y \\
	s = \frac {\mathbf{a} \cdot \mathbf{b}} {|\mathbf{b}| }
\end{eqnarray}\]</div>

## Substitution!

<div>\[\begin{eqnarray}
	s = \frac {\mathbf{a} \cdot \mathbf{b}} {r_b } \\
	= \frac {a_xb_x + a_yb_y} {r_b } \\
	= \frac {(r_a \cos \theta_a)(r_b \cos \theta_b) + (r_a \sin \theta_a)(r_b \sin \theta_b)} {r_b } \\
	= \frac {(r_ar_b)(\cos \theta_a \cos \theta_b + \sin \theta_a \sin \theta_b)} {r_b } \\
	= (r_a)(\cos \theta_a \cos \theta_b + \sin \theta_a \sin \theta_b)
\end{eqnarray}\]</div>

## Why?

I'm doing a bunch of work with angles between vectors and projecting vectors back and forth.  Because sin and cos are pre-computed and only require indexing into the table, this is a fast way to compute the scalar projection.  It's less useful when working primarily in cartesian coordinates, since the length calculation (which includes a square root) still needs to happen.
