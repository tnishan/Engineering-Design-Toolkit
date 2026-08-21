"""Pure-Python calculation engine. No web framework imports belong in here.

The BLAS thread limits below must be set before NumPy is first imported.
Beam stiffness matrices are small (a few hundred degrees of freedom), and at
that size multi-threaded OpenBLAS spends far more time synchronising threads
than solving: on this machine a 242x242 solve measured 119 ms threaded versus
0.43 ms single-threaded. Auto-sizing runs hundreds of solves, so this is the
difference between 20 seconds and well under one.
"""

import os

for _var in (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ.setdefault(_var, "1")
