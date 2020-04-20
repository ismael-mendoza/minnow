#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from setuptools import setup

setup(
    name='gmodel',
    version='0.1',
    description='A compression library for cosmological data',
    long_description='A compression library for cosmological data',
    author='Phil Mansfield',
    author_email='',
    url='https://github.com/phil-mansfield/minnow',
    packages=[
        'pminh',
    ],
    python_requires='>=3.6',
    # scripts=[],
    # include_package_data=True,
    # zip_safe=False,
    install_requires=[
        'cython'
    ],  # requirements,
    license='MIT',
)
