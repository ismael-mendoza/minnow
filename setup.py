#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from setuptools import setup
from distutils.core import setup
from Cython.Build import cythonize
import numpy as np

setup(
    name='pminh',
    version='0.1',
    description='A compression library for cosmological data',
    long_description='A compression library for cosmological data',
    author='Phil Mansfield',
    author_email='',
    url='https://github.com/ismael-mendoza/minnow',
    packages=[
        'pminh',
    ],
    ext_modules=cythonize("pminh/cy_bit.pyx"), 
    include_dirs=[np.get_include()],
    python_requires='>=3.6',
    # scripts=[],
    # include_package_data=True,
    # zip_safe=False,
    install_requires=[
        'cython'
    ],  # requirements,
    license='MIT',
)
